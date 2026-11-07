"""Interpret observed travel prose as bounded expressions for local planning."""
import copy

from .operational_expressions import OFFER_FIELDS, STATE_FIELDS, validate_expression


NUMBER_FIELDS = {"price", "arrival_minute", "meeting_arrival", "available_from", "expires_at",
                 "cancel_fee_usd", "held_at", "confirmed_at", "hold_fee_usd"}
BOOLEAN_FIELDS = {"step_free", "weather_exposed"}
NUMBER_VARIABLES = sorted([root + "." + field for root in ("candidate", "booking", "item")
                           for field in NUMBER_FIELDS] + ["state." + field for field in STATE_FIELDS])
BOOLEAN_VARIABLES = sorted(root + "." + field for root in ("candidate", "booking", "item") for field in BOOLEAN_FIELDS)
STRING_VARIABLES = sorted(root + "." + field for root in ("candidate", "booking", "item")
                          for field in OFFER_FIELDS - NUMBER_FIELDS - BOOLEAN_FIELDS)


def _object(properties):
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def _enum(values):
    return dict(type="string", enum=list(values))


def make_schema(offers):
    """Strict, typed recursive AST; source evidence determines every numeric term.

    Numeric contract outputs cannot be Boolean conditions or JSON strings.
    Grouped identical refund terms avoid repeating large conditional expressions.
    """
    num = {"$ref": "#/$defs/number_expression"}
    pred = {"$ref": "#/$defs/predicate"}
    value = {"$ref": "#/$defs/value"}
    refund = {"$ref": "#/$defs/refund_expression"}
    numeric_nodes = [
        {"type": "number"}, _object({"var": _enum(NUMBER_VARIABLES)}),
        _object({"op": _enum(["add", "min", "max"]), "args": dict(type="array", items=num, minItems=1)}),
        _object({"op": _enum(["sub"]), "args": dict(type="array", items=num, minItems=2, maxItems=2)}),
        _object({"op": _enum(["if"]), "when": pred, "then": num, "else": num}),
        _object({"op": _enum(["minimum"]), "pool": _enum(["offers", "holds"]), "where": pred,
                 "value": num, "default": {"type": "number"}}),
    ]
    predicate_nodes = [
        {"type": "boolean"}, _object({"var": _enum(BOOLEAN_VARIABLES)}),
        _object({"op": _enum(["and", "or"]), "args": dict(type="array", items=pred, minItems=1)}),
        _object({"op": _enum(["not"]), "arg": pred}),
        _object({"op": _enum(["lt", "le", "gt", "ge"]), "left": num, "right": num}),
        _object({"op": _enum(["eq", "ne"]), "left": value, "right": value}),
        _object({"op": _enum(["in"]), "left": value, "right": dict(type="array", items=value)}),
        _object({"op": _enum(["exists"]), "pool": _enum(["offers", "holds"]), "where": pred}),
        _object({"op": _enum(["if"]), "when": pred, "then": pred, "else": pred}),
    ]
    modes = _object({mode: {"type": "number"} for mode in ("flight", "train", "coach")})
    nullable_number = {"type": ["number", "null"]}
    schema = _object({
        "budget_limit": num,
        "arrival_deadline": copy.deepcopy(num),
        "refund_groups": dict(type="array", minItems=1, items=_object({
            "offer_ids": dict(type="array", minItems=1, items=_enum(sorted(offer["id"] for offer in offers))),
            "retained": refund,
        })),
        "facts": _object({
            "consent": {"type": "string"}, "transfer": modes,
            "preferred": _enum(["flight", "train", "coach"]), "requires_step_free": {"type": "boolean"},
            "avoid_carriers": dict(type="array", items={"type": "string"}), "weather": copy.deepcopy(modes),
            "waiver": _object({"topic": {"type": "string"}, "code": {"type": "string"}, "version": {"type": "integer"}}),
            "forecasts": dict(type="array", items=_object({"mode": _enum(["flight", "train", "coach"]),
                "delay": nullable_number, "at": copy.deepcopy(nullable_number), "probability": copy.deepcopy(nullable_number)})),
        }),
    })
    schema["$defs"] = {
        "number_expression": {"anyOf": numeric_nodes},
        "predicate": {"anyOf": predicate_nodes},
        "value": {"anyOf": [num, pred, {"type": "string"}, {"type": "null"},
                              _object({"var": _enum(STRING_VARIABLES)}), dict(type="array", items=value),
                              # Value comparisons may select a string, such as a
                              # travel mode, while numeric outputs remain typed.
                              _object({"op": _enum(["if"]), "when": pred, "then": value, "else": value})]},
        "refund_expression": {"anyOf": [num, {"type": "null"},
            _object({"op": _enum(["if"]), "when": pred, "then": refund, "else": refund})]},
    }
    return schema

INSTRUCTIONS = """You compile currently observed travel contracts into the typed executable object required by the response schema. You do not grade, choose an offer, or infer future events. Return the structured object itself, not JSON inside a string. Interpret ordinary English scope, exceptions, amendments and inequalities exactly. Preserve unamended conditions. The current authoritative source versions supersede earlier text only for their stated scope. Base numeric change_policy/cancel_fee_usd are ordinary terms; conditional prose overrides them. A forecast is a possibility, never realized weather.

Output object keys:
budget_limit: expression for the applicable TOTAL spending ceiling in dollars (not a per-ticket price).
arrival_deadline: expression for the client's required MEETING arrival clock minute (HH:MM -> 60*HH+MM).
refund_groups: a list of {offer_ids:[...],retained:EXPR} groups. Include EVERY observed offer exactly once. Group offers only when their complete refund expressions are identical. retained returns RETAINED dollars, or null if cancellation is forbidden. Terms freeze at purchase; their conditions evaluate at cancellation completion. A hold is not a confirmed replacement. A previous normalized draft may instead map IDs in refund_terms; output the equivalent groups.
facts: {consent:string, transfer:{flight:number,train:number,coach:number}, preferred:'flight'|'train'|'coach', requires_step_free:boolean, avoid_carriers:[strings], weather:{flight:number,train:number,coach:number}, waiver:{topic:string,code:string,version:integer}, forecasts:[{mode:string,delay:number|null,at:number|null,probability:number|null}]}.
Transfer values add to terminal arrival. weather is realized mode delay only, zero before realization. forecasts contains explicitly announced possible weather delays. Its at is the virtual minute of the upcoming final operating report or uncertainty resolution, not the forecast's issue/revision time or a backup sales cutoff. Use null for an unstated report time, delay or probability. The waiver fields must describe the current hotel bulletin's actual evidence, not archived examples. Consent covers the lead outbound only. Ordinary access/carrier facts apply to the current trip.

CEILING EXAMPLE: 'Total spending, including retained charges and the hotel fee, is capped at USD 240' compiles to budget_limit:240. It does NOT compile to 240 minus current spending, minus retained charges, or minus the hotel fee. The planner already compares the TOTAL ledger expense with your returned ceiling. If an amendment replaces 240 with 260, return 260, not 500 or remaining credit. Only subtract a cost when the prose explicitly defines the ceiling itself that way. Conditions that grant different ceilings belong in the when of an if; its then/else are numeric ceilings. Distinguish a number the caller needs from a yes/no question the caller will calculate.

Expression language, exact forms:
JSON number/string/boolean/null or lists of expressions are literals.
{"var":"candidate.price"} accesses a public fact.
{"op":"if","when":EXPR,"then":EXPR,"else":EXPR}; if branches short-circuit.
{"op":"and"|"or","args":[EXPR,...]}; {"op":"not","arg":EXPR}.
{"op":"eq"|"ne"|"lt"|"le"|"gt"|"ge"|"in","left":EXPR,"right":EXPR}. 'in' requires a list on the right; ordering requires numbers.
{"op":"add"|"sub"|"min"|"max","args":[EXPR,...]}; sub takes exactly two operands.
{"op":"exists","pool":"holds"|"offers","where":EXPR}.
{"op":"minimum","pool":"holds"|"offers","where":EXPR,"value":EXPR,"default":NUMBER}.
Quantifiers bind item to each pool object. They do not change outer candidate/booking.
candidate/booking/item fields: id, option_id, price, mode, carrier, step_free, arrival_minute, meeting_arrival, available_from, expires_at, change_policy, cancel_fee_usd, weather_exposed, held_at, confirmed_at, status, hold_fee_usd.
state fields: now, net_spend, hotel_fee, retained_fees, total_refunds, uncredited_hold_deposits, retained_hold_fees, total_retained_loss, weather.flight, weather.train, weather.coach.
candidate is the proposed offer or hold at purchase and the active booking when checking arrival; booking is empty before purchase. At cancellation both are the cancelled booking. now is action COMPLETION minute. meeting_arrival is terminal arrival plus current transfer. Missing optional object fields are null. offers is current unheld on-sale inventory plus a candidate's valid held offer; holds is all live holds. State amounts are actual current ledger amounts; retained_fees means cancellation retention only. Quoted fare price already includes any reservation deposit credited when confirmed.

Do not encode a preferred/optimal offer ID, read case IDs as clues, guess hidden schedules, translate conditions into unexplained booleans, or return prose instead of expressions. Reference offer IDs only to map refund expressions to observed tickets. Keep every threshold and exception inside its proper conditional scope. For ordinary fee fares with no exceptions the refund expression is the numeric base retention; flexible is 0 and locked is null. Compile from source text, using previous interpretation only to preserve facts not amended by current evidence. All monetary ceilings are total spending, unless the prose explicitly compares prices inside a condition.
"""


def validate_compilation(result, offers):
    if not isinstance(result, dict) or not {"budget_limit", "arrival_deadline", "refund_terms", "facts"} <= set(result):
        raise ValueError("Compilation must contain the three contract programs and ordinary facts.")
    for key in ("budget_limit", "arrival_deadline"):
        if key in result:
            validate_expression(result[key], result_kind="number")
    identifiers = {offer["id"] for offer in offers}
    if set(result["refund_terms"]) != identifiers:
        raise ValueError("Compile refund terms for exactly the observed offer IDs.")
    for expression in result["refund_terms"].values():
        validate_expression(expression, result_kind="refund")
    facts = result["facts"]
    for key in ("consent", "transfer", "preferred", "requires_step_free", "avoid_carriers", "weather", "waiver", "forecasts"):
        if key not in facts:
            raise ValueError("Missing ordinary fact: " + key)
    if facts["preferred"] not in ("flight", "train", "coach") or type(facts["requires_step_free"]) is not bool:
        raise ValueError("Invalid preference or accessibility facts.")
    for key in ("transfer", "weather"):
        if set(facts[key]) != {"flight", "train", "coach"} or any(type(value) not in (int, float) or value < 0 for value in facts[key].values()):
            raise ValueError("Mode facts require nonnegative numeric values for all three modes.")
    return copy.deepcopy(result)


def normalize_response(response, offers):
    """Expand only model-returned groups; never infer missing terms or repair prose."""
    result = copy.deepcopy(response)
    refunds = {}
    for group in result.pop("refund_groups"):
        for identifier in group["offer_ids"]:
            if identifier in refunds:
                raise ValueError("An observed offer appears in more than one refund group.")
            refunds[identifier] = copy.deepcopy(group["retained"])
    result["refund_terms"] = refunds
    return validate_compilation(result, offers)



# These fields are language interpretation tasks, not extra agent requirements.
ROLE_FIELDS = {
    "traveler": ("budget_limit",),
    "transport": ("arrival_deadline", "refund_groups"),
    "hotel": (),
}
ROLE_FACTS = {
    "traveler": ("consent", "preferred", "requires_step_free", "avoid_carriers"),
    "transport": ("transfer", "weather", "forecasts"),
    "hotel": ("waiver",),
}


def _role_schema(full, role):
    properties = {key: copy.deepcopy(full["properties"][key]) for key in ROLE_FIELDS[role]}
    properties["facts"] = _object({key: copy.deepcopy(full["properties"]["facts"]["properties"][key])
                                  for key in ROLE_FACTS[role]})
    schema = _object(properties)
    schema["$defs"] = copy.deepcopy(full["$defs"])
    return schema


def role_source_ids(payload):
    """Use source links supplied by the world; body text cannot grant authority."""
    sources = payload["observation"]["operational_sources"]
    existing = {source["id"] for source in payload["documents"]}
    return {
        "traveler": ({sources["budget_limit"]["id"], "traveler-profile"} & existing),
        "transport": ({sources["arrival_deadline"]["id"], "transport-guide", "weather-forecast"}
                      | {offer["refund_contract_source"]["id"] for offer in payload["offers"]}) & existing,
        "hotel": {"hotel-terms", "hotel-bulletin"} & existing,
    }


def compile_contract(payload, api, config, domains, trace):
    """One combined call or optional scoped calls, all through the supplied ledger."""
    from concurrent.futures import ThreadPoolExecutor
    full = make_schema(payload["offers"])
    roles = list(dict.fromkeys(domains))
    split = (config["architecture"] == "hybrid_multi" and roles
             and len(roles) >= config["route_threshold"]
             and payload["observation"].get("tier") != "basic")
    if not split:
        response = api.json(config["model_settings"], INSTRUCTIONS + "\n" + config["prompt"],
                            payload, full, dict(role="combined_contract_interpreter"))
        trace.append(dict(kind="interpretation", role="combined", payload=copy.deepcopy(payload),
                          decision=copy.deepcopy(response)))
        return normalize_response(response, payload["offers"])
    source_ids = role_source_ids(payload)
    previous = payload.get("previous") or {}

    def interpret(role):
        scoped = dict(observation={key: copy.deepcopy(payload["observation"][key])
                                   for key in ("virtual_minute", "notices", "operational_sources")},
                      documents=[copy.deepcopy(source) for source in payload["documents"]
                                 if source["id"] in source_ids[role]],
                      offers=copy.deepcopy(payload["offers"]),
                      previous={key: copy.deepcopy(previous[key]) for key in ROLE_FIELDS[role] if key in previous})
        if role == "transport" and previous.get("refund_terms"):
            scoped["previous"]["refund_terms"] = copy.deepcopy(previous["refund_terms"])
        scoped["previous"]["facts"] = {key: copy.deepcopy(previous.get("facts", {}).get(key))
                                        for key in ROLE_FACTS[role] if key in previous.get("facts", {})}
        instructions = (INSTRUCTIONS + "\nYou interpret only the " + role + " scope. "
                        "Return only the fields in this request's schema. "
                        + config["extraction_prompts"][role] + "\n" + config["prompt"])
        response = api.json(config["model_settings"], instructions, scoped, _role_schema(full, role),
                            dict(role=role + "_contract_interpreter"))
        return dict(kind="interpretation", role=role, payload=scoped, decision=response)

    if config["concurrent_investigators"]:
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(interpret, roles))
    else:
        rows = [interpret(role) for role in roles]
    merged = copy.deepcopy(previous)
    merged.setdefault("facts", {})
    for row in rows:
        output = copy.deepcopy(row["decision"])
        merged["facts"].update(output.pop("facts"))
        merged.update(output)
    trace.extend(rows)
    if "refund_groups" in merged:
        return normalize_response(merged, payload["offers"])
    return validate_compilation(merged, payload["offers"])
