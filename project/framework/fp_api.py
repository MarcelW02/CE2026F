"""Thread-safe paid requests with original inputs, outputs, and complete usage."""
import copy
import json
import math
import re
import threading
import time
from datetime import datetime, timezone

from .common import ResponseFailure, BudgetExceeded, object_schema, validate_json
from .settings import (PRICES, EFFORTS, CACHE_WRITE_PRICES, DECISION_PRICES,
                          STANDARD_INPUT_LIMIT, validate_settings)
from .fp_cases import fp_hash, FP_GRADING_COST_BASIS


class APISetupError(RuntimeError):
    """Local request preparation failed before an API request was submitted."""


def _input_token_count(text):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("o200k_base").encode(text))
    except Exception as exc:
        raise APISetupError("Could not prepare token accounting; resolve tokenizer setup before a new run.") from exc


def _tokens(value):
    return value if type(value) is int and value >= 0 else None


def _number(value, lower, upper):
    return (type(value) in (int, float) and math.isfinite(value)
            and lower <= value <= upper)


def _known_pricing(record):
    model = record.get("settings", {}).get("model")
    returned = record.get("returned_model")
    same_model = (returned in (None, model) or isinstance(returned, str) and isinstance(model, str)
                  and re.fullmatch(re.escape(model) + r"-\d{4}-\d{2}-\d{2}", returned) is not None)
    return (record.get("pricing_scope", "global_standard") == "global_standard"
            and same_model
            and record.get("service_tier") in (None, "default", "standard")
            and record.get("processing_region") in (None, "global"))


def grading_cost_from_record(record):
    """Price each endpoint without changing observed cache discounts.

    Historical rows without an endpoint are Responses requests. Decisions bills
    input only, so an unreported output counter does not make its price unknown.
    """
    if not isinstance(record, dict) or not isinstance(record.get("settings"), dict):
        return None
    model = record["settings"].get("model")
    if model not in PRICES or record.get("mode") == "fixture" or not _known_pricing(record):
        return None
    inputs = _tokens(record.get("input_tokens"))
    if inputs is None or inputs > STANDARD_INPUT_LIMIT:
        return None
    endpoint = record.get("endpoint", "responses")
    if endpoint == "decisions":
        return inputs * DECISION_PRICES[model] / 1e6 if model in DECISION_PRICES else None
    if endpoint != "responses":
        return None
    outputs = _tokens(record.get("output_tokens"))
    if outputs is None:
        return None
    try:
        cost = (inputs * PRICES[model][0] + outputs * PRICES[model][2]) / 1e6
        return cost if math.isfinite(cost) else None
    except OverflowError:
        return None


def _record_usage(row, usage):
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return
    row["usage"] = copy.deepcopy(usage)
    for key in ("input_tokens", "output_tokens"):
        row[key] = _tokens(usage.get(key))
    for target, details, source in (
        ("cached_tokens", "input_tokens_details", "cached_tokens"),
        ("cache_write_tokens", "input_tokens_details", "cache_write_tokens"),
        ("reasoning_tokens", "output_tokens_details", "reasoning_tokens"),
    ):
        info = usage.get(details)
        row[target] = _tokens(info.get(source)) if isinstance(info, dict) else None
    model = row["settings"]["model"]
    if row["endpoint"] == "decisions":
        row["estimated_usd"] = grading_cost_from_record(row)
    elif _known_pricing(row):
        it, ot = row["input_tokens"], row["output_tokens"]
        cached, written = row["cached_tokens"], row["cache_write_tokens"]
        if model not in CACHE_WRITE_PRICES:
            # Preserve the existing five-model accounting contract. Those
            # historical Responses schemas omitted zero-valued cache details.
            info = usage.get("input_tokens_details") or {}
            if isinstance(info, dict) and "cached_tokens" not in info:
                cached = row["cached_tokens"] = 0
            details = usage.get("output_tokens_details") or {}
            if isinstance(details, dict) and "reasoning_tokens" not in details:
                row["reasoning_tokens"] = 0
        required = (it, ot, cached, written) if model in CACHE_WRITE_PRICES else (it, ot, cached)
        if (all(value is not None for value in required) and it <= STANDARD_INPUT_LIMIT
                and cached <= it and (model not in CACHE_WRITE_PRICES or cached + written <= it)):
            rates = PRICES[model]
            ordinary = it - cached - (written if model in CACHE_WRITE_PRICES else 0)
            try:
                cost = (ordinary*rates[0] + cached*rates[1] + ot*rates[2]
                        + (written*CACHE_WRITE_PRICES[model] if model in CACHE_WRITE_PRICES else 0))/1e6
                row["estimated_usd"] = cost if math.isfinite(cost) else None
            except OverflowError:
                pass
    row["grading_usd"] = grading_cost_from_record(row)


def _decision_request(payload, questions, model):
    if model not in DECISION_PRICES:
        raise ValueError("Decisions supports only gpt-6-luna in this project.")
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if not text.strip():
        raise ValueError("Decisions input must not be empty.")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 400:
        raise ValueError("Supply between 1 and 400 named Decisions questions.")
    names = set()
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Each Decisions question must be a dictionary.")
        kind, name = question.get("type"), question.get("name")
        if kind not in ("choice", "predicate", "score"):
            raise ValueError("Decisions question type must be choice, predicate or score.")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Each Decisions question needs a unique nonempty name.")
        names.add(name)
        if not isinstance(question.get("instructions"), str) or not question["instructions"].strip():
            raise ValueError("Each Decisions question needs nonempty instructions.")
        allowed = {"name", "type", "instructions"}
        if kind == "choice":
            allowed.add("choices")
            options = question.get("choices")
            if not isinstance(options, list) or len(options) < 2:
                raise ValueError("A choice question needs at least two options.")
            values = []
            for option in options:
                if (not isinstance(option, dict) or set(option) - {"value", "description"}
                        or not isinstance(option.get("value"), str) or not option["value"].strip()
                        or ("description" in option and not isinstance(option["description"], str))):
                    raise ValueError("Choice options need nonempty string values and optional text descriptions.")
                values.append(option["value"])
            if len(values) != len(set(values)):
                raise ValueError("Choice option values must be distinct.")
        elif kind == "score":
            allowed.add("levels")
            levels = question.get("levels")
            if not isinstance(levels, list) or len(levels) < 2:
                raise ValueError("A score question needs at least two ordered levels.")
            for level in levels:
                if (not isinstance(level, dict) or set(level) - {"label", "description"}
                        or not isinstance(level.get("label"), str) or not level["label"].strip()
                        or ("description" in level and not isinstance(level["description"], str))):
                    raise ValueError("Score levels need nonempty labels and optional text descriptions.")
        if set(question) - allowed:
            raise ValueError("Unsupported Decisions question fields; Responses controls do not apply.")
    request = dict(model=model, input=text, questions=copy.deepcopy(questions))
    json.dumps(request, ensure_ascii=False, allow_nan=False)
    return request


def _decision_answers(raw, questions):
    answers = raw.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise ResponseFailure("Decisions did not return one answer per question.")
    expected, seen = {question["name"]: question for question in questions}, set()
    for answer in answers:
        if (not isinstance(answer, dict) or not isinstance(answer.get("name"), str)
                or answer["name"] not in expected or answer["name"] in seen):
            raise ResponseFailure("Decisions returned missing, repeated or unknown answer names.")
        seen.add(answer["name"])
        if answer.get("type") == "refusal":
            raise ResponseFailure("Decisions refused a question. No automatic retry or fallback will run.")
        question = expected[answer["name"]]
        kind = question["type"]
        if answer.get("type") != kind:
            raise ResponseFailure("Decisions returned the wrong answer type.")
        if kind == "predicate":
            if not _number(answer.get("probability"), 0, 1):
                raise ResponseFailure("Decisions returned an invalid predicate probability.")
            continue
        if not _number(answer.get("confidence"), 0, 1):
            raise ResponseFailure("Decisions returned invalid confidence.")
        values = ([option["value"] for option in question["choices"]] if kind == "choice"
                  else list(range(len(question["levels"]))))
        if kind == "choice" and answer.get("choice") not in values:
            raise ResponseFailure("Decisions selected an unknown choice value.")
        if kind == "score" and not _number(answer.get("score"), 0, len(values)-1):
            raise ResponseFailure("Decisions returned a score outside its supplied levels.")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, list) or len(probabilities) != len(values):
            raise ResponseFailure("Decisions returned an incomplete option distribution.")
        observed = []
        for probability in probabilities:
            value = probability.get("value") if isinstance(probability, dict) else None
            valid_value = (isinstance(value, str) if kind == "choice" else type(value) is int)
            if (not valid_value or value not in values
                    or not _number(probability.get("probability"), 0, 1)):
                raise ResponseFailure("Decisions returned an invalid option distribution.")
            observed.append(value)
        if len(set(observed)) != len(values):
            raise ResponseFailure("Decisions returned repeated option probabilities.")
        if not math.isclose(sum(item["probability"] for item in probabilities), 1, abs_tol=.001):
            raise ResponseFailure("Decisions option probabilities do not sum to one.")


class TravelAPI:
    mode = "actual_api"
    def __init__(self, client, max_calls=1000, max_usd=2.0):
        if type(max_calls) is not int or max_calls<1:
            raise ValueError("max_calls must be a positive integer.")
        if type(max_usd) not in (int,float) or not math.isfinite(max_usd) or max_usd<=0:
            raise ValueError("max_usd must be a finite positive estimate.")
        self.client = client
        self.max_calls = max_calls
        self.max_usd = max_usd
        self.records = []
        self._lock = threading.Lock()
        self._reserved_usd = 0.0
        self._submitted = 0

    def pending_requests(self):
        """Return submitted requests whose response/accounting is not yet saved."""
        with self._lock:
            return self._submitted - len(self.records)

    def snapshot_records(self, start_index=0):
        """Capture completed records and outstanding requests under one lock.

        A request finishing between separate record and pending-count reads must
        not disappear from both. Pending requests remain unknown-cost attempts.
        """
        with self._lock:
            return dict(records=copy.deepcopy(self.records[start_index:]),
                        pending_requests=self._submitted - len(self.records))

    def _reserve(self, reservation):
        with self._lock:
            spent = sum(r["estimated_usd"] or 0 for r in self.records)
            if any(r["estimated_usd"] is None for r in self.records):
                raise BudgetExceeded("A previous request has unknown cost. Inspect it before authorizing new spending.")
            if self._submitted >= self.max_calls or spent+self._reserved_usd+reservation > self.max_usd:
                raise BudgetExceeded("The explicit call or estimated-dollar guard would be exceeded.")
            self._submitted += 1
            self._reserved_usd += reservation
            return self._submitted

    def _finish(self, row, reservation, start):
        row["seconds"] = round(time.monotonic()-start, 4)
        with self._lock:
            self._reserved_usd -= reservation
            self.records.append(row)

    def _request_client(self, row):
        client = self.client
        if callable(getattr(client, "with_options", None)):
            client = client.with_options(max_retries=0)
        base_url = str(getattr(client, "base_url", "https://api.openai.com/v1/"))
        if base_url.rstrip("/") != "https://api.openai.com/v1":
            row["pricing_scope"] = "unverified_endpoint_or_region"
        return client

    def _row(self, endpoint, config, request, payload, label, **details):
        json.dumps(label, ensure_ascii=False, allow_nan=False)
        return dict(endpoint=endpoint, label=copy.deepcopy(label), mode=self.mode,
            settings=copy.deepcopy(config), request_hash=fp_hash(request), request=copy.deepcopy(request),
            observed_at=datetime.now(timezone.utc).isoformat(), payload=copy.deepcopy(payload),
            status="request_error", input_tokens=None, cached_tokens=None, cache_write_tokens=None,
            output_tokens=None, reasoning_tokens=None, estimated_usd=None, grading_usd=None,
            grading_cost_basis=FP_GRADING_COST_BASIS, raw_response=None,
            pricing_scope="global_standard", **details)

    def json(self, config, instructions, payload, schema, label):
        config = copy.deepcopy(config)
        validate_settings(config)
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        schema_text = json.dumps(schema, allow_nan=False)
        tokens = _input_token_count(instructions+text+schema_text)+1024
        p = PRICES[config["model"]]
        input_rate = max(p[0], CACHE_WRITE_PRICES.get(config["model"], p[0]))
        reservation = (tokens*input_rate+config["max_output_tokens"]*p[2])/1e6
        kwargs = dict(model=config["model"], instructions=instructions, input=text,
            max_output_tokens=config["max_output_tokens"], store=False, service_tier="default",
            text=dict(format=dict(type="json_schema", name="travel_decision", strict=True, schema=schema)))
        if EFFORTS[config["model"]]:
            kwargs["reasoning"] = dict(effort=config["effort"])
        if config["verbosity"] is not None:
            kwargs["text"]["verbosity"] = config["verbosity"]
        for k in ("temperature", "top_p"):
            if config[k] is not None:
                kwargs[k] = config[k]
        row = self._row("responses", config, kwargs, payload, label, instructions=instructions)
        row["request_number"] = self._reserve(reservation)
        start = time.monotonic()
        try:
            response = self._request_client(row).responses.create(**kwargs)
            row["raw_response"] = response.model_dump(mode="json")
            row["status"] = response.status
            row["response_id"] = getattr(response, "id", None)
            row["returned_model"] = getattr(response, "model", None)
            row["service_tier"] = getattr(response, "service_tier", None)
            row["processing_region"] = getattr(response, "processing_region", None)
            _record_usage(row, getattr(response, "usage", None))
            if response.status != "completed":
                raise ResponseFailure("The model response did not complete. No paid retry is automatic.")
            for item in row["raw_response"].get("output", []) or []:
                if isinstance(item, dict) and any(isinstance(content, dict) and content.get("type") == "refusal"
                        for content in item.get("content", []) or []):
                    row["status"] = "refusal"
                    raise ResponseFailure("The model refused the request. No paid retry is automatic.")
            parsed = validate_json(json.loads(response.output_text), schema)
            row["parsed"] = copy.deepcopy(parsed)
            return parsed
        except Exception as exc:
            # Exception messages can contain request details; record only the type.
            row["error_type"] = type(exc).__name__
            raise
        finally:
            self._finish(row, reservation, start)

    def decide(self, payload, questions, label, *, task=None, model="gpt-6-luna"):
        """Make one typed Decisions request in the shared guard and ledger.

        Non-string JSON data is serialized as input text. ``task`` is an optional
        local label, not a provider parameter or a memory/cache guarantee. Raw
        typed answers are returned; refusal/invalid answers retain charged usage
        and raise ResponseFailure without a retry or another endpoint fallback.
        """
        request = _decision_request(payload, questions, model)
        if task is not None and not isinstance(task, str):
            raise ValueError("Decisions task must be a string or None.")
        tokens = _input_token_count(json.dumps(request, ensure_ascii=False, allow_nan=False))+1024
        reservation = tokens*DECISION_PRICES[model]/1e6
        row = self._row("decisions", {"model": model}, request, payload, label, task=task)
        row["request_number"] = self._reserve(reservation)
        start = time.monotonic()
        try:
            client = self._request_client(row)
            resource = getattr(client, "decisions", None)
            if callable(getattr(resource, "create", None)):
                row["transport"] = "sdk_decisions"
                response = resource.create(**request)
            else:
                row["transport"] = "sdk_post"
                response = client.post("/decisions", cast_to=object, body=request)
            raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else copy.deepcopy(response)
            row["raw_response"] = copy.deepcopy(raw)
            row["status"] = "malformed_response"
            if not isinstance(raw, dict):
                raise ResponseFailure("Decisions returned a non-object response. No automatic fallback will run.")
            row["response_id"] = raw.get("id")
            row["returned_model"] = raw.get("model")
            row["service_tier"] = raw.get("service_tier")
            row["processing_region"] = raw.get("processing_region")
            _record_usage(row, raw.get("usage"))
            answers = raw.get("answers")
            if isinstance(answers, list) and any(isinstance(answer, dict) and answer.get("type") == "refusal" for answer in answers):
                row["status"] = "refusal"
            _decision_answers(raw, request["questions"])
            row["status"] = "completed"
            row["parsed"] = copy.deepcopy(raw["answers"])
            return raw
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            raise
        finally:
            self._finish(row, reservation, start)

    def usage(self, records=None):
        snapshot = self.snapshot_records() if records is None else dict(records=records, pending_requests=0)
        rows, pending = snapshot["records"], snapshot["pending_requests"]
        result = dict(mode=self.mode, calls=len(rows), grading_cost_basis=FP_GRADING_COST_BASIS)
        for key in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "estimated_usd"):
            result[key] = sum(r[key] for r in rows) if all(r.get(key) is not None for r in rows) else None
        result["actual_request_seconds"] = sum(r["seconds"] for r in rows)
        grading_costs = [grading_cost_from_record(row) for row in rows]
        result["grading_usd"] = sum(grading_costs) if all(cost is not None for cost in grading_costs) else None
        result["endpoint_counts"] = {endpoint: sum(row.get("endpoint", "responses") == endpoint for row in rows)
                                     for endpoint in sorted({row.get("endpoint", "responses") for row in rows})}
        result["pending_count"] = pending
        if pending:
            result["calls"] += pending
            for key in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens",
                        "estimated_usd", "grading_usd", "actual_request_seconds"):
                result[key] = None
        return result


class TravelFixtureAPI:
    """Offline control-flow checks only. These records never receive a model grade."""
    mode = "fixture"
    def __init__(self, responses):
        self.responses = iter(responses)
        self.records = []

    def json(self, config, instructions, payload, schema, label):
        result = next(self.responses)
        validate_json(result, schema)
        self.records.append(dict(endpoint="responses", label=label, settings=copy.deepcopy(config), mode=self.mode,
            payload=copy.deepcopy(payload), parsed=copy.deepcopy(result), status="fixture",
            input_tokens=None, cached_tokens=None, cache_write_tokens=None, output_tokens=None, reasoning_tokens=None,
            estimated_usd=None, grading_usd=None, grading_cost_basis=FP_GRADING_COST_BASIS, seconds=0))
        return result

    def decide(self, payload, questions, label, *, task=None, model="gpt-6-luna"):
        request = _decision_request(payload, questions, model)
        if task is not None and not isinstance(task, str):
            raise ValueError("Decisions task must be a string or None.")
        raw = next(self.responses)
        row = dict(endpoint="decisions", label=copy.deepcopy(label), settings={"model": model},
            mode=self.mode, payload=copy.deepcopy(payload), request=request, task=task,
            raw_response=copy.deepcopy(raw), status="fixture", input_tokens=None,
            cached_tokens=None, cache_write_tokens=None, output_tokens=None, reasoning_tokens=None,
            estimated_usd=None, grading_usd=None, grading_cost_basis=FP_GRADING_COST_BASIS, seconds=0)
        try:
            if not isinstance(raw, dict):
                raise ResponseFailure("The Decisions fixture must be a typed response dictionary.")
            _decision_answers(raw, request["questions"])
            row["parsed"] = copy.deepcopy(raw["answers"])
            return raw
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            raise
        finally:
            self.records.append(row)

    def usage(self, records=None):
        rows = self.records if records is None else records
        return dict(mode=self.mode, calls=len(rows), input_tokens=None, cached_tokens=None,
                    cache_write_tokens=None, output_tokens=None, reasoning_tokens=None, estimated_usd=None,
                    grading_usd=None, grading_cost_basis=FP_GRADING_COST_BASIS,
                    actual_request_seconds=0)
