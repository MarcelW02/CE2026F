"""Validate and package five declarative cases and replayable tool witnesses.

Validation runs only the common simulator. Submitted JSON is never imported as
Python. Successful replay establishes a feasible trace, not prose equivalence
or whether a witness relied on information that was unavailable at the time.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import zipfile

from .fp_cases import FP_VERSION, fp_hash
from .fp_world import FP_TOOL_DURATIONS

PACK_SCHEMA = "travel-case-pack-v1"
WITNESS_SCHEMA = "travel-case-witness-v1"
TEAM_IDS = tuple(f"team{n}" for n in range(1, 7))
PACK_FILES = ("cases.json", "witnesses.json", "CASE_MANIFEST.json")
MAX_FILE_BYTES = 2_000_000
MAX_WITNESS_STEPS = 128
MAX_WITNESS_ACTIONS = 256
_TIERS = {
    "team1": ("basic", "basic", "reactive", "reactive", "forecast"),
    "team2": ("basic", "basic", "reactive", "reactive", "forecast"),
    "team3": ("basic", "basic", "reactive", "forecast", "forecast"),
    "team4": ("basic", "basic", "reactive", "forecast", "forecast"),
    "team5": ("basic", "reactive", "reactive", "forecast", "forecast"),
    "team6": ("basic", "reactive", "reactive", "forecast", "forecast"),
}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def team_slots(team_id):
    if team_id not in TEAM_IDS:
        raise ValueError("team_id must be team1 through team6.")
    return {f"{team_id}-{index}": tier for index, tier in enumerate(_TIERS[team_id], 1)}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON objects must not repeat a key: " + key)
        result[key] = value
    return result


def parse_json(data):
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Each case-pack file must be at most 2 MB.")
    def reject(value):
        raise ValueError("JSON must contain finite numbers, not " + value)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=reject)
        # JSON permits finite-looking exponents that overflow Python's float.
        canonical_bytes(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Invalid UTF-8 JSON: " + str(error)) from error


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Provide an ordinary JSON file: " + path.name)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Each case-pack file must be at most 2 MB.")
    return parse_json(path.read_bytes())


def witnesses_from_report(team_id, cases, report):
    """Extract matching recorded actions; write_pack validates and replays them."""
    if (not isinstance(report, dict) or report.get("version") != FP_VERSION
            or report.get("status") != "complete"):
        raise ValueError("Use a complete recorded run from the current project version.")
    if (not isinstance(cases, list) or len(cases) != 5
            or any(not isinstance(entry, dict) or not isinstance(entry.get("slot_id"), str)
                   for entry in cases)
            or {entry["slot_id"] for entry in cases} != set(team_slots(team_id))):
        raise ValueError("Provide exactly the five assigned {slot_id, case} entries.")
    result = report.get("result")
    if not isinstance(result, dict) or result.get("complete") is not True:
        raise ValueError("Use the results.json produced by a complete local case run.")
    rows = result.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("The recorded run has no valid episode rows.")
    declared = report.get("instance_fingerprints", {})
    if not isinstance(declared, dict):
        raise ValueError("The recorded run has invalid case fingerprints.")
    witnesses = {}
    for entry in cases:
        case = entry.get("case")
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise ValueError("Each slot needs a complete case object with a case ID.")
        identifier, fingerprint = case["case_id"], fp_hash(case)
        if declared and declared.get(identifier) != fingerprint:
            raise ValueError("The recorded run used different case content: " + identifier)
        candidates = [row for row in rows if row.get("case_id") == identifier
                      and row.get("case_fingerprint") == fingerprint and row.get("success") is True]
        if not candidates:
            raise ValueError("No successful episode matches this exact case: " + identifier)
        # A matching success supplies a feasibility witness, never a replacement
        # score or a selected performance estimate. Packaging replays the actions.
        actions = candidates[0].get("observed_action_sequence")
        if not isinstance(actions, list) or not actions:
            raise ValueError("The recorded episode lacks captured tool actions; rerun with the current framework.")
        witnesses[entry["slot_id"]] = {"steps": copy.deepcopy(actions), "expected_success": True}
    return {"schema_version": WITNESS_SCHEMA, "witnesses": witnesses}


def _resolve(value, results, saved):
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"} or not isinstance(value["$ref"], str):
                raise ValueError("A witness reference has exactly one string $ref field.")
            parts = value["$ref"].split(".")
            if not parts or any(not part for part in parts):
                raise ValueError("A witness reference must name an earlier tool result.")
            if parts[0] == "steps":
                current = results
            elif parts[0] in saved:
                current = saved[parts[0]]
            else:
                raise ValueError("Unknown witness result reference: " + parts[0])
            try:
                for part in parts[1:]:
                    if isinstance(current, list) and part.isdigit():
                        current = current[int(part)]
                    elif isinstance(current, dict):
                        current = current[part]
                    else:
                        raise KeyError(part)
            except (KeyError, IndexError) as error:
                raise ValueError("Witness reference is unavailable: " + value["$ref"]) from error
            return copy.deepcopy(current)
        return {key: _resolve(item, results, saved) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, results, saved) for item in value]
    return value


def _action(action):
    if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
        raise ValueError("Each witness action has tool and arguments fields only.")
    if action["tool"] not in FP_TOOL_DURATIONS or not isinstance(action["arguments"], dict):
        raise ValueError("Use a published tool and an arguments object in each witness action.")
    allowed = {"id", "code", "key", "version", "topic", "minutes"}
    if set(action["arguments"]) - allowed:
        raise ValueError("Witness actions contain an unsupported tool argument.")
    return action


def replay_witness(case, witness):
    """Replay JSON actions through ordinary public tools; do not trust a pass flag."""
    from .world_factory import validate_case, world_for_case
    validate_case(case)
    if not isinstance(witness, dict) or set(witness) - {"steps", "expected_success"}:
        raise ValueError("A witness contains steps and optional expected_success only.")
    if "expected_success" in witness and witness["expected_success"] is not True:
        raise ValueError("A submitted feasibility witness must expect complete success.")
    steps = witness.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_WITNESS_STEPS:
        raise ValueError("A witness needs 1 to 128 observable tool steps.")
    world = world_for_case(copy.deepcopy(case), concurrency=3)
    results, saved, actions = [], {}, 0
    for index, original in enumerate(steps):
        if not isinstance(original, dict):
            raise ValueError("Each witness step must be an object.")
        step = copy.deepcopy(original)
        name = step.pop("save_as", None)
        if name is not None and (not isinstance(name, str) or
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name) or name == "steps" or name in saved):
            raise ValueError("save_as must be a new short result name.")
        step = _resolve(step, results, saved)
        if step == {"observe": True}:
            result = world.observe()
        elif set(step) == {"batch"}:
            batch = step["batch"]
            if not isinstance(batch, list) or not 1 <= len(batch) <= 12:
                raise ValueError("Witness batches need 1 to 12 published actions.")
            actions += len(batch)
            if actions > MAX_WITNESS_ACTIONS:
                raise ValueError("A witness may contain at most 256 tool actions.")
            result = world.batch([_action(action) for action in batch])
        else:
            action = _action(step)
            actions += 1
            if actions > MAX_WITNESS_ACTIONS:
                raise ValueError("A witness may contain at most 256 tool actions.")
            result = world.call(action["tool"], **action["arguments"])
        results.append(copy.deepcopy(result))
        if name is not None:
            saved[name] = copy.deepcopy(result)
    assessment = world.evaluate()
    if assessment.get("success") is not True:
        raise ValueError("Witness replay did not achieve complete travel success; a claimed pass or no-op is insufficient.")
    return {"success": True, "steps": len(steps), "tool_actions": actions,
            "final_virtual_minute": world.now, "assessment": assessment}


def validate_pack(cases, witnesses, team_id, *, replay=True):
    from .world_factory import validate_case
    slots = team_slots(team_id)
    if not isinstance(cases, list) or len(cases) != 5:
        raise ValueError("cases.json must contain exactly five {slot_id, case} entries.")
    seen, ids, normalized = set(), set(), []
    for entry in cases:
        if not isinstance(entry, dict) or set(entry) != {"slot_id", "case"}:
            raise ValueError("Each case entry has slot_id and case fields only.")
        slot, case = entry["slot_id"], entry["case"]
        if not isinstance(slot, str) or slot not in slots or slot in seen:
            raise ValueError("Use each of your five assigned slots exactly once.")
        if not isinstance(case, dict) or case.get("version") != FP_VERSION or case.get("horizon") != 36:
            raise ValueError("Use the exact current project version and the 36-minute horizon.")
        if case.get("difficulty") != slots[slot]:
            raise ValueError("The case difficulty does not match its assigned slot: " + slot)
        if not isinstance(case.get("case_id"), str) or case["case_id"] in ids:
            raise ValueError("Five cases must have distinct, nonempty case IDs.")
        validate_case(case)
        seen.add(slot)
        ids.add(case["case_id"])
        normalized.append(copy.deepcopy(entry))
    normalized.sort(key=lambda item: item["slot_id"])
    if (not isinstance(witnesses, dict) or set(witnesses) != {"schema_version", "witnesses"}
            or witnesses.get("schema_version") != WITNESS_SCHEMA
            or not isinstance(witnesses.get("witnesses"), dict)
            or set(witnesses["witnesses"]) != set(slots)):
        raise ValueError("witnesses.json must use travel-case-witness-v1 and contain all five slot witnesses.")
    checks = {}
    if replay:
        for entry in normalized:
            checks[entry["slot_id"]] = replay_witness(entry["case"], witnesses["witnesses"][entry["slot_id"]])
    manifest = {"schema_version": PACK_SCHEMA, "project_version": FP_VERSION,
        "team_id": team_id, "horizon": 36, "case_count": 5,
        "content_hash": content_hash(normalized),
        "witnesses_hash": content_hash(witnesses),
        "slots": [{"slot_id": entry["slot_id"], "tier": slots[entry["slot_id"]],
                   "case_id": entry["case"]["case_id"], "case_hash": content_hash(entry["case"])}
                  for entry in normalized]}
    manifest["pack_hash"] = content_hash(manifest)
    return {"cases": normalized, "witnesses": copy.deepcopy(witnesses),
            "manifest": manifest, "witness_checks": checks}


def load_pack(path, *, team_id=None, replay=True):
    """Read an exact three-file ZIP or a directory; never extract or execute it."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Provide an ordinary case-pack file or directory.")
    if path.is_dir():
        data = {name: read_json(path / name) for name in PACK_FILES}
    elif path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if sorted(names) != sorted(PACK_FILES):
                raise ValueError("The case ZIP must contain only cases.json, witnesses.json and CASE_MANIFEST.json, once each.")
            data = {}
            for name in PACK_FILES:
                info = archive.getinfo(name)
                if info.file_size > MAX_FILE_BYTES or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise ValueError("Case ZIP entries must be bounded, unencrypted ordinary JSON files.")
                data[name] = parse_json(archive.read(info))
    else:
        raise ValueError("Provide a case-pack directory or the ZIP created by submit_cases.py.")
    manifest = data["CASE_MANIFEST.json"]
    if not isinstance(manifest, dict):
        raise ValueError("CASE_MANIFEST.json must be an object.")
    declared_team = manifest.get("team_id")
    if team_id is not None and declared_team != team_id:
        raise ValueError("This case pack belongs to a different team.")
    pack = validate_pack(data["cases.json"], data["witnesses.json"], declared_team, replay=replay)
    if manifest != pack["manifest"]:
        raise ValueError("The automatic case manifest does not match its exact case/witness content.")
    return pack


def write_pack(output, cases, witnesses, team_id):
    pack = validate_pack(cases, witnesses, team_id, replay=True)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Preserve the previous ZIP; choose a fresh output filename.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in (("cases.json", pack["cases"]), ("witnesses.json", pack["witnesses"]),
                            ("CASE_MANIFEST.json", pack["manifest"])):
            archive.writestr(name, canonical_bytes(value) + b"\n")
    return pack


def load_case_package(path, *, team_id=None, replay=True):
    pack = load_pack(path, team_id=team_id, replay=replay)
    return dict(pack, team_id=pack["manifest"]["team_id"],
                content_hash=pack["manifest"]["content_hash"],
                pack_hash=pack["manifest"]["pack_hash"])
