"""EDITABLE: routing, memory, planning and the agent interaction loop.

Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from collections import defaultdict
from framework.common import object_schema
from framework.contract_interpreter import (BOOLEAN_VARIABLES, NUMBER_VARIABLES, STRING_VARIABLES,
                                            compile_contract, normalize_response)
from framework.contract_policy import Controller
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


def pack_observed_packet(payload):
    """Factor offer fields shared by every row, preserving the observed values."""
    offers = payload["offers"]
    if not offers:
        return payload
    fields = list(dict.fromkeys(key for offer in offers for key in offer))
    common = {key: offers[0][key] for key in fields if key in offers[0]
              and all(key in offer and offer[key] == offers[0][key] for offer in offers)}
    columns = [key for key in fields if key not in common]
    # Missing and explicit null values are distinct in the source packet.
    missing = {"absent": True}
    if any(offer.get(key) == missing for offer in offers for key in columns):
        return payload
    rows = [[offer.get(key, missing) for key in columns] for offer in offers]
    return dict(payload, offers=dict(shared=common, columns=columns, rows=rows))


def offer_references(payload, shape):
    """Use short, reversible aliases for opaque observed offer identifiers."""
    identifiers = [offer["id"] for offer in payload["offers"]]
    candidates = [identifier for identifier in identifiers
                  if len(identifier) >= 12 and any(c.isdigit() for c in identifier)
                  and re.fullmatch(r"[\w-]+", identifier)]
    aliases = {identifier: f"@O{index}@" for index, identifier in enumerate(candidates)}
    if not aliases or re.search(r"@O\d+@", json.dumps(payload)):
        return payload, shape, {}

    pattern = re.compile(r"(?<![\w-])(?:" + "|".join(
        re.escape(item) for item in sorted(aliases, key=len, reverse=True)) + r")(?![\w-])")

    def replace(value):
        if isinstance(value, str):
            return pattern.sub(lambda match: aliases[match[0]], value)
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        return value

    schema = deepcopy(shape)
    groups = schema["properties"]["refund_groups"]["items"]["properties"]["offer_ids"]["items"]
    groups["enum"] = [aliases.get(identifier, identifier) for identifier in groups["enum"]]
    return replace(payload), schema, {alias: identifier for identifier, alias in aliases.items()}


def restore_offer_references(value, references):
    if isinstance(value, str):
        return references.get(value, value)
    if isinstance(value, list):
        return [restore_offer_references(item, references) for item in value]
    if isinstance(value, dict):
        return {key: restore_offer_references(item, references) for key, item in value.items()}
    return value


def compact_initial(api, settings, instructions, payload, schema, label):
    """Share a strict expression grammar across contract output fields."""
    def request(local_settings, text, viewed, full, request_label):
        shape = deepcopy(full)
        props = shape["properties"]
        expr = {"$ref": "#/$defs/expression"}
        variables = sorted(set(NUMBER_VARIABLES + BOOLEAN_VARIABLES + STRING_VARIABLES))
        enum = lambda names: {"type": "string", "enum": list(names)}
        nodes = [
            {"type": "number"}, {"type": "boolean"}, {"type": "string"}, {"type": "null"},
            object_schema({"var": enum(variables)}),
            object_schema({"op": enum(("if",)), "when": expr, "then": expr, "else": expr}),
            object_schema({"op": enum(("not",)), "arg": expr}),
            object_schema({"op": enum(("and", "or", "add", "sub", "min", "max")),
                           "args": {"type": "array", "items": expr, "minItems": 1}}),
            object_schema({"op": enum(("eq", "ne", "lt", "le", "gt", "ge", "in")),
                           "left": expr, "right": expr}),
            object_schema({"op": enum(("exists",)), "pool": enum(("offers", "holds")), "where": expr}),
            object_schema({"op": enum(("minimum",)), "pool": enum(("offers", "holds")),
                           "where": expr, "value": expr, "default": {"type": "number"}}),
            {"type": "array", "items": expr},
        ]
        shape["$defs"] = {"expression": {"anyOf": nodes}}
        props["budget_limit"] = expr
        props["arrival_deadline"] = expr
        props["refund_groups"]["items"]["properties"]["retained"] = expr
        visible = dict(viewed, offers=[{key: value for key, value in offer.items()
                                      if key not in {"observed_at", "fare_fields_scope"}}
                                     for offer in viewed["offers"]])
        referenced, shape, references = offer_references(visible, shape)
        packed = pack_observed_packet(referenced)
        if isinstance(packed["offers"], dict):
            text += ("\nOffers are a table. Each row inherits all shared fields and adds the values "
                     "listed in columns in order. An absent marker means the field was missing.")
        if references:
            text += "\nUse the observed @O#@ offer references verbatim when returning an offer ID."
        response = api.json(local_settings, text, packed, shape, dict(request_label, stage="packed_evidence"))
        return restore_offer_references(response, references) if references else response

    response = interpret_with_consent_references(
        SimpleNamespace(json=request), settings, instructions, payload, schema, label,
    )
    normalize_response(response, payload["offers"])
    return response


def interpret_amendment(api, settings, payload, previous_packet, schema, label):
    """Compile only changed authority documents and affected fare terms."""
    prior = payload["previous"]
    if prior is None or previous_packet is None:
        return None
    old_observation = previous_packet["observation"]
    observation = payload["observation"]
    old_notices = old_observation["notices"]
    notices = observation["notices"]
    arrived = notices[len(old_notices):]
    if (not arrived or notices[:len(old_notices)] != old_notices
            or any(notice["kind"] != "user_update" for notice in arrived)):
        return None

    old_docs = {doc["id"]: doc for doc in previous_packet["documents"]}
    docs = {doc["id"]: doc for doc in payload["documents"]}
    sources = observation["operational_sources"]
    old_sources = old_observation["operational_sources"]
    rule_keys = ("budget_limit", "arrival_deadline")
    offers = {offer["id"]: offer for offer in payload["offers"]}
    old_offers = {offer["id"]: offer for offer in previous_packet["offers"]}
    fare_sources = {identifier: offer["refund_contract_source"] for identifier, offer in offers.items()}
    refs = [sources[key] for key in rule_keys] + list(fare_sources.values())
    if any(docs.get(ref["id"], {}).get("version") != ref["version"] for ref in refs):
        return None
    changed_docs = {key for key in docs.keys() | old_docs.keys() if docs.get(key) != old_docs.get(key)}
    if not changed_docs <= {ref["id"] for ref in refs}:
        return None
    rules = [key for key in rule_keys if sources[key] != old_sources[key]
             or sources[key]["id"] in changed_docs]

    def fare_fields(offer):
        return {key: value for key, value in offer.items() if key != "observed_at"}

    changed_fares = {identifier: ref for identifier, ref in fare_sources.items()
                     if identifier not in prior["refund_terms"]
                     or fare_fields(offers[identifier]) != fare_fields(old_offers.get(identifier, {}))
                     or ref["id"] in changed_docs}
    evidence_ids = {sources[key]["id"] for key in rules} | {ref["id"] for ref in changed_fares.values()}
    fact_names = ("consent", "preferred", "requires_step_free", "avoid_carriers")
    fact_schema = schema["properties"]["facts"]["properties"]
    properties = {key: schema["properties"][key] for key in rules}
    properties.update({key: {"anyOf": [fact_schema[key], {"type": "null"}]} for key in fact_names})
    if changed_fares:
        properties["refunds"] = object_schema({
            identifier: {"$ref": "#/$defs/refund_expression"} for identifier in changed_fares
        })
    properties["requires_full"] = {"type": "boolean"}
    shape = object_schema(properties)
    if rules or changed_fares:
        shape["$defs"] = schema["$defs"]

    instructions = """Compile the arrived user amendments from the listed current sources.
Return complete executable expressions for the requested rules. Use the previous rule
only to keep terms outside the amendment's scope. Return the TOTAL spending ceiling.
The planner compares the total ledger expense against your result. If the amended
authority states a new total ceiling of USD 240, return 240. Retained charges, current
spending and hotel fees are counted by the planner. Subtract costs only if the source
explicitly specifies a formula for the ceiling itself. Keep any conditions that change
the total ceiling. Arrival is the binding client-site clock deadline in minutes
since midnight, before subtracting any transfer. Refunds are dollars retained or null
for prohibited cancellation. Apply each fare document to its corresponding offer only.
Use candidate for the proposed ticket, booking for the existing booking and item only
inside the offers or holds quantifier. Meeting arrival includes transfer. state.now is
the action completion minute. state.total_refunds means actual credits received.
Put a conditional threshold in the numeric branches of an if. Approval codes are
ordinary facts, never a state variable or part of a monetary expression.
Return null for each unchanged traveler fact, or the full new value if explicitly amended.
Copy any new consent code verbatim from the arrived notices. Reuse prior facts for
unchanged authority. The model can update several fields together. For example, a
new carrier restriction can be returned in avoid_carriers alongside a revised budget
expression. Keep booking eligibility conditions in the correct expression. Mention of
an unchanged rule does not require recompiling it. Request a full interpretation
only if a required expression or newly changed fact cannot be represented from the
provided evidence. If requires_full is true, the caller ignores the other fields."""
    evidence = dict(
        notices=arrived,
        documents={key: docs[key]["text"] for key in sorted(evidence_ids)},
        rule_sources={key: sources[key] for key in rules},
        previous={key: prior[key] for key in rules},
        traveler={key: prior["facts"][key] for key in fact_names},
        fare_sources=changed_fares,
        new_fares={identifier: offers[identifier] for identifier in changed_fares},
    )
    reply = api.json(settings, instructions, evidence, shape, dict(label, stage="typed_amendment"))
    if reply["requires_full"]:
        return None
    consent = reply["consent"]
    if consent not in (None, prior["facts"]["consent"]) and (not consent or not any(
            consent in notice["text"] for notice in arrived)):
        return None
    facts = dict(prior["facts"], **{key: reply[key] for key in fact_names if reply[key] is not None})
    refunds = reply.get("refunds", {})
    result = {key: reply[key] if key in rules else prior[key] for key in rule_keys}
    result.update(facts=facts, refund_groups=[
        dict(offer_ids=[identifier], retained=refunds[identifier] if identifier in refunds
             else prior["refund_terms"][identifier]) for identifier in offers
    ])
    try:
        normalize_response(result, payload["offers"])
    except ValueError:
        return None
    return result


def weather_delta(api, settings, payload, previous_packet, schema, label):
    """Reinterpret a weather-only update without rebuilding unchanged contracts."""
    previous = payload["previous"]
    if previous is None or previous_packet is None:
        return None
    old_observation, observation = previous_packet["observation"], payload["observation"]
    old_notices, notices = old_observation["notices"], observation["notices"]
    new_notices = notices[len(old_notices):]
    if notices[:len(old_notices)] != old_notices or not new_notices or any(
        notice["kind"] not in {"weather_update", "forecast_update"} for notice in new_notices
    ):
        return None
    if old_observation["operational_sources"] != observation["operational_sources"]:
        return None
    forecast_key = "weather-forecast"
    old_documents = {d["id"]: d for d in previous_packet["documents"]}
    documents = {d["id"]: d for d in payload["documents"]}
    forecast = documents.pop(forecast_key, None)
    old_forecast = old_documents.pop(forecast_key, None)
    if not forecast or not old_forecast or documents != old_documents:
        return None
    offers = payload["offers"]
    old_offers = {offer["id"]: offer for offer in previous_packet["offers"]}
    if {offer["id"] for offer in offers} != old_offers.keys() or any(
        (offer.get("refund_contract_source") or {}).get("id") == forecast_key for offer in offers
    ):
        return None
    # Search may refresh arrival and observation time. Preserve the complete
    # compiler when any other offer evidence changes.
    dynamic = {"arrival_minute", "observed_at"}
    for offer in offers:
        old_offer = old_offers[offer["id"]]
        if {k: v for k, v in offer.items() if k not in dynamic} != {
            k: v for k, v in old_offer.items() if k not in dynamic
        }:
            return None
    facts_schema = schema["properties"]["facts"]["properties"]
    fields = dict(weather=facts_schema["weather"], forecasts=facts_schema["forecasts"],
                  weather_only={"type": "boolean"})
    shape = dict(type="object", properties=fields, required=list(fields), additionalProperties=False)
    instructions = (
        "Update actual delays by mode and unresolved forecasts from this observed update. "
        "Keep previous actual delays outside the update. A possibility is never an actual delay. "
        "Remove resolved forecasts. For an unresolved forecast use the virtual time of its expected "
        "final report, not the bulletin time; use null for unknown values. Set weather_only true "
        "when the update only reports weather, revised forecasts, their physical effects or instructions "
        "to check affected bookings. Keep any pre-existing rules that depend on weather. Set it false "
        "if the text itself adds or changes a non-weather rule, requirement, permission, or preference."
    )
    old_facts = previous["facts"]
    detected = {}
    actual_update = any(n["kind"] == "weather_update" for n in new_notices)
    if actual_update:
        for offer in offers:
            old_offer = old_offers[offer["id"]]
            if offer.get("observed_at") == old_offer.get("observed_at"):
                continue
            difference = offer["arrival_minute"] - old_offer["arrival_minute"]
            if not offer["weather_exposed"]:
                if difference:
                    return None
                continue
            mode = offer["mode"]
            inferred = old_facts["weather"][mode] + difference
            if inferred < 0 or (mode in detected and detected[mode] != inferred):
                return None
            detected[mode] = inferred
    instructions += (" Any corroborated actual delays shown in observed_arrival_deltas are authoritative. "
                     "Keep them as supplied and resolve forecasts for those reports where applicable.")
    reply = api.json(dict(settings, effort="none"), instructions, dict(
        notices=new_notices, forecast=forecast["text"],
        weather=old_facts["weather"], forecasts=old_facts["forecasts"],
        observed_arrival_deltas=detected,
    ), shape, dict(label, stage="weather_delta"))
    if not reply["weather_only"]:
        return None
    facts = dict(old_facts, weather={**reply["weather"], **detected}, forecasts=reply["forecasts"])
    return dict(budget_limit=previous["budget_limit"], arrival_deadline=previous["arrival_deadline"],
                refund_groups=[dict(offer_ids=[key], retained=rule)
                               for key, rule in previous["refund_terms"].items()], facts=facts)


class ForecastController(Controller):
    def prepare(self, observation, booking):
        """Evaluate compatible delays from the same announced report together."""
        reports = defaultdict(dict)
        conflicts = set()
        for forecast in self.facts["forecasts"]:
            at, delay = forecast.get("at"), forecast.get("delay")
            if type(at) not in (int, float) or type(delay) not in (int, float) or at <= self.world.now:
                continue
            mode = forecast["mode"]
            if mode in reports[at] and reports[at][mode] != delay:
                conflicts.add(at)
            reports[at][mode] = delay
        joint_reports = {at: delays for at, delays in reports.items()
                         if len(delays) > 1 and at not in conflicts}
        if not joint_reports:
            return super().prepare(observation, booking)

        opportunities = []
        for at, delays in joint_reports.items():
            weather = {**self.facts["weather"], **delays}
            if self.keep_valid(observation, booking, weather=weather, at=at):
                continue
            if any(hold["status"] == "held" and hold["expires_at"] > at + 4
                   and (candidate := self.offers.get(hold["option_id"])) is not None
                   and self.purchase_plan(observation, candidate, booking, weather=weather, at=at) is not None
                   for hold in observation["holds"]):
                continue
            for offer in self.candidates(observation):
                if offer["id"] == booking["option_id"] or not self.world.now + 1 < offer["expires_at"] <= at + 1:
                    continue
                fee = offer.get("hold_fee_usd", 0)
                if fee:
                    context = self.context(observation, offer, at=self.world.now + 1)
                    limit = self.number(self.program["budget_limit"], context)
                    if limit is None or observation["net_transport_spend_usd"] + observation["hotel_fee"] + fee > limit:
                        continue

                # Project the deposit and live reservation before evaluating recovery.
                imagined = deepcopy(observation)
                imagined["virtual_minute"] = at
                imagined["net_transport_spend_usd"] += fee
                imagined["uncredited_hold_deposits_usd"] += fee
                imagined["holds"].append(dict(offer, id="anticipated-hold", option_id=offer["id"],
                    held_at=self.world.now + 1, expires_at=observation["horizon"], deposit_paid_usd=fee, status="held"))
                plan = self.purchase_plan(imagined, offer, booking, weather=weather, at=at)
                if plan is not None:
                    opportunities.append((not plan["preferred"], fee, plan["expense"], offer["expires_at"], offer["id"]))
        if not opportunities:
            return super().prepare(observation, booking)
        _, _, _, expires_at, offer_id = min(opportunities)
        latest_start = expires_at - 2
        if self.world.now < latest_start:
            return latest_start
        result = self.call("hold", id=offer_id)
        self.trace.append(dict(kind="preparation", strategy="joint operating report",
                               option_id=offer_id, result=deepcopy(result)))
        return self.world.now if result.get("ok") else None


def solve(world, api, config, route_fn):
    if config["architecture"] != "hybrid_single" or not world.observe().get("operational_sources"):
        return supplied_agent(world, api, config, route_fn)

    traces = []
    previous_packet = None

    def interpret(settings, instructions, payload, schema, label):
        nonlocal previous_packet
        if payload["previous"] is None:
            instructions += (
                "\nBefore encoding refund_groups, resolve each offer's linked fare source and version "
                "against that offer's carrier, mode and any other clause qualifiers. "
                "Apply the most specific matching clause even when the offer's base change policy "
                "or cancellation fee conflicts with the source. The expression is dollars retained: "
                "a full refund retains 0, a partial refund retains the unreturned amount, and a "
                "prohibition on cancelling returns null. Keep conditions in the expression so their "
                "eligibility can be evaluated at cancellation. The holds pool already contains only "
                "live holds at action completion. For a rule requiring a live hold, filter the holds pool "
                "by the stated qualifications. Never add an expired-hold condition for a live hold. "
                "Use base terms only for situations "
                "the linked source leaves uncovered. Group offers only after resolving their terms."
            )
        response = weather_delta(api, settings, payload, previous_packet, schema, label)
        if response is None:
            response = interpret_amendment(api, settings, payload, previous_packet, schema, label)
        previous_packet = payload
        if response is None and payload["previous"] is None:
            try:
                response = compact_initial(api, settings, instructions, payload, schema, label)
            except ValueError:
                response = None
        if response is None:
            response = interpret_with_consent_references(api, settings, instructions, payload, schema, label)
        try:
            normalize_response(response, payload["offers"])
        except ValueError as error:
            instructions += (
                f"\nThe previous compilation failed contract validation: {error}. "
                "Recompile from the observed sources and check the complete response against the schema."
            )
            return interpret_with_consent_references(
                api, settings, instructions, payload, schema, dict(label, attempt="validation_retry"),
            )
        return response

    gateway = SimpleNamespace(json=interpret)
    controller = ForecastController(
        world, lambda payload: compile_contract(payload, gateway, config, (), traces), traces,
        refresh_context=config["refresh_context"], max_decisions=config["max_decisions"],
        prepare=config.get("forecast_strategy", "precaution") != "cheapest",
    )
    controller.run()
    return dict(traces=traces, working_memory=dict(documents=controller.documents,
        compiled=controller.program, purchased_refund_terms=controller.booked_programs,
        purchased_refund_evidence=controller.booked_evidence),
        context=dict(architecture=config["architecture"],
                     source_versions={name: source["version"] for name, source in controller.documents.items()}))
