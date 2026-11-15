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
from framework.operational_expressions import validate_expression
from framework.fp_agents import run_travel_agent as supplied_agent, travel_route
from framework.fp_world import FP_TOOL_DURATIONS
from copy import deepcopy
import ast
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


INITIAL_INSTRUCTIONS = """Compile the observed lead-outbound agreement into this executable schema.
- budget_limit: TOTAL authorized expense, including retained charges, deposits and hotel fee. The planner counts actual expenses; only subtract when the source defines the ceiling that way.
- arrival_deadline: client-site deadline as local clock minutes (HH*60+MM). Planner adds transfer to arrival, never subtract transfer from the deadline. A mode concession applies only to that mode. Preserve exceptions to exceptions.
- refund_groups: assign each offer exactly once, using its linked source and version. Resolve the most specific matching carrier, mode or offer clause before grouping identical rules. Return dollars kept, 0 for full refund, null when cancellation is forbidden. Base fee/change fields apply where the source leaves a gap. Terms freeze at purchase and are evaluated at cancellation completion.
- facts: exact current outbound approval token, access requirement, exclusions, mode preference, mode transfers and current bulletin's evidence type, code and version. For each uncertain delay, make a forecast row. The at field is the announced time of the FINAL upcoming notice that will reveal whether that particular delay occurs. Read the sentence scheduling that report; use that virtual minute even when the warning arrived earlier. Do not use the now minute, warning issue minute, recovery sales cutoff or hold expiry. Null only if the source leaves a field unspecified. Until realization keep facts.weather zero for the predicted delays. Apply actual delays only to the affected mode and exposure.
Return the numeric ceiling or clock deadline, never a Boolean check of price or arrival. Example: a USD 210 ceiling yields 210, and a 10:55 client deadline yields 655. For conditional limits use the conditions solely under if.when. Use literal numbers/booleans/strings and {"var":"state.now"} for variables. Use schema operators. Put numeric thresholds in if branches; use op/when/then/else for if. 'sub' takes two args and 'in' takes a list on the right. candidate is the proposed offer or hold (confirmed ticket when checking arrival), booking is the current ticket, both refer to the cancelled ticket when evaluating refunds. item is bound only inside an offers/holds quantifier. holds contains only live holds at completion; filter it to the conditions stated in the source. A replacement hold need not match the cancelled ticket ID. state.now is virtual action-completion minute. state amounts are actual ledger amounts. meeting_arrival includes transfer. Use the current source versions and apply scope exactly; avoid guessing missing events or returning prose."""


def pack_initial_documents(documents):
    if any(set(doc) != {"id", "version", "title", "text", "related"} for doc in documents):
        return documents
    indexed = {doc["id"]: [doc["version"], doc["title"], doc["text"], *doc["related"]]
               for doc in documents}
    return indexed if len(indexed) == len(documents) else documents


def collapses_observed_budget(response, payload):
    if type(response["budget_limit"]) not in (int, float):
        return False
    ref = payload["observation"]["operational_sources"]["budget_limit"]
    text = next((doc["text"] for doc in payload["documents"]
                 if doc["id"] == ref["id"] and doc["version"] == ref["version"]), "")
    amounts = re.findall(r"(?:\bUSD\s+|\$)(\d+(?:,\d{3})*(?:\.\d+)?)", text, re.IGNORECASE)
    return len({float(amount.replace(",", "")) for amount in amounts}) > 1


def observed_clocks(payload, key="arrival_deadline"):
    ref = payload["observation"]["operational_sources"][key]
    text = next((doc["text"] for doc in payload["documents"]
                 if doc["id"] == ref["id"] and doc["version"] == ref["version"]), "")
    clock_pattern = r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])"
    if re.search(r"\d\s*(?:a\.?m\.?|p\.?m\.?)\b", text, re.IGNORECASE):
        return {}
    return {m[0]: 60 * int(m[1]) + int(m[2]) for m in re.finditer(clock_pattern, text)}


def restore_deadline(expression, clocks):
    if isinstance(expression, list):
        return [restore_deadline(child, clocks) for child in expression]
    if not isinstance(expression, dict):
        return expression
    if expression.keys() == {"clock"}:
        return clocks[expression["clock"]]
    return {key: restore_deadline(child, clocks) for key, child in expression.items()}


INFIX_INSTRUCTIONS = """Compile current linked travel rules. Output b and a as expression strings.
b is the TOTAL authorized ceiling including fees. The planner counts costs against it.
Use the stated limit directly; subtract expenses only if the source defines that formula.
a is the binding deadline at the client in minutes since midnight. The planner adds
transfer to terminal arrival. Copy an explicit source clock as clock("HH:MM"); Python converts it.
Use plain numeric values for derived durations. Never subtract transfer from a client-site deadline.
A comparison cutoff or early incentive is not an arrival obligation. Preserve nested
exceptions with their complete mode, price, time and carrier scope.

Use Python expression syntax: literals, dotted variables, +, -, min(), max(),
comparisons including in, and/or/not, and value if condition else other.
Use exists("holds", condition) or minimum("offers", condition, value, fallback).
item exists only inside its quantifier. candidate is the proposed ticket; booking is
the existing purchase. Compare option_id when relating a purchase or hold to an offer.
At cancellation candidate and booking both refer to the cancelled ticket. Do not assume
a replacement must be the same ticket. Holds already contain only live holds.
Offers include available offers and the candidate's valid held quote. state.now is
the action completion minute. state.weather.MODE is actual delay. state.retained_fees
is retained cancellation cost; state.total_refunds is refunded money. Use
candidate.meeting_arrival for client arrival. Other documented fields keep their names.

Output rules as distinct retained-dollar expressions. Use 0 for a full refund and
None when cancellation is forbidden. Map each offer row to its zero-based rule index
in r. Match each offer to its own linked fare clause, using base terms only for gaps.
Do not put redundant checks of the current offer ID in the rule. Never test expiry of a live hold. Terms freeze at
purchase; evaluate their conditions at cancellation.

Copy consent and waiver proof verbatim. waiver.topic is the name of the evidence item
the bulletin asks the traveler to present. Copy its code and version from that bulletin.
Transfer adds to terminal arrival. Copy carrier exclusions, access and mode preference.
Actual weather is zero until observed. Include a forecast only for a mode with an
unresolved possibility reported in the evidence. Report possible delay, probability
and the final operating report minute, distinct from issue or backup sale cutoff time.
Use null for unannounced quantities within a reported forecast. Use an empty list
when there are no forecasts. Compile rules without selecting an offer.
"""


def decode_infix(source, clocks=None):
    """Translate a bounded expression subset without executing Python."""
    if len(source) > 2400:
        raise ValueError("Expression exceeds the compiler limit")
    comparison = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le",
                  ast.Gt: "gt", ast.GtE: "ge", ast.In: "in"}

    def parse(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str, bool, type(None)):
            return node.value
        if isinstance(node, ast.Attribute):
            name = ast.unparse(node)
            if name in NUMBER_VARIABLES or name in STRING_VARIABLES or name in BOOLEAN_VARIABLES:
                return {"var": name}
        if isinstance(node, (ast.List, ast.Tuple)):
            return [parse(item) for item in node.elts]
        if isinstance(node, ast.IfExp):
            return dict(op="if", when=parse(node.test), then=parse(node.body), **{"else": parse(node.orelse)})
        if isinstance(node, ast.BoolOp):
            return dict(op="and" if isinstance(node.op, ast.And) else "or",
                        args=[parse(item) for item in node.values])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return dict(op="not", arg=parse(node.operand))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            number = parse(node.operand)
            if type(number) in (int, float):
                return -number
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            return dict(op="add" if isinstance(node.op, ast.Add) else "sub",
                        args=[parse(node.left), parse(node.right)])
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            tests = []
            for index, operator in enumerate(node.ops):
                left = parse(operands[index])
                right = parse(operands[index + 1])
                if isinstance(operator, ast.NotIn):
                    tests.append(dict(op="not", arg=dict(op="in", left=left, right=right)))
                elif type(operator) in comparison:
                    tests.append(dict(op=comparison[type(operator)], left=left, right=right))
                else:
                    raise ValueError("Unsupported comparison")
            return tests[0] if len(tests) == 1 else dict(op="and", args=tests)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            args = [parse(arg) for arg in node.args]
            if name == "clock" and len(args) == 1 and isinstance(args[0], str) and args[0] in (clocks or {}):
                return clocks[args[0]]
            if name in {"min", "max"} and args:
                return dict(op=name, args=args)
            if name == "exists" and len(args) == 2:
                return dict(op=name, pool=args[0], where=args[1])
            if name == "minimum" and len(args) == 4:
                return dict(op=name, pool=args[0], where=args[1], value=args[2], default=args[3])
        raise ValueError("Unsupported expression syntax")

    try:
        return parse(ast.parse(source.strip(), mode="eval").body)
    except (SyntaxError, RecursionError) as error:
        raise ValueError("Invalid rule expression") from error


def client_deadline_value(expression):
    """Recover the numeric endpoint from an equivalent planner comparison."""
    if not isinstance(expression, dict):
        return expression
    op = expression.get("op")
    if op == "if":
        return dict(expression, then=client_deadline_value(expression["then"]),
                    **{"else": client_deadline_value(expression["else"])})
    candidate_clock = {"var": "candidate.meeting_arrival"}
    if op == "le" and expression["left"] == candidate_clock:
        return expression["right"]
    if op == "ge" and expression["right"] == candidate_clock:
        return expression["left"]
    return expression


def written_ceiling_values(payload):
    ref = payload["observation"]["operational_sources"]["budget_limit"]
    text = next((doc["text"] for doc in payload["documents"]
                 if doc["id"] == ref["id"] and doc["version"] == ref["version"]), "")
    return {float(value.replace(",", "")) for value in
            re.findall(r"(?:\bUSD\s+|\$)(\d+(?:,\d{3})*(?:\.\d+)?)", text, re.IGNORECASE)}


def simple_literal_authorities(payload):
    if not len(written_ceiling_values(payload)) == len(set(observed_clocks(payload).values())) == 1:
        return False
    refs = {(ref["id"], ref["version"]) for ref in payload["observation"]["operational_sources"].values()}
    authority = "\n".join(doc["text"] for doc in payload["documents"]
                          if (doc["id"], doc["version"]) in refs)
    quote_values = {offer[key] for offer in payload["offers"] for key in ("carrier", "mode")}
    return not any(re.search(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])", authority, re.IGNORECASE)
                   for value in quote_values if value)


def decode_grounded_limit(value, clocks, spending_text=""):
    if type(value) in (int, float):
        return value
    value = value.strip()
    if value in clocks:
        return clocks[value]
    money = r"(?:\bUSD\s+|\$)(\d+(?:,\d{3})*(?:\.\d+)?)"
    if spending_text and (match := re.fullmatch(money, value, re.IGNORECASE)):
        amount = float(match[1].replace(",", ""))
        observed = {float(written.replace(",", ""))
                    for written in re.findall(money, spending_text, re.IGNORECASE)}
        if amount not in observed:
            raise ValueError("Currency literal is absent from the operative authority")
        return amount
    return decode_infix(value, clocks)


def cited_infix_initial(api, settings, payload, base_schema, label, *, defer=False):
    def request(local_settings, instructions, viewed, full, call_label):
        clocks = observed_clocks(viewed)
        policy_clocks = clocks | observed_clocks(viewed, "budget_limit")
        visible = dict(viewed, offers=[{key: value for key, value in offer.items()
                                      if key not in {"observed_at", "fare_fields_scope"}}
                                     for offer in viewed["offers"]])
        referenced, _, aliases = offer_references(visible, full)
        packed = pack_observed_packet(referenced)
        isolate = defer and local_settings["model"] == "gpt-5-nano"
        if isolate:
            text = "\n".join(doc["text"] for doc in referenced["documents"])
            text += "\n" + "\n".join(notice["text"] for notice in referenced["observation"]["notices"])
            if not any(offer["id"] in text for offer in referenced["offers"]):
                packed.pop("offers")
                packed["runtime_offer_fields"] = sorted({key for quote in referenced["offers"] for key in quote})
                instructions += ("\nActual quotes are evaluated later by Python. Infer rules only from "
                                 "the linked authority, never from a ticket price or arrival. The "
                                 "runtime supplies candidate and live offers for conditional calculations.")
        documents = pack_initial_documents(packed["documents"])
        packed = dict(packed, documents=documents)
        if isinstance(documents, dict):
            instructions += "\nDocuments keyed by ID: [version, title, full text, ...links]."
        if "offers" in packed:
            instructions += "\nFor tabular offers, each row inherits shared fields, then the ordered columns. "
        if not defer:
            instructions += "Refund assignment keys are zero-based offer row indices. "
        if policy_clocks:
            instructions += "Use clock() only for these observed spending or client-arrival clocks: " + ", ".join(policy_clocks) + "."
        else:
            instructions += "Express any deadline in clock minutes or a dynamic rule; there is no known clock() label."
        offers = referenced["offers"]
        facts = deepcopy(full["properties"]["facts"])
        notices = viewed["observation"]["notices"]
        approvals = sorted({token for notice in notices for token in re.findall(r"\[CONSENT_REF_\d+\]", notice["text"])})
        if approvals:
            facts["properties"]["consent"]["enum"] = [*approvals, ""]
        string = {"type": "string"}
        use_literals = local_settings["model"] == "gpt-5-nano"
        limit = {"anyOf": [{"type": "number"}, string]} if use_literals else string
        props = dict(b=limit, a=limit, facts=facts)
        if use_literals:
            transfer = facts["properties"]["transfer"]
            facts["properties"]["transfer"] = {"anyOf": [{"type": "number"}, transfer]}
            instructions += ("\nRead the transport guide for transfers. If all modes take the same "
                             "transfer time, output that single number in facts.transfer. Use a "
                             "complete mode map for distinct times. Apply the guide to every mode, "
                             "including modes without current offers.")
            instructions += ("\nFor a simple ceiling give a number in b. For a stated client clock "
                             "give its exact HH:MM string in a. For a conditional or derived rule "
                             "return a Python expression. b is total authorized dollars, not a test.")
            bulletin = next((doc for doc in viewed["documents"] if doc["id"] == "hotel-bulletin"), None)
            if bulletin:
                waiver = facts["properties"]["waiver"]["properties"]
                proof = set(re.findall(r"\bproof-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b", bulletin["text"]))
                topic = set(re.findall(r"\b[A-Za-z]+(?:[-_][A-Za-z0-9]+)+\b", bulletin["text"])) - proof
                for key, values in (("topic", topic), ("code", proof)):
                    if len(values) == 1:
                        waiver[key]["enum"] = sorted(values)
        if not defer:
            props.update(rules=dict(type="array", minItems=1, items=string),
                         r=object_schema({str(i): dict(type="integer", minimum=0, maximum=len(offers)-1)
                                          for i in range(len(offers))}))
        shape = object_schema(props)
        stage = "booking_only" if defer else "cited_infix"
        raw = api.json(local_settings, instructions, packed, shape, dict(call_label, stage=stage))
        if use_literals and type(raw["facts"]["transfer"]) in (int, float):
            raw["facts"]["transfer"] = dict.fromkeys(("flight", "train", "coach"), raw["facts"]["transfer"])
        if defer:
            refund_groups = [dict(offer_ids=[offer["id"] for offer in offers], retained=None)]
        else:
            grouped = defaultdict(list)
            for i, offer in enumerate(offers):
                group = raw["r"][str(i)]
                if group >= len(raw["rules"]):
                    raise ValueError("Missing refund expression")
                grouped[group].append(offer["id"])
            refund_groups = [dict(offer_ids=ids, retained=decode_infix(raw["rules"][index]))
                             for index, ids in grouped.items()]
        if use_literals:
            ref = viewed["observation"]["operational_sources"]["budget_limit"]
            spending = next((doc["text"] for doc in viewed["documents"]
                             if doc["id"] == ref["id"] and doc["version"] == ref["version"]), "")
            if isinstance(raw["b"], str) and raw["b"].strip() in policy_clocks:
                raise ValueError("A budget is expressed in dollars")
            budget = decode_grounded_limit(raw["b"], policy_clocks, spending)
            arrival = decode_grounded_limit(raw["a"], clocks)
        else:
            budget = decode_infix(raw["b"], policy_clocks)
            arrival = decode_infix(raw["a"], clocks)
        response = dict(budget_limit=budget, arrival_deadline=client_deadline_value(arrival),
                        refund_groups=refund_groups, facts=raw["facts"])
        return restore_offer_references(response, aliases) if aliases else response

    instructions = INFIX_INSTRUCTIONS
    viewed = payload
    if defer:
        start, end = instructions.index("Output rules as distinct"), instructions.index("Copy consent")
        instructions = instructions[:start] + instructions[end:]
        authority_ids = {ref["id"] for ref in payload["observation"]["operational_sources"].values()}
        fare_ids = {offer["refund_contract_source"]["id"] for offer in payload["offers"]}
        linked = {identifier for doc in payload["documents"] for identifier in doc["related"]}
        viewed = dict(payload, documents=[doc for doc in payload["documents"]
                     if doc["id"] not in fare_ids - authority_ids - linked or doc["related"]])
    response = interpret_with_consent_references(
        SimpleNamespace(json=request), settings, instructions, viewed, base_schema, label)
    facts = response["facts"]
    if defer and settings["model"] == "gpt-5-nano":
        sources = "\n".join(doc["text"] for doc in viewed["documents"])
        sources += "\n" + "\n".join(n["text"] for n in viewed["observation"]["notices"])
        if any(not carrier or not re.search(r"(?<![\w-])" + re.escape(carrier) + r"(?![\w-])", sources,
                                           re.IGNORECASE) for carrier in facts["avoid_carriers"]):
            raise ValueError("Carrier exclusion lacks observed text")
    facts["forecasts"] = [value for value in facts["forecasts"]
                         if value["at"] is not None or value["probability"] is not None or value["delay"] not in (0, None)]
    bulletin = next((doc for doc in payload["documents"] if doc["id"] == "hotel-bulletin"), None)
    proof = facts["waiver"]
    if bulletin and (proof["version"] != bulletin["version"] or any(
            not proof[key] or not re.search(r"(?<![\w-])" + re.escape(proof[key]) + r"(?![\w-])", bulletin["text"])
            for key in ("code", "topic"))):
        raise ValueError("Unverified waiver proof")
    if not facts["consent"] or not any(re.search(r"(?<![\w-])" + re.escape(facts["consent"]) + r"(?![\w-])", n["text"])
                                      for n in payload["observation"]["notices"]):
        raise ValueError("Unverified initial consent")
    normalize_response(response, payload["offers"])
    if collapses_observed_budget(response, payload):
        raise ValueError("Check distinct amounts before choosing a constant ceiling")
    return response


def review_unanchored_transfer(api, settings, payload, compiled, label):
    guide = next((doc for doc in payload["documents"] if doc["id"] == "transport-guide"), None)
    if guide is None:
        return compiled
    claimed = compiled["facts"]["transfer"]
    known = {int(value) for value in re.findall(r"\b(\d+)\s+minutes?\b", guide["text"])}
    if not known or set(claimed.values()) <= known:
        return compiled
    modes = ("flight", "train", "coach")
    shape = object_schema(dict.fromkeys(modes, {"type": "number"}))
    instructions = ("Read the current guide and return terminal-to-client transfer minutes for all modes. "
                    "Apply the same number to each mode when the guide gives a shared transfer. Keep "
                    "separate durations only when differentiated by the observed guide or request. "
                    "No transfer is zero. Neither quote arrival times nor travel duration are transfers.")
    answer = api.json(settings, instructions,
                      dict(guide=guide["text"], notices=payload["observation"]["notices"], draft=claimed),
                      shape, dict(label, stage="transfer_review"))
    revised = dict(compiled, facts=dict(compiled["facts"], transfer=answer))
    normalize_response(revised, payload["offers"])
    return revised


def uses_ledger_in_ceiling(expression):
    if isinstance(expression, list):
        return any(uses_ledger_in_ceiling(child) for child in expression)
    if not isinstance(expression, dict):
        return False
    if "var" in expression:
        return expression["var"] in {
            "state.net_spend", "state.retained_fees", "state.hotel_fee", "state.total_refunds",
            "state.uncredited_hold_deposits", "state.retained_hold_fees", "state.total_retained_loss",
        }
    if expression.get("op") == "if":
        return any(uses_ledger_in_ceiling(expression[key]) for key in ("then", "else"))
    if expression.get("op") == "minimum":
        return uses_ledger_in_ceiling(expression["value"])
    return any(uses_ledger_in_ceiling(child) for child in expression.values())


def review_planning_rules(api, settings, payload, response, controller, label, *, verify_literals=False):
    """Audit draft feasibility without advancing simulator time, then review selected slots."""
    observation = deepcopy(payload["observation"])
    if observation["hotel_fee"]:
        observation["hotel_fee"] = 0
        observation["virtual_minute"] += FP_TOOL_DURATIONS["claim"]
    original = controller.program
    controller.program = normalize_response(response, payload["offers"])
    try:
        viable = controller.choose_plan(observation, controller.active(observation)) is not None
    finally:
        controller.program = original
    budgets_need_review = uses_ledger_in_ceiling(response["budget_limit"])
    clocks = observed_clocks(payload)
    deadline = response["arrival_deadline"]
    deadlines_need_review = False
    if verify_literals:
        budget = response["budget_limit"]
        budgets_need_review |= type(budget) in (int, float) and budget not in written_ceiling_values(payload)
        deadlines_need_review = type(deadline) in (int, float) and deadline not in clocks.values()
    if type(deadline) in (int, float) and deadline not in clocks.values() and any(
            clock - transfer == deadline for clock in clocks.values() for transfer in response["facts"]["transfer"].values()):
        deadlines_need_review = True
    fields = [key for key, detect in (("budget_limit", budgets_need_review),
                                      ("arrival_deadline", deadlines_need_review)) if detect]
    if not viable and not fields:
        fields = ["budget_limit", "arrival_deadline"]
    if not fields:
        return response
    authority = observation["operational_sources"]
    documents = {key: next(doc["text"] for doc in payload["documents"] if
                           (doc["id"], doc["version"]) == (authority[key]["id"], authority[key]["version"]))
                 for key in fields}
    evidence = dict(documents=documents, draft={key: response[key] for key in fields},
                    transfer=response["facts"]["transfer"],
                    candidates=[{key: offer[key] for key in ("id", "mode", "carrier", "price", "arrival_minute", "step_free")}
                                for offer in payload["offers"]])
    if "arrival_deadline" in fields:
        evidence["clock_minutes"] = clocks
    shape = object_schema(dict.fromkeys(fields, {"type": "string"}))
    instructions = """Audit only the requested rules against their linked text before booking. Keep draft values if supported.
Return Python expression strings: numeric literals, dotted variables, +/-, min(), max(), comparisons and Python conditional expressions. For quote-based rules use exists("offers", condition) and minimum("offers", condition, value, default); item denotes the quote inside these functions.
For the spending rule return the TOTAL ceiling. Check the original authorization before keeping any arithmetic from the draft. The planner already counts retained costs, actual refunds, and all payments. Use an arithmetic adjustment only when the authority defines that formula for the ceiling itself. Keep mode and carrier conditions on candidate (the proposed ticket).
For the arrival rule preserve every binding conditional concession and return the client clock, with no transfer subtracted. An unrelated appointment is not a deadline. Use clock("HH:MM") for supported explicit clock labels. For each conditional rule retain the default value and put the full condition on its exception."""
    review = api.json(settings, instructions, evidence, shape, dict(label, stage="scoped_rule_review"))
    repaired = dict(response, **{key: decode_infix(review[key], clocks if key == "arrival_deadline" else None)
                                for key in fields})
    normalize_response(repaired, payload["offers"])
    return repaired


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
        limit = {"$ref": "#/$defs/limit"}
        shape["$defs"]["limit"] = {"anyOf": [
            {"type": "number"},
            object_schema({"var": enum(NUMBER_VARIABLES)}),
            object_schema({"op": enum(("if",)), "when": expr, "then": limit, "else": limit}),
            object_schema({"op": enum(("add", "sub", "min", "max")),
                           "args": {"type": "array", "items": limit, "minItems": 1}}),
            object_schema({"op": enum(("minimum",)), "pool": enum(("offers", "holds")),
                           "where": expr, "value": limit, "default": {"type": "number"}}),
        ]}
        props["budget_limit"] = limit
        clocks = observed_clocks(viewed)
        props["arrival_deadline"] = limit
        if clocks:
            props["arrival_deadline"] = {"anyOf": [object_schema({"clock": enum(clocks)}), limit]}
            text += ("\nFor a single explicit client deadline, cite its exact clock string in a clock "
                     "object. Payment and route checks use the original client deadline. For "
                     "conditional or derived deadlines preserve the full numeric expression.")
        props["refund_groups"]["items"]["properties"]["retained"] = expr
        visible = dict(viewed, offers=[{key: value for key, value in offer.items()
                                      if key not in {"observed_at", "fare_fields_scope"}}
                                     for offer in viewed["offers"]])
        referenced, shape, references = offer_references(visible, shape)
        # Constrain exact observed spellings when the hotel source uniquely exposes them.
        bulletin = next((doc for doc in referenced["documents"] if doc["id"] == "hotel-bulletin"), None)
        if bulletin:
            waiver = shape["properties"]["facts"]["properties"]["waiver"]["properties"]
            proof = set(re.findall(r"\bproof-[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b", bulletin["text"]))
            topic = set(re.findall(r"\b[A-Za-z]+(?:[-_][A-Za-z0-9]+)+\b", bulletin["text"])) - proof
            for key, values in (("topic", topic), ("code", proof)):
                if len(values) == 1:
                    waiver[key]["enum"] = [next(iter(values)), ""]
        packed = pack_observed_packet(referenced)
        documents = pack_initial_documents(packed["documents"])
        if isinstance(documents, dict):
            packed = dict(packed, documents=documents)
            text += "\nDocuments keyed by source ID: [version, title, full text, ...related source IDs]."
        if isinstance(packed["offers"], dict):
            text += ("\nOffers are a table. Each row inherits all shared fields and adds the values "
                     "listed in columns in order. An absent marker means the field was missing.")
        if references:
            text += "\nUse the observed @O#@ offer references verbatim when returning an offer ID."
        response = api.json(local_settings, text, packed, shape, dict(request_label, stage="packed_evidence"))
        if clocks:
            deadline = restore_deadline(response["arrival_deadline"], clocks)
            transfers = response["facts"]["transfer"].values()
            if type(deadline) in (int, float) and deadline not in clocks.values() and any(
                    clock - minutes == deadline for clock in clocks.values() for minutes in transfers):
                raise ValueError("Check whether transfer was subtracted from the client deadline")
            response["arrival_deadline"] = deadline
        return restore_offer_references(response, references) if references else response

    response = interpret_with_consent_references(
        SimpleNamespace(json=request), settings, instructions, payload, schema, label,
    )
    normalize_response(response, payload["offers"])
    if collapses_observed_budget(response, payload):
        raise ValueError("Check distinct currency amounts before choosing a constant ceiling")
    return response


def interpret_amendment(api, settings, payload, previous_packet, schema, label, *, defer_fares=False):
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
    if defer_fares:
        changed_fares = {}
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
    if defer_fares:
        instructions += (
            "\nThe caller separately tracks purchase-time fare contracts. A provider fare amendment "
            "alone needs no changes to these fields and does not require a full interpretation. "
            "Still return changes to approval, eligibility, or the requested spending and arrival rules."
        )
        evidence["deferred_fare_versions"] = {
            identifier: docs[identifier]["version"] for identifier in sorted(changed_docs)
            if identifier in {ref["id"] for ref in fare_sources.values()} and identifier not in evidence_ids
        }
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
             else None if defer_fares else prior["refund_terms"][identifier]) for identifier in offers
    ])
    try:
        normalize_response(result, payload["offers"])
    except ValueError:
        return None
    return result


def weather_delta(api, settings, payload, previous_packet, schema, label, *, effort="none"):
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
    reply = api.json(dict(settings, effort=effort), instructions, dict(
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


def program_definitions():
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
    definitions = {"expression": {"anyOf": nodes}}
    limit = {"$ref": "#/$defs/limit"}
    definitions["limit"] = {"anyOf": [
        {"type": "number"},
        object_schema({"var": enum(NUMBER_VARIABLES)}),
        object_schema({"op": enum(("if",)), "when": expr, "then": limit, "else": limit}),
        object_schema({"op": enum(("add", "sub", "min", "max")),
                       "args": {"type": "array", "items": limit, "minItems": 1}}),
        object_schema({"op": enum(("minimum",)), "pool": enum(("offers", "holds")),
                       "where": expr, "value": limit, "default": {"type": "number"}}),
    ]}
    return definitions


def apply_base_retention(expression, base):
    if isinstance(expression, list):
        return [apply_base_retention(value, base) for value in expression]
    if not isinstance(expression, dict):
        return expression
    if expression == {"base_retention": True}:
        return base
    return {name: apply_base_retention(value, base) for name, value in expression.items()}


def compile_purchased_refund(api, settings, ticket, source, *, stage="purchased_fare"):
    public_quote = {key: value for key, value in ticket.items()
                    if key not in {"cancel_fee_usd", "fare_fields_scope"}}
    evidence = dict(ticket=public_quote, purchase_source=dict(version=source["version"], text=source["text"]))
    shape = object_schema({"retained": {"$ref": "#/$defs/expression"}})
    definition = program_definitions()["expression"]
    definition["anyOf"].append(object_schema({"base_retention": {"type": "boolean", "enum": [True]}}))
    shape["$defs"] = {"expression": definition}
    instructions = """Compile the purchase authority's rule for money RETAINED on cancellation of this quote.
A clause that returns every payment leaves 0 retained. A prohibition leaves null. A partial refund keeps the unreturned money.
Use the linked fare text as authority, including its explicit default. Use {"base_retention":true} only on a branch where the source delegates to ordinary terms or leaves the case uncovered. The planner will fill in that value. Read all clauses before choosing the most specific one for this quote's ID, mode or carrier.
Use the schema expressions; keep if conditions and their correct then/else amounts. state.now is the cancellation completion minute. state.weather.MODE is the actual delay.
For qualifying replacement holds use an exists expression over the live holds pool. item denotes the held replacement and does not inherit this purchased quote's carrier or mode. item.meeting_arrival includes transfer."""
    reply = api.json(settings, instructions, evidence, shape, dict(role="frozen_refund", stage=stage))
    policy = ticket.get("change_policy", "flexible")
    base = {"fee": ticket.get("cancel_fee_usd", 0), "flexible": 0, "locked": None}[policy]
    expression = apply_base_retention(reply["retained"], base)
    validate_expression(expression, result_kind="refund")
    return expression


def arrival_depends_on_recovery(value):
    stable = {"candidate.mode", "candidate.carrier", "candidate.price", "candidate.step_free",
              "candidate.arrival_minute", "candidate.meeting_arrival", "candidate.weather_exposed"}
    if isinstance(value, dict):
        if "var" in value:
            return value["var"] not in stable
        return "pool" in value or any(arrival_depends_on_recovery(child) for child in value.values())
    return isinstance(value, list) and any(arrival_depends_on_recovery(child) for child in value)


def depends_on_refund_amount(expression):
    if isinstance(expression, list):
        return any(depends_on_refund_amount(child) for child in expression)
    if not isinstance(expression, dict):
        return False
    if "var" in expression:
        return expression["var"] in {
            "state.net_spend", "state.retained_fees", "state.total_refunds", "state.total_retained_loss"
        }
    return any(depends_on_refund_amount(child) for child in expression.values())


class DeferredRefundController(ForecastController):
    def __init__(self, *args, compile_refund, **kwargs):
        super().__init__(*args, **kwargs)
        self.compile_refund = compile_refund
        self.defer_fares = False
        self.pending_refunds = {}
        self.reviewable_refunds = {}
        self.forecast_trial = None
        self.refund_obstacle = False

    def implement(self, plan, booking):
        success = super().implement(plan, booking)
        if not success or not (ticket := self.active(self.world.observe())):
            return success
        identifier = ticket["id"]
        evidence = self.booked_evidence[identifier]
        reference = evidence["purchased_source"]
        source = evidence["read_source"]
        offer = self.offers[ticket["option_id"]]
        if (source and source["version"] == reference["version"]
                and offer["refund_contract_source"] == reference):
            archived = (deepcopy(offer), deepcopy(source))
            if self.defer_fares:
                self.pending_refunds[identifier] = archived
                evidence["interpreted_version_matches"] = False
            elif evidence["interpreted_version_matches"]:
                self.reviewable_refunds[identifier] = archived
        return success

    def prepare(self, observation, booking):
        identifier = booking["id"]
        if identifier not in self.reviewable_refunds:
            return super().prepare(observation, booking)
        self.forecast_trial = identifier
        self.refund_obstacle = False
        try:
            wake = super().prepare(observation, booking)
        finally:
            self.forecast_trial = None
        if wake is not None or not self.refund_obstacle:
            return wake

        ticket, source = self.reviewable_refunds.pop(identifier)
        original = self.booked_programs[identifier]
        try:
            revised = self.compile_refund(ticket, source, stage="forecast_fare_review")
        except ValueError:
            self.trace.append(dict(kind="forecast_fare_review", option_id=ticket["id"], valid=False))
            return None
        self.booked_programs[identifier] = revised
        self.trace.append(dict(kind="forecast_fare_review", option_id=ticket["id"], original=deepcopy(original),
                               revised=deepcopy(revised), purchase_version=source["version"]))
        return super().prepare(observation, booking)

    def refresh(self, initial=False):
        super().refresh(initial)
        for identifier, (offer, source) in self.pending_refunds.items():
            self.booked_programs[identifier] = None
            evidence = self.booked_evidence[identifier]
            evidence.update(read_source=deepcopy(source), interpreted_version_matches=False)

    def choose_plan(self, observation, booking):
        if booking and booking["id"] in self.pending_refunds and self.keep_valid(observation, booking):
            preferred = self.facts["preferred"]
            contextual_deadline = arrival_depends_on_recovery(self.program["arrival_deadline"])
            if booking["mode"] == preferred or not any(
                    candidate["mode"] == preferred and candidate["id"] != booking["option_id"]
                    and (contextual_deadline or self.physically_usable(candidate, self.context(observation, candidate)))
                    for candidate in self.candidates(observation)):
                return None
        return super().choose_plan(observation, booking)

    def purchase_plan(self, observation, candidate, booking=None, *, weather=None, at=None, assume_hold=False):
        if booking and (archived := self.pending_refunds.get(booking["id"])):
            # Static arrival rules provide a safe necessary condition before interpreting a refund.
            if not arrival_depends_on_recovery(self.program["arrival_deadline"]):
                context = self.context(observation, candidate, at=at, weather=weather)
                if not self.physically_usable(candidate, context):
                    return None
            ticket, source = archived
            identifier = booking["id"]
            if not any(depends_on_refund_amount(self.program[key])
                       for key in ("budget_limit", "arrival_deadline")):
                # A full refund minimizes net spend; this trial cannot take any action.
                previous = self.booked_programs[identifier]
                self.booked_programs[identifier] = 0
                try:
                    feasible = super().purchase_plan(observation, candidate, booking,
                                                     weather=weather, at=at, assume_hold=assume_hold)
                finally:
                    self.booked_programs[identifier] = previous
                if feasible is None:
                    return None
            try:
                self.booked_programs[identifier] = self.compile_refund(ticket, source)
            except ValueError:
                self.trace.append(dict(kind="purchased_fare_invalid", option_id=ticket["id"]))
                self.booked_programs[identifier] = None
            else:
                self.booked_evidence[identifier]["interpreted_version_matches"] = True
            del self.pending_refunds[identifier]
        plan = super().purchase_plan(observation, candidate, booking, weather=weather, at=at,
                                      assume_hold=assume_hold)
        if (plan is None and booking and self.forecast_trial == booking["id"] and not self.refund_obstacle
                and weather is not None and at is not None):
            identifier = booking["id"]
            original = self.booked_programs[identifier]
            self.booked_programs[identifier] = 0
            try:
                optimistic = super().purchase_plan(observation, candidate, booking, weather=weather, at=at,
                                                    assume_hold=assume_hold)
            finally:
                self.booked_programs[identifier] = original
            self.refund_obstacle = optimistic is not None
        return plan


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
        try:
            response = weather_delta(api, settings, payload, previous_packet, schema, label)
        except json.JSONDecodeError:
            try:
                response = weather_delta(api, settings, payload, previous_packet, schema,
                                         dict(label, attempt="weather_json_retry"), effort=settings["effort"])
            except json.JSONDecodeError:
                response = None
        if response is None:
            response = interpret_amendment(api, settings, payload, previous_packet, schema, label,
                                           defer_fares=controller.defer_fares)
        previous_packet = payload
        if response is None and payload["previous"] is None:
            try:
                defer_fares = not any(doc["id"] == "weather-forecast" for doc in payload["documents"])
                use_nano = defer_fares and simple_literal_authorities(payload)
                first_settings = dict(settings, model="gpt-5-nano", effort="minimal") if use_nano else settings
                response = cited_infix_initial(api, first_settings, payload, schema, label, defer=defer_fares)
                if use_nano:
                    response = review_unanchored_transfer(api, settings, payload, response, label)
                response = review_planning_rules(api, settings, payload, response, controller, label,
                                                 verify_literals=use_nano)
                controller.defer_fares = defer_fares
            except ValueError:
                try:
                    response = compact_initial(api, settings, INITIAL_INSTRUCTIONS, payload, schema, label)
                except ValueError:
                    response = None
        if response is None:
            controller.defer_fares = False
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
    controller = DeferredRefundController(
        world, lambda payload: compile_contract(payload, gateway, config, (), traces), traces,
        compile_refund=lambda ticket, source, **kwargs: compile_purchased_refund(
            api, config["model_settings"], ticket, source, **kwargs),
        refresh_context=config["refresh_context"], max_decisions=config["max_decisions"],
        prepare=config.get("forecast_strategy", "precaution") != "cheapest",
    )
    controller.run()
    return dict(traces=traces, working_memory=dict(documents=controller.documents,
        compiled=controller.program, purchased_refund_terms=controller.booked_programs,
        purchased_refund_evidence=controller.booked_evidence),
        context=dict(architecture=config["architecture"],
                     source_versions={name: source["version"] for name, source in controller.documents.items()}))
