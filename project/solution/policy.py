"""EDITABLE: routing, memory, planning and the agent interaction loop.

Keep additional policy functions/classes here. Model calls use api.json/api.decide;
all actions must use the supplied world interface. Do not import the evaluator,
read future events, inspect _spec/_rules, or choose actions by case-ID lookup.
"""
from collections import defaultdict
from framework.contract_interpreter import compile_contract, normalize_response
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

    def interpret(settings, instructions, payload, schema, label):
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
