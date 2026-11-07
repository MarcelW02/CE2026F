"""Select published cases or load student-authored local diagnostic cases."""
import copy
import json
import math
from pathlib import Path

from .fp_cases import FP_DEV_CASES, FP_PUBLIC_CASES, FP_VERSION, FP_TIERS
from .world_factory import validate_case


def select_cases(split="dev", tier=None):
    if split not in ("dev", "public"):
        raise ValueError("Choose the dev or public split.")
    if tier is not None and tier not in FP_TIERS:
        raise ValueError("Choose basic, reactive or forecast difficulty.")
    cases = FP_DEV_CASES if split == "dev" else FP_PUBLIC_CASES
    return copy.deepcopy([case for case in cases if tier is None or case["difficulty"] == tier])


def case_catalog(cases):
    """Show initial requests and source titles, without future events or labels."""
    return [dict(case_id=case["case_id"], tier=case["difficulty"],
        initial_request=case["initial_request"], source_titles=[dict(id=source["id"], title=source["title"])
            for source in case["documents"].values() if source["id"] != "hotel-bulletin"])
        for case in cases]


def _reject_constant(value):
    raise ValueError("Local case JSON must use finite numbers.")


def _nonnegative(value, integer=False):
    return type(value) in ((int,) if integer else (int, float)) and math.isfinite(value) and value >= 0


def load_local_cases(path):
    """Validate complete local JSON cases before paid calls; meaning needs review."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object keys are not supported.")
            result[key] = value
        return result
    try:
        file = Path(path)
        if file.stat().st_size > 6000000:
            raise ValueError("A local case file may contain at most 6000000 bytes.")
        cases = json.loads(file.read_text(encoding="utf-8"), parse_constant=_reject_constant,
                           object_pairs_hook=unique_object)
    except (OSError, ValueError, RecursionError) as error:
        raise ValueError("Could not read local cases as JSON: " + str(error)) from error
    if not isinstance(cases, list) or not 1 <= len(cases) <= 60:
        raise ValueError("Local cases must be a JSON list containing 1 to 60 complete cases.")
    wrapped = [isinstance(item, dict) and 'case' in item for item in cases]
    if any(wrapped):
        if not all(wrapped) or any(set(item) != {'slot_id', 'case'} for item in cases):
            raise ValueError("Use either raw cases or uniformly wrapped slot_id/case objects.")
        slots = [item['slot_id'] for item in cases]
        if any(not isinstance(slot, str) or not slot.strip() or len(slot) > 120 for slot in slots):
            raise ValueError("slot_id must be nonempty text of at most 120 characters.")
        if len(set(slots)) != len(slots):
            raise ValueError("slot_id must be unique within the file.")
        cases = [item['case'] for item in cases]
    seen = set()
    for index, case in enumerate(cases, 1):
        try:
            validate_case(case)
            if case["case_id"] in seen:
                raise ValueError("case_id must be unique within the file.")
            seen.add(case["case_id"])
        except (KeyError, TypeError, ValueError, RecursionError) as error:
            raise ValueError("Local case " + str(index) + ": " + str(error)) from error
    return cases
