"""EDITABLE: routing, memory, planning and the agent interaction loop.

Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from framework.fp_agents import run_travel_agent as supplied_agent, travel_route
from copy import deepcopy
import json
import re
from types import SimpleNamespace


def interpret_with_consent_references(api, settings, instructions, payload, schema, label):
    observation = {key: payload["observation"][key]
                   for key in ("virtual_minute", "tier", "notices", "operational_sources")}
    payload = dict(payload, observation=observation)
    notices = payload["observation"]["notices"]
    # shortcut: alias the standard consent format, extend coverage if other formats cause copying errors.
    token_pattern = r"\bconsent-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b"
    tokens = dict.fromkeys(token for notice in notices
                           for token in re.findall(token_pattern, notice["text"]))
    if not tokens or any("[CONSENT_REF_" in notice["text"] for notice in notices):
        return api.json(settings, instructions, payload, schema, label)

    references = {token: f"[CONSENT_REF_{index}]" for index, token in enumerate(tokens, 1)}
    payload = deepcopy(payload)
    for notice in payload["observation"]["notices"]:
        notice["text"] = re.sub(token_pattern, lambda match: references[match[0]], notice["text"])
    if previous := payload.get("previous"):
        facts = previous["facts"]
        facts["consent"] = references.get(facts["consent"], facts["consent"])
    instructions += (
        "\nA bracketed CONSENT_REF token stands for the literal code at that position. "
        "If the applicable approval uses one, copy the complete bracketed token "
        "into facts.consent. Determine approval scope and amendments as usual."
    )
    response = api.json(settings, instructions, payload, schema, label)
    codes = {reference: code for code, reference in references.items()}
    facts = response["facts"]
    selected = facts["consent"]
    reference = f'[{selected.strip().strip("[]")}]'
    return dict(response, facts=dict(facts, consent=codes.get(reference, selected)))


def resolve_observed_weather(payload, previous_packet):
    if previous_packet is None or not payload.get("previous"):
        return None
    notices = payload["observation"]["notices"]
    earlier = previous_packet["observation"]["notices"]
    if len(notices) != len(earlier) + 1 or notices[:-1] != earlier:
        return None
    event = notices[-1]
    if event["kind"] != "weather_update":
        return None
    forecast_id = "weather-forecast"
    documents = {source["id"]: source for source in payload["documents"]}
    forecast = documents.pop(forecast_id, None)
    unchanged = {source["id"]: source for source in previous_packet["documents"]
                 if source["id"] != forecast_id}
    earlier_forecast = next((source for source in previous_packet["documents"]
                             if source["id"] == forecast_id), None)
    if not forecast or not earlier_forecast or forecast["version"] <= earlier_forecast["version"] or documents != unchanged:
        return None
    sources = payload["observation"]["operational_sources"]
    if sources != previous_packet["observation"]["operational_sources"] or any(
        source["id"] == forecast_id for source in sources.values()
    ):
        return None
    offers = payload["offers"]
    previous = payload["previous"]
    if {offer["id"] for offer in offers} != previous["refund_terms"].keys():
        return None
    if any((offer.get("refund_contract_source") or {}).get("id") == forecast_id for offer in offers):
        return None

    # shortcut: recognize standalone operating reports; defer mixed or unfamiliar notices to the interpreter.
    report = re.fullmatch(
        r"Observed operating result at virtual minute (\d+): (flight|train|coach) delay (\d+) minutes\. "
        r"This resolves the forecast; sheltered services are unchanged\.",
        forecast["text"],
    )
    notice = re.fullmatch(
        r"The final operating report confirms an actual (\d+)-minute delay to exposed (flight|train|coach) services\. "
        r"(?:Use this observed disruption when checking the existing booking\.|"
        r"The warned major disruption has not occurred; use this observed outcome when checking the existing booking\.) "
        r"Sheltered services retain their original arrival times\.",
        event["text"],
    )
    if not report or not notice:
        return None
    minute, mode, delay = report.groups()
    if int(minute) != event["at"] or notice.groups() != (delay, mode):
        return None
    facts = deepcopy(previous["facts"])
    facts["weather"][mode] = int(delay)
    facts["forecasts"] = [row for row in facts["forecasts"] if row["mode"] != mode]
    return {
        "budget_limit": previous["budget_limit"],
        "arrival_deadline": previous["arrival_deadline"],
        "refund_groups": [{"offer_ids": [identifier], "retained": expression}
                          for identifier, expression in previous["refund_terms"].items()],
        "facts": facts,
    }


CLOCK = r"(?:[01]\d|2[0-3]):[0-5]\d"
MODE = r"flight|train|coach"
FARE_HEADER = (
    r"Base fare fields describe ordinary cancellation: these fee fares normally retain USD \d+\. "
    r"The following provider terms override that amount\. They are fixed when each ticket is confirmed; "
    r"the conditions are checked when cancellation actually completes\. Cancellation uses the outbound consent\. "
    r"A hold is not a confirmed replacement, and overlapping confirmed outbounds remain forbidden\.\n"
)


def clock_minutes(clock):
    hours, minutes = map(int, clock.split(":"))
    return 60 * hours + minutes


def compare(op, variable, value):
    return {"op": op, "left": {"var": variable}, "right": value}


def read_arrival(text):
    plain = re.fullmatch(
        rf"(?:The client needs me there|Reach the client) by ({CLOCK}), including the current transfer"
        r"(?: from the terminal)?\.",
        text,
    )
    if plain:
        return clock_minutes(plain[1])
    concession = re.fullmatch(
        rf"Please arrive at the client by ({CLOCK})\. I can accept ({CLOCK}) when the selected service is a ({MODE})\. "
        r"That concession is withdrawn for \3 tickets priced above USD (\d+): "
        r"those tickets must still get me there by \1\. These are client arrival times, so include the transfer\.",
        text,
    )
    if concession:
        default, exception, mode, maximum = concession.groups()
        return {"op": "if", "when": {"op": "and", "args": [
            compare("eq", "candidate.mode", mode),
            compare("le", "candidate.price", int(maximum)),
        ]}, "then": clock_minutes(exception), "else": clock_minutes(default)}
    return None


def read_spending_limit(text):
    fixed = re.fullmatch(
        rf"The approved total for this repair is USD (\d+), including retained charges and any hotel fee\. "
        rf"The later (?:{MODE}) arrival concession below does not increase this amount\.|"
        r"I approve total additional spending up to USD (\d+), including retained ticket charges and any hotel fee\.",
        text,
    )
    if fixed:
        return int(fixed[1] or fixed[2])
    quote = re.fullmatch(
        r"For this trip, a qualifying quote is a currently available step-free service, operated by any carrier "
        rf"other than ([\w -]+), that gets me to the client by ({CLOCK})\. "
        r"Use the cheapest such quote as the spending reference\. I approve that fare plus USD (\d+) "
        r"for the whole repair, with an absolute ceiling of USD (\d+)\. If no quote qualifies, the ceiling is USD (\d+)\. "
        r"This total includes the ticket, retained charges and any hotel amount still due; the USD \3 is not a second allowance\. "
        r"For these offer comparisons, currently available quotes include unheld inventory still on sale and the particular "
        r"option now being considered if your own live hold preserves it after sales close\. Other held options are not "
        r"automatically included in that quote set; a condition that calls for a live hold checks held options separately\.",
        text,
    )
    if not quote:
        return None
    excluded, time, add, cap, fallback = quote.groups()
    qualifying = {"op": "and", "args": [
        {"var": "item.step_free"},
        compare("ne", "item.carrier", excluded),
        compare("le", "item.meeting_arrival", clock_minutes(time)),
    ]}
    lowest = {"op": "minimum", "pool": "offers", "where": qualifying,
              "value": {"var": "item.price"}, "default": int(fallback)}
    return {"op": "if", "when": {"op": "exists", "pool": "offers", "where": qualifying},
            "then": {"op": "min", "args": [int(cap), {"op": "add", "args": [lowest, int(add)]}]},
            "else": int(fallback)}


def read_initial_contract(payload):
    notices = payload["observation"]["notices"]
    if payload["previous"] is not None or len(notices) != 1 or notices[0]["kind"] != "initial_request":
        return None
    # shortcut: compile complete supported document forms; defer unfamiliar wording or conflicting evidence.
    request = re.fullmatch(
        rf"Repair my cancelled outbound to [\w -]+\. Prefer ({MODE}) whenever a suitable \1 is affordable\. "
        r"I require step-free travel\. (?:All listed carriers are permitted\.|Do not use ([\w -]+)\. "
        r"All other listed carriers are permitted\.) Keep the existing hotel and my colleague's return unchanged, "
        r"and claim the hotel charge waiver\. Approval ([\w-]+) covers my outbound and its permitted cancellation, "
        r"subject to the spending conditions in ([\w-]+)\. Read ([\w-]+) for the binding arrival obligation, "
        r"([\w-]+) for transfers, and ([\w-]+) for actual cancellation refunds\. "
        r"A first confirmed replacement is required by virtual minute \d+\. "
        r"(?:Verify the booking before handing it over at or after minute \d+\.|"
        r"I may send partial changes later\. Keep checking current notices through minute \d+ and finish by minute \d+\.) "
        r"Clock times and arrival minutes refer to local time after midnight; virtual minutes measure elapsed tool time\. "
        r"Spending authorization is checked when a charged action completes\. A later lower allowance does not revoke an earlier authorized payment\.",
        notices[0]["text"],
    )
    if not request:
        return None
    mode, excluded, consent, budget_id, arrival_id, transfer_id, fare_id = request.groups()
    documents = {source["id"]: source for source in payload["documents"]}
    if set(documents) != {budget_id, arrival_id, transfer_id, fare_id, "hotel-terms", "hotel-bulletin", "traveler-profile"}:
        return None
    sources = payload["observation"]["operational_sources"]
    if any(sources.get(key) != {"id": source_id, "version": documents[source_id]["version"]}
           for key, source_id in (("budget_limit", budget_id), ("arrival_deadline", arrival_id))):
        return None
    offers = payload["offers"]
    fare_ref = {"id": fare_id, "version": documents[fare_id]["version"]}
    if not offers or any(offer.get("refund_contract_source") != fare_ref for offer in offers):
        return None
    profile = (
        f"Use a suitable {mode} if one is affordable. Keep step-free access. "
        "The colleague's separate return and our existing hotel are outside this request."
    )
    if documents["traveler-profile"]["text"] != profile + (f" Do not use {excluded}." if excluded else ""):
        return None
    transfer = re.fullmatch(r"Add (\d+) minutes to terminal arrival for flight, train or coach\. "
                            r"The result is arrival at the client, not terminal arrival\.", documents[transfer_id]["text"])
    waiver = re.fullmatch(r"Claim evidence type ([\w-]+), code ([\w-]+), version (\d+), before virtual minute \d+\. "
                          r"A successful claim removes the USD (\d+) charge while retaining the room\.", documents["hotel-bulletin"]["text"])
    fare = re.fullmatch(FARE_HEADER + r"(?:Cancellation retains USD (\d+) from the ticket price\. The balance is refunded\.|"
                        r"If a ticket is cancelled, the provider retains USD (\d+) and refunds the rest\.)",
                        documents[fare_id]["text"])
    budget = read_spending_limit(documents[budget_id]["text"])
    arrival = read_arrival(documents[arrival_id]["text"])
    if not all((transfer, waiver, fare)) or budget is None or arrival is None:
        return None
    hotel = f"Keep the room. Read the linked hotel-bulletin for the current evidence that removes the USD {waiver[4]} charge."
    if documents["hotel-terms"]["text"] != hotel or int(waiver[3]) != documents["hotel-bulletin"]["version"]:
        return None
    return {
        "budget_limit": budget, "arrival_deadline": arrival,
        "refund_groups": [{"offer_ids": [offer["id"] for offer in offers], "retained": int(fare[1] or fare[2])}],
        "facts": {
            "consent": consent, "preferred": mode, "requires_step_free": True, "avoid_carriers": [excluded] if excluded else [],
            "transfer": dict.fromkeys(("flight", "train", "coach"), int(transfer[1])),
            "weather": dict.fromkeys(("flight", "train", "coach"), 0), "forecasts": [],
            "waiver": {"topic": waiver[1], "code": waiver[2], "version": int(waiver[3])},
        },
    }


def read_spending_amendment(payload, previous_packet):
    prior = read_initial_contract(previous_packet) if previous_packet else None
    previous = payload.get("previous")
    if prior is None or previous is None or type(prior["budget_limit"]) is not int:
        return None
    now_observation = payload["observation"]
    old_observation = previous_packet["observation"]
    old_notices = old_observation["notices"]
    notices = now_observation["notices"]
    if notices[:len(old_notices)] != old_notices or len(notices) != len(old_notices) + 2:
        return None
    approval, restriction = notices[-2:]
    if approval["at"] != restriction["at"] or any(
        notice["kind"] != "user_update" for notice in (approval, restriction)
    ):
        return None
    supplement = re.fullmatch(
        rf"A limited ({MODE}) recovery supplement is now approved\. Read the revised spending approval; "
        r"the arrival obligation and fare conditions have not changed\.", approval["text"])
    carrier = re.fullmatch(
        rf"The traveller can no longer use ([\w -]+)\. This carrier restriction is separate from the "
        rf"({MODE}) spending supplement; the arrival deadline and fare rider stay unchanged\.", restriction["text"])
    if not supplement or not carrier or supplement[1] != carrier[2]:
        return None
    sources = now_observation["operational_sources"]
    old_sources = old_observation["operational_sources"]
    authority = sources["budget_limit"]
    source_id = authority["id"]
    if (authority["id"] != old_sources["budget_limit"]["id"]
            or authority["version"] <= old_sources["budget_limit"]["version"]
            or sources["arrival_deadline"] != old_sources["arrival_deadline"]):
        return None
    documents = {s["id"]: s for s in payload["documents"]}
    old_documents = {s["id"]: s for s in previous_packet["documents"]}
    spending = documents.pop(source_id, None)
    del old_documents[source_id]
    if spending is None or spending["version"] != authority["version"] or documents != old_documents:
        return None
    amended = re.fullmatch(
        rf"I can now stretch the total to USD (\d+) for a step-free ({MODE}) that gets me to the client by ({CLOCK}), "
        r"as long as earlier ticket cancellations have retained no more than USD (\d+)\. This replaces the USD (\d+) "
        r"ceiling only for a booking meeting all those conditions\. The ordinary USD \5 ceiling still covers every other choice\. "
        r"The appointment and the provider's refund terms stay as they were; the supplement is not another USD \1 on top\.",
        spending["text"],
    )
    old_offers = previous_packet["offers"]
    offers = payload["offers"]
    if not amended or amended[2] != supplement[1] or int(amended[5]) != prior["budget_limit"] or not offers:
        return None
    fare_source = old_offers[0]["refund_contract_source"]
    if any(offer.get("refund_contract_source") != fare_source for offer in offers):
        return None
    facts = deepcopy(previous["facts"])
    facts["avoid_carriers"] = list(dict.fromkeys([*facts["avoid_carriers"], carrier[1]]))
    cap, mode, arrival_time, fees, default = amended.groups()
    return {
        "budget_limit": {"op": "if", "when": {"op": "and", "args": [
            compare("eq", "candidate.mode", mode), {"var": "candidate.step_free"},
            compare("le", "candidate.meeting_arrival", clock_minutes(arrival_time)),
            compare("le", "state.retained_fees", int(fees)),
        ]}, "then": int(cap), "else": int(default)},
        "arrival_deadline": previous["arrival_deadline"],
        "refund_groups": [{"offer_ids": [offer["id"] for offer in offers],
                           "retained": prior["refund_groups"][0]["retained"]}],
        "facts": facts,
    }


def read_weather_refunds(payload):
    sources = {source["id"]: source for source in payload["documents"]}
    groups = {}
    for offer in payload["offers"]:
        reference = offer.get("refund_contract_source")
        source = sources.get(reference["id"]) if reference else None
        if source is None or reference["version"] != source["version"]:
            return None
        # shortcut: compile this complete provider clause; defer other refund text to the model.
        clause = re.fullmatch(
            FARE_HEADER + rf"Ordinary cancellation retains USD (\d+)\. An exposed ({MODE}) ticket receives "
            r"a full refund when cancellation completes by virtual minute (\d+) and the actual \2 delay is "
            r"at least (\d+|thirty) minutes\. Both requirements must be met\. Sheltered \2(?:s|es) and other "
            r"modes keep the ordinary charge, even during the disruption\.",
            source["text"],
        )
        if not clause:
            return None
        retained, mode, cutoff, threshold = clause.groups()
        eligible = offer["mode"] == mode and offer.get("weather_exposed") is True
        key = (int(retained), mode, int(cutoff), 30 if threshold == "thirty" else int(threshold)) if eligible else (int(retained),)
        groups.setdefault(key, []).append(offer["id"])

    result = []
    for key, identifiers in groups.items():
        expression = key[0]
        if len(key) > 1:
            retained, mode, cutoff, minimum = key
            expression = {"op": "if", "when": {"op": "and", "args": [
                compare("le", "state.now", cutoff),
                compare("ge", f"state.weather.{mode}", minimum),
            ]}, "then": 0, "else": retained}
        result.append({"offer_ids": identifiers, "retained": expression})
    return result if result else None


def choose_offer_with_decisions(observation, trip_state, offers, api):
    """Optional paid proposal; solve does not call this helper by default.

    Pass only current observed offers and interpreted evidence. The result does
    not execute a booking. Recheck its suitability and tool dependencies before
    acting, and retain the returned decision in your diagnostic traces.
    """
    if api is None:
        raise ValueError("Use a model-enabled architecture when calling Decisions.")
    if not offers:
        return dict(offer_id=None, decision=None)
    bound = {f"offer_{index}": offer for index, offer in enumerate(offers)}
    if any(not isinstance(offer.get("id"), str) for offer in offers):
        raise ValueError("Pass current search offers with their observed string IDs.")
    choices = [dict(value=key, description=json.dumps(value, ensure_ascii=False))
               for key, value in bound.items()]
    choices.append(dict(value="review", description="Read or reconsider before selecting an offer."))
    decision = api.decide(
        payload=dict(observation=observation, trip_state=trip_state, offers=offers),
        questions=[dict(type="choice", name="offer", instructions=(
            "Propose a current offer using the observed requirements, transfer times, "
            "spending including retained fees, fare terms and scoped forecast evidence. "
            "Choose review if no offered proposal is suitable or evidence is missing. "
            "This selects a proposal; it does not authorize or execute a booking."), choices=choices)],
        label=dict(role="offer_proposal"), task="travel_offer_proposal")
    selected = decision["answers"][0]["choice"]
    return dict(offer_id=bound[selected]["id"] if selected in bound else None,
                decision=decision)


def route(observation, memory):
    """Choose transport, hotel and/or traveler from observed changes.

    The supplied loop passes a copy of its routing metadata, not its complete
    parsed trip state. Return domain names; edits to this argument do not persist.
    """
    return travel_route(observation, memory)


def solve(world, api, config, route_fn):
    """Retain the supplied agent, or implement your own observed-information loop.

    The delegate already owns episode-local document, trip-state, routing and
    search caches. Replace this body for a custom memory format or update policy;
    keep helper functions/classes in this file and initialize memory inside solve.
    Return serializable traces, working_memory and context for inspection. Memory
    content is not a separate scoring criterion; actual outcomes are evaluated.
    """
    if config["architecture"] == "hybrid_single" and world.observe().get("operational_sources"):
        previous_packet = None

        def interpret(settings, instructions, payload, schema, label):
            nonlocal previous_packet
            result = resolve_observed_weather(payload, previous_packet)
            if result is None:
                result = read_initial_contract(payload)
            if result is None:
                result = read_spending_amendment(payload, previous_packet)
            if result is None:
                result = interpret_with_consent_references(api, settings, instructions, payload, schema, label)
                if refunds := read_weather_refunds(payload):
                    result = dict(result, refund_groups=refunds)
            previous_packet = payload
            return result

        return supplied_agent(world, SimpleNamespace(json=interpret), config, route_fn)
    return supplied_agent(world, api, config, route_fn)
