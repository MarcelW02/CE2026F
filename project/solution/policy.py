"""EDITABLE: routing, memory, planning and the agent interaction loop.

Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from framework.fp_agents import run_travel_agent as supplied_agent, travel_route
from framework.operational_expressions import validate_expression
import difflib
import json
import re


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


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*[A-Za-z0-9]")


def _tokens(text):
    return list(dict.fromkeys(t for t in _TOKEN.findall(text) if len(t) >= 5))


def _snap_code(value, text):
    """Snap a model-copied code to a literal token of the observed text.

    Models sometimes return a whole sentence, drop a prefix, or lose the last
    character of a long code. A value that already occurs literally is kept.
    Otherwise the closest observed token containing a digit is used. No code
    prefix or length is assumed.
    """
    if not isinstance(value, str):
        return value
    tokens = _tokens(text)
    if value in tokens:
        return value
    pieces = [t for t in _TOKEN.findall(value) if len(t) >= 5]
    for piece in pieces:                       # code inside a sentence
        if piece in tokens and any(c.isdigit() for c in piece):
            return piece
    digit_tokens = [t for t in tokens if any(c.isdigit() for c in t)]
    for piece in (pieces or [value.strip()]):
        contained = [t for t in digit_tokens if piece in t or t in piece]
        if contained:                           # prefix dropped / extra words
            return max(contained, key=len) if piece in max(contained, key=len) else min(contained, key=len)
        best = max(digit_tokens, key=lambda t: difflib.SequenceMatcher(None, piece, t).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, piece, best).ratio() >= 0.8:
            return best                         # a character was lost or changed
    return value


def _bulletin(payload):
    for doc in (payload or {}).get("documents", []) if isinstance(payload, dict) else []:
        if doc.get("id") == "hotel-bulletin":
            return doc
    return None


def _fix_waiver(waiver, payload, text):
    """Use the current observed bulletin for the evidence type, code and version."""
    doc = _bulletin(payload)
    if doc is None:
        waiver["code"] = _snap_code(waiver.get("code"), text)
        return
    body = doc.get("text", "")
    literal = set(_TOKEN.findall(body))
    topic = re.search(r"evidence type\s+([A-Za-z0-9_\-]*[A-Za-z0-9])", body)
    code = re.search(r"\bcode\s+([A-Za-z0-9_\-]*[A-Za-z0-9])", body)
    if topic and waiver.get("topic") not in literal:
        waiver["topic"] = topic.group(1)
    if code and waiver.get("code") not in literal:
        waiver["code"] = code.group(1)
    elif not code:
        waiver["code"] = _snap_code(waiver.get("code"), body)
    if isinstance(doc.get("version"), int):
        waiver["version"] = doc["version"]


def _unbind_item(expr, bound=False):
    """`item` exists only inside exists/minimum; outside it means the ticket itself."""
    if isinstance(expr, list):
        return [_unbind_item(e, bound) for e in expr]
    if not isinstance(expr, dict):
        return expr
    if set(expr) == {"var"} and isinstance(expr["var"], str):
        if not bound and expr["var"].startswith("item."):
            return {"var": "booking." + expr["var"][5:]}
        return expr
    quantifier = expr.get("op") in ("exists", "minimum")
    return {k: _unbind_item(v, bound or (quantifier and k in ("where", "value")))
            for k, v in expr.items()}


def _reply_problem(result, payload):
    """Same structural checks the framework applies later; None when acceptable."""
    try:
        for key in ("budget_limit", "arrival_deadline"):
            if key in result:
                validate_expression(result[key], result_kind="number")
        if "refund_groups" in result:
            for group in result["refund_groups"]:
                validate_expression(group["retained"], result_kind="refund")
            seen = [i for group in result["refund_groups"] for i in group["offer_ids"]]
            wanted = {offer["id"] for offer in payload.get("offers", [])}
            if len(seen) != len(set(seen)) or set(seen) != wanted:
                return "refund_groups must contain every observed offer ID exactly once"
    except ValueError as error:
        return str(error)
    return None


_REPORT = re.compile(
    r"Observed operating result at virtual minute (\d+): (flight|train|coach) delay (\d+) minutes\. "
    r"This resolves the forecast; sheltered services are unchanged\.")
_REPORT_NOTICE = re.compile(
    r"The final operating report confirms an actual (\d+)-minute delay to exposed (flight|train|coach) services\. "
    r"(?:Use this observed disruption when checking the existing booking\.|"
    r"The warned major disruption has not occurred; use this observed outcome when checking the existing booking\.) "
    r"Sheltered services retain their original arrival times\.")


def _weather_shortcut(payload, last):
    """Return the previous compiled contract with the realized delay filled in, without a model call.

    Only for a standalone operating report: exactly one new weather notice, every other
    source unchanged, the same offers, and both texts in the exact standard wording.
    Anything else returns None and goes to the model as before."""
    prev = payload.get("previous")
    if last is None or not prev or not isinstance(prev.get("facts"), dict):
        return None
    notices, earlier = payload["observation"]["notices"], last["observation"]["notices"]
    if len(notices) != len(earlier) + 1 or notices[:-1] != earlier or notices[-1]["kind"] != "weather_update":
        return None
    docs = {d["id"]: d for d in payload["documents"]}
    forecast = docs.pop("weather-forecast", None)
    before = {d["id"]: d for d in last["documents"]}
    old_forecast = before.pop("weather-forecast", None)
    if not forecast or not old_forecast or forecast["version"] <= old_forecast["version"] or docs != before:
        return None
    sources = payload["observation"].get("operational_sources")
    if not sources or sources != last["observation"].get("operational_sources") \
            or any(v.get("id") == "weather-forecast" for v in sources.values()):
        return None
    if {o["id"] for o in payload["offers"]} != set(prev["refund_terms"]) \
            or any((o.get("refund_contract_source") or {}).get("id") == "weather-forecast" for o in payload["offers"]):
        return None
    report, notice = _REPORT.fullmatch(forecast["text"]), _REPORT_NOTICE.fullmatch(notices[-1]["text"])
    if not report or not notice:
        return None
    minute, mode, delay = report.groups()
    if int(minute) != notices[-1]["at"] or notice.groups() != (delay, mode):
        return None
    facts = json.loads(json.dumps(prev["facts"]))
    facts["weather"][mode] = int(delay)
    facts["forecasts"] = [row for row in facts["forecasts"] if row.get("mode") != mode]
    return {"budget_limit": prev["budget_limit"], "arrival_deadline": prev["arrival_deadline"],
            "refund_groups": [{"offer_ids": [i], "retained": e} for i, e in prev["refund_terms"].items()],
            "facts": facts}


class _NormalizingAPI:
    """Pass-through to the supplied API (same accounting) that repairs known
    interpretation slips: sentence-valued or mis-copied codes, a wrong hotel
    evidence type, `item` used outside a quantifier. At most one extra repair
    request is made, and only when a reply is structurally invalid."""

    def __init__(self, api):
        self._api = api
        self._last = None

    def __getattr__(self, name):
        return getattr(self._api, name)

    def _call(self, *args, **kwargs):
        """Call the API; if the reply was not pure JSON (the model sometimes emits a
        stray text message before the real object), retry. The second retry uses
        reasoning effort low. Every attempt is made and counted by the supplied API."""
        for attempt in range(3):
            try:
                return self._api.json(*args, **kwargs)
            except json.JSONDecodeError:
                if attempt == 2:
                    raise
                if attempt == 1 and args and isinstance(args[0], dict) \
                        and args[0].get("effort") == "none":
                    args = (dict(args[0], effort="low"),) + tuple(args[1:])

    def json(self, *args, **kwargs):
        payload = args[2] if len(args) > 2 else kwargs.get("payload")
        last, self._last = self._last, payload
        if isinstance(payload, dict) and "observation" in payload:
            try:
                shortcut = _weather_shortcut(payload, last)
            except (KeyError, TypeError, ValueError):
                shortcut = None
            if shortcut is not None:
                return shortcut
        result = self._call(*args, **kwargs)
        if not isinstance(result, dict) or not isinstance(payload, dict):
            return result
        text = json.dumps(payload, ensure_ascii=False, default=str)
        facts = result.get("facts")
        if isinstance(facts, dict):
            if "consent" in facts:
                facts["consent"] = _snap_code(facts["consent"], text)
            if isinstance(facts.get("waiver"), dict):
                _fix_waiver(facts["waiver"], payload, text)
        for key in ("budget_limit", "arrival_deadline"):
            if key in result:
                result[key] = _unbind_item(result[key])
        for group in result.get("refund_groups", []):
            group["retained"] = _unbind_item(group["retained"])
        problem = _reply_problem(result, payload)
        if problem and len(args) >= 5:
            note = ("\nREPAIR: your previous reply was rejected: " + problem +
                    ". Return the complete corrected reply for the same schema.")
            retry = self._call(args[0], args[1] + note, *args[2:])
            if isinstance(retry, dict):
                if isinstance(retry.get("facts"), dict):
                    if "consent" in retry["facts"]:
                        retry["facts"]["consent"] = _snap_code(retry["facts"]["consent"], text)
                    if isinstance(retry["facts"].get("waiver"), dict):
                        _fix_waiver(retry["facts"]["waiver"], payload, text)
                for key in ("budget_limit", "arrival_deadline"):
                    if key in retry:
                        retry[key] = _unbind_item(retry[key])
                for group in retry.get("refund_groups", []):
                    group["retained"] = _unbind_item(group["retained"])
                if _reply_problem(retry, payload) is None:
                    return retry
        return result


def solve(world, api, config, route_fn):
    """Retain the supplied agent, or implement your own observed-information loop.

    The delegate already owns episode-local document, trip-state, routing and
    search caches. Replace this body for a custom memory format or update policy;
    keep helper functions/classes in this file and initialize memory inside solve.
    Return serializable traces, working_memory and context for inspection. Memory
    content is not a separate scoring criterion; actual outcomes are evaluated.
    """
    return supplied_agent(world, _NormalizingAPI(api) if api is not None else api, config, route_fn)