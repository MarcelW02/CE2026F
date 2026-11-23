"""TRUTH PLANNER - local case-validation tool only, never submitted.

The supplied framework planner, fed each case's ground-truth contract and facts instead of a model
interpretation. It makes no model calls. Used by tools/eval/case_gate.py to obtain a feasibility witness for
a newly authored case: if the supplied planner, given the true rules, reaches complete success, its observed
actions are replayed with the framework's replay_witness as the case's solvability proof.

It reads the case file named by the ORACLE_CASES environment variable (os.pathsep separates several files)
and looks the case up by the world's case ID, which a submitted solver must never do.
"""
import copy
import json
import os
from types import SimpleNamespace

from framework.fp_agents import run_travel_agent as supplied_agent, travel_route

MODES = ("flight", "train", "coach")


def load_cases():
    cases = {}
    for path in filter(None, os.environ.get("ORACLE_CASES", "").split(os.pathsep)):
        data = json.loads(open(path, encoding="utf-8").read())
        for entry in data:
            case = entry.get("case", entry)
            cases[case["case_id"]] = case
    return cases


def truth_at(case, minute, offer_ids):
    """The contract and facts that hold at a virtual minute, applying every event that has arrived."""
    contract = copy.deepcopy(case["operational_contract"])
    rules = dict(transfer=copy.deepcopy(case["transfer"]), preferred=case["preferred"],
                 requires_step_free=case["requires_step_free"], avoid_carriers=list(case["avoid_carriers"]),
                 waiver=case["waiver_type"], waiver_version=2)
    weather = dict.fromkeys(MODES, 0)
    forecasts = []
    for event in case["events"]:
        changes = event["changes"]
        if event["at"] <= minute:
            for key, value in changes.get("operational_contract", {}).items():
                if key == "refund_terms":
                    contract[key].update(copy.deepcopy(value))
                else:
                    contract[key] = copy.deepcopy(value)
            for key in ("transfer", "preferred", "requires_step_free", "avoid_carriers", "waiver", "waiver_version"):
                if key in changes:
                    rules[key] = copy.deepcopy(changes[key])
            weather.update(changes.get("weather_delays", {}))
        elif event["kind"] == "weather_update":
            forecasts += [dict(mode=mode, delay=delay, at=event["at"], probability=None)
                          for mode, delay in changes.get("weather_delays", {}).items()]
    return {
        "budget_limit": contract["budget_limit"],
        "arrival_deadline": contract["arrival_deadline"],
        "refund_groups": [{"offer_ids": [identifier], "retained": copy.deepcopy(contract["refund_terms"][identifier])}
                          for identifier in offer_ids],
        "facts": dict(consent=case["consent"], transfer=rules["transfer"], preferred=rules["preferred"],
                      requires_step_free=rules["requires_step_free"], avoid_carriers=rules["avoid_carriers"],
                      weather=weather, forecasts=forecasts,
                      waiver=dict(topic=rules["waiver"], code=case["waiver_code"], version=rules["waiver_version"])),
    }


def route(observation, memory):
    return travel_route(observation, memory)


def solve(world, api, config, route_fn):
    case = load_cases()[world.case_id]

    def interpret(settings, instructions, payload, schema, label):
        offer_ids = [offer["id"] for offer in payload["offers"]]
        return truth_at(case, payload["observation"]["virtual_minute"], offer_ids)

    return supplied_agent(world, SimpleNamespace(json=interpret), config, route_fn)
