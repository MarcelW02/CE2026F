"""EDITABLE: routing, memory, planning and the agent interaction loop.
 
Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from framework.fp_agents import run_travel_agent as supplied_agent, travel_route
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
 
 
def _bare_code(text, payload_text):
    """Reduce a code the model returned inside a sentence to the single literal token.
 
    Only observed text is used: the token must contain a digit (or a hyphen as a
    fallback) and is preferred when it literally occurs in the observed payload.
    No prefix or length is assumed. A value that is already one token is unchanged.
    """
    if not isinstance(text, str) or not re.search(r"\s", text.strip()):
        return text
    tokens = [t.strip(".,;:!?()[]\"'") for t in text.split()]
    tokens = [t for t in tokens if t]
    for test in (lambda t: any(c.isdigit() for c in t), lambda t: "-" in t):
        found = [t for t in tokens if test(t)]
        if found:
            seen = [t for t in found if t in payload_text]
            return (seen or found)[0]
    return text
 
 
class _NormalizingAPI:
    """Thin pass-through: same accounting, but fixes sentence-valued codes."""
 
    def __init__(self, api):
        self._api = api
 
    def __getattr__(self, name):
        return getattr(self._api, name)
 
    def json(self, *args, **kwargs):
        result = self._api.json(*args, **kwargs)
        payload = args[2] if len(args) > 2 else kwargs.get("payload")
        facts = result.get("facts") if isinstance(result, dict) else None
        if isinstance(facts, dict):
            text = json.dumps(payload, ensure_ascii=False, default=str)
            if "consent" in facts:
                facts["consent"] = _bare_code(facts["consent"], text)
            if isinstance(facts.get("waiver"), dict) and "code" in facts["waiver"]:
                facts["waiver"]["code"] = _bare_code(facts["waiver"]["code"], text)
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