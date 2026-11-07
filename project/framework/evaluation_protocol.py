"""Declared evaluation sizes and cache-neutral spending allowances."""
from .fp_cases import FP_VERSION, FP_SCORE_VERSION, FP_GRADING_COST_BASIS, travel_case_fingerprints

REPEATS = 2  # Public local development; official manifests declare their own repeats.
OFFICIAL_PUBLIC_REPEATS = 1
OFFICIAL_HIDDEN_REPEATS = 1
PUBLIC_CASE_COUNT = 30
CONTRIBUTED_CASE_COUNT = 30
INSTRUCTOR_HIDDEN_CASE_COUNT = 60
TOOL_SLOTS = 3
ALLOWANCE_PER_EPISODE_USD = 0.03851960 / 96
ALLOWANCE_KIND = "prorated_historical_per_episode"


def cost_allowance(cases, repeats=REPEATS):
    """Register a declared allowance; do not invent a new measured baseline."""
    if not cases or type(repeats) is not int or repeats < 1:
        raise ValueError("Register nonempty cases and a positive integer repeat count.")
    amount = len(cases) * repeats * ALLOWANCE_PER_EPISODE_USD
    return dict(version=FP_VERSION, scoring_version=FP_SCORE_VERSION,
        grading_cost_basis=FP_GRADING_COST_BASIS,
        allowance_kind=ALLOWANCE_KIND,
        allowance_per_episode_usd=ALLOWANCE_PER_EPISODE_USD,
        grading_usd=amount, estimated_usd=None,
        usage=dict(grading_usd=amount, estimated_usd=None),
        distinct_cases=len(cases), repeats=repeats, concurrency=TOOL_SLOTS,
        case_fingerprints=travel_case_fingerprints(cases),
        provenance="Declared scale inherited from USD 0.03851960 for 96 episodes; not a new API measurement.",
        historical_measurement=dict(version="travel-2026f-v8", episodes=96,
                                    estimated_usd=0.01655132, grading_usd=0.03851960))
