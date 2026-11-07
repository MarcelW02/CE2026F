"""Fresh-process episodes with a single accounted API ledger for a whole run.

Local evaluation and official evaluation use the same episode boundary. A policy
may retain memory within a trip; interpreter state never passes to the next trip.
This isolates ordinary process state, not adversarial code or external storage.
"""
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
import json
import multiprocessing as mp
from multiprocessing.managers import BaseManager
import os
from pathlib import Path
import tempfile
import threading
import time
from uuid import uuid4

from .fp_api import TravelAPI
from .fp_cases import FP_GRADING_COST_BASIS, fp_hash, travel_case_fingerprints
from .fp_evaluation import evaluate_travel, travel_outcome_summary, travel_tier_summary
from .runtime import EDITABLE_FILES, load_solution

EXECUTION_PROTOCOL = "isolated-episode-v1"
_PROCESS_OPERATIONS = threading.Lock()



class RemoteCallError(Exception):
    """Transport an error type without provider exception messages or secrets."""


def _remote_error(name):
    from .common import BudgetExceeded, ResponseFailure
    from .fp_api import APISetupError
    known = {cls.__name__: cls for cls in
             (BudgetExceeded, ResponseFailure, APISetupError, ValueError, TypeError, KeyError, RuntimeError)}
    message = "Accounted model request failed; inspect the saved request record."
    if name in known:
        return known[name](message)
    if name == "JSONDecodeError":
        return json.JSONDecodeError(message, "", 0)
    if name == "ValidationError":
        from jsonschema import ValidationError
        return ValidationError(message)
    import openai
    import httpx
    request = httpx.Request("POST", "https://api.openai.com/v1/")
    if name == "APITimeoutError":
        return openai.APITimeoutError(request=request)
    if name == "APIConnectionError":
        return openai.APIConnectionError(message=message, request=request)
    codes = {"AuthenticationError": 401, "PermissionDeniedError": 403,
             "RateLimitError": 429, "BadRequestError": 400,
             "NotFoundError": 404, "ConflictError": 409,
             "UnprocessableEntityError": 422, "InternalServerError": 500}
    if name in codes:
        return getattr(openai, name)(message, response=httpx.Response(codes[name], request=request), body=None)
    return type(name, (Exception,), {})(message)


class _APIService:
    def __init__(self, key, max_calls, max_usd):
        from openai import OpenAI
        self.api = TravelAPI(OpenAI(api_key=key, timeout=180.0, max_retries=0),
                             max_calls=max_calls, max_usd=max_usd)
        self.active = {}
        self.lock = threading.Lock()

    def invoke(self, token, method, args, kwargs):
        if method not in ("json", "decide"):
            raise ValueError("Unsupported model method.")
        args, kwargs = copy.deepcopy(args), copy.deepcopy(kwargs)
        position = 4 if method == "json" else 2
        if len(args) > position:
            args[position] = dict(args[position], execution_episode=token)
        else:
            kwargs["label"] = dict(kwargs["label"], execution_episode=token)
        with self.lock:
            self.active[token] = self.active.get(token, 0) + 1
        try:
            return getattr(self.api, method)(*args, **kwargs)
        except Exception as exc:
            raise RemoteCallError(type(exc).__name__) from None
        finally:
            with self.lock:
                self.active[token] -= 1

    def snapshot(self, token=None):
        with self.lock:
            snapshot = self.api.snapshot_records()
            if token is None:
                return snapshot
            return dict(records=[row for row in snapshot["records"]
                                 if row.get("label", {}).get("execution_episode") == token],
                        pending_requests=self.active.get(token, 0))

    def usage(self, records):
        return self.api.usage(records)


class _APIManager(BaseManager):
    pass


_APIManager.register("APIService", _APIService)


class _EpisodeAPI:
    mode = "actual_api"

    def __init__(self, service, token):
        self.service, self.token = service, token

    def _invoke(self, method, args, kwargs):
        try:
            return self.service.invoke(self.token, method, list(args), kwargs)
        except RemoteCallError as exc:
            # evaluate_travel uses the type to distinguish interruptions. Do not
            # expose the original provider exception message or API credentials.
            raise _remote_error(str(exc)) from None

    def json(self, *args, **kwargs):
        return self._invoke("json", args, kwargs)

    def decide(self, *args, **kwargs):
        return self._invoke("decide", args, kwargs)

    @property
    def records(self):
        return self.snapshot_records()["records"]

    def snapshot_records(self, start_index=0):
        value = self.service.snapshot(self.token)
        value["records"] = value["records"][start_index:]
        return value

    def pending_requests(self):
        return self.snapshot_records()["pending_requests"]

    def usage(self, records=None):
        return self.service.usage(self.records if records is None else records)


def _worker(connection, sources, config, case, repeat, service):
    """Run one case in this process, then discard its imported policy modules."""
    root = Path(__file__).resolve().parents[1] / ".runtime"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = tempfile.tempdir = str(root)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(root / "tiktoken"))
    try:
        with tempfile.TemporaryDirectory(prefix="episode-", dir=root) as temporary:
            directory = Path(temporary)
            for name in EDITABLE_FILES:
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(sources[name], encoding="utf-8")
            with load_solution(directory) as (loaded, route, solver, digest, _):
                if loaded != config:
                    raise ValueError("Configuration must resolve identically in every fresh episode.")
                api = _EpisodeAPI(service, uuid4().hex) if service is not None else None
                result = evaluate_travel([case], api, loaded, repeats=1, route_fn=route,
                                         solver_fn=solver, concurrency=3)
                result["rows"][0]["repeat"] = repeat
                result["policy_fingerprint"] = fp_hash(dict(sources=sources, config=config,
                                                              execution_protocol=EXECUTION_PROTOCOL))
                result["execution_protocol"] = EXECUTION_PROTOCOL
                result["worker_pid"] = os.getpid()
                connection.send(dict(result=result))
    except BaseException as exc:
        connection.send(dict(worker_error=type(exc).__name__))
    finally:
        connection.close()


def _launch(sources, config, case, repeat, service, timeout_seconds):
    context = mp.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, sources, config, case, repeat, service))
    # multiprocessing's global child cleanup and waitpid bookkeeping are not
    # coordinated between our launching threads. Serialize process operations.
    with _PROCESS_OPERATIONS:
        process.start()
    send.close()
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            if receive.poll(0.1):
                try:
                    value = receive.recv()
                except EOFError:
                    value = dict(worker_error="EpisodeWorkerExited")
                with _PROCESS_OPERATIONS:
                    process.join(timeout=5)
                    if process.is_alive():
                        value = dict(worker_error="EpisodeWorkerDidNotExit", partial=value)
                return value
            with _PROCESS_OPERATIONS:
                alive = process.is_alive()
            if not alive:
                # A worker can send its result between poll() and is_alive().
                if receive.poll(1):
                    try:
                        return receive.recv()
                    except EOFError:
                        pass
                return dict(worker_error="EpisodeWorkerExited")
        return dict(worker_error="EpisodeTimeout")
    finally:
        with _PROCESS_OPERATIONS:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        receive.close()


def aggregate_episode_results(cases, repeats, results, config, case_workers=1):
    """Combine episode rows and their request usage under one score protocol."""
    if not results:
        raise ValueError("No complete worker result is available.")
    result = copy.deepcopy(results[0])
    result.update(rows=[copy.deepcopy(row) for item in results for row in item["rows"]],
                  requests=[copy.deepcopy(row) for item in results for row in item["requests"]],
                  config=copy.deepcopy(config), case_fingerprints=travel_case_fingerprints(cases),
                  distinct_cases=len(cases), situations=len({case["family"] for case in cases}),
                  repeats=repeats, case_workers=case_workers,
                  execution_protocol=EXECUTION_PROTOCOL)
    result.pop("worker_pid", None)
    result["complete"] = len(results) == len(cases) * repeats and all(item["complete"] for item in results)
    result["status"] = "complete" if result["complete"] else "interrupted"
    result["pending_requests"] = sum(item.get("pending_requests", 0) for item in results)
    result["pending_observed_after_solver"] = max(item.get("pending_observed_after_solver", 0) for item in results)
    usage = dict(mode=result["mode"], grading_cost_basis=FP_GRADING_COST_BASIS)
    for name in ("calls", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens",
                 "reasoning_tokens", "estimated_usd", "grading_usd", "actual_request_seconds", "pending_count"):
        values = [item["usage"].get(name, 0 if name in ("cache_write_tokens", "pending_count") else None) for item in results]
        usage[name] = sum(values) if all(value is not None for value in values) else None
    endpoints = {name for item in results for name in item["usage"].get("endpoint_counts", {})}
    usage["endpoint_counts"] = {name: sum(item["usage"].get("endpoint_counts", {}).get(name, 0) for item in results) for name in endpoints}
    result["usage"] = usage
    result["recorded_episode_seconds"] = sum(item.get("wall_seconds", 0) for item in results)
    result["wall_seconds"] = result["recorded_episode_seconds"]
    result.update(travel_outcome_summary(result["rows"]))
    result["tiers"] = travel_tier_summary(result["rows"])
    return result


class IsolatedEvaluator(AbstractContextManager):
    """One shared guarded API service and a fresh worker for every episode."""
    def __init__(self, sources, config, key=None, *, case_workers=1, timeout_seconds=3600,
                 max_calls=1000, max_usd=2.0):
        if type(case_workers) is not int or case_workers < 1:
            raise ValueError("Choose a positive case_workers count.")
        self.sources, self.config = copy.deepcopy(sources), copy.deepcopy(config)
        self.key, self.case_workers, self.timeout_seconds = key, case_workers, timeout_seconds
        self.max_calls, self.max_usd = max_calls, max_usd
        self.manager = self.service = None
        self.failures = []

    def __enter__(self):
        root = Path(__file__).resolve().parents[1] / ".runtime"
        root.mkdir(parents=True, exist_ok=True)
        os.environ["TMPDIR"] = tempfile.tempdir = str(root)
        if self.config["architecture"] != "rules":
            if not self.key or self.key == "PASTE_YOUR_KEY_HERE":
                raise ValueError("Set the distributed OPENAI_API_KEY before a paid run.")
            os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(root / "tiktoken"))
            self.manager = _APIManager(address=("127.0.0.1", 0), ctx=mp.get_context("spawn"))
            self.manager.start()
            self.service = self.manager.APIService(self.key, self.max_calls, self.max_usd)
        return self

    def snapshot(self):
        if self.service is None:
            return dict(records=[], pending_requests=0)
        return self.service.snapshot()

    def execute(self, jobs, *, progress=None):
        """Execute each (case, repeat) job freshly; return completed worker results."""
        if any(type(repeat) is not int or repeat < 1 for _, repeat in jobs):
            raise ValueError("Use positive episode repeat numbers.")
        completed = {}
        def run(job):
            index, (case, repeat) = job
            return index, case, repeat, _launch(self.sources, self.config, case, repeat, self.service, self.timeout_seconds)
        with ThreadPoolExecutor(max_workers=self.case_workers) as executor:
            futures = {executor.submit(run, job): job for job in enumerate(jobs)}
            self.interrupted = False
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                index, case, repeat, value = future.result()
                if "worker_error" in value:
                    self.failures.append(dict(case_id=case["case_id"], repeat=repeat, **value))
                    self.interrupted = True
                else:
                    result = value["result"]
                    completed[index] = result
                    if progress:
                        progress(copy.deepcopy(result["rows"][0]))
                    if not result["complete"] or result["usage"].get("estimated_usd") is None:
                        self.interrupted = True
                if self.interrupted:
                    for other in futures:
                        other.cancel()
        return [completed[index] for index in sorted(completed)]

    def evaluate(self, cases, repeats=1, *, progress=None):
        """Run every requested case and repeat; each call makes fresh observations."""
        if type(repeats) is not int or repeats < 1 or not cases:
            raise ValueError("Provide cases and a positive repeat count.")
        started = time.monotonic()
        jobs = [(case, repeat) for repeat in range(1, repeats + 1) for case in cases]
        results = self.execute(jobs, progress=progress)
        if not results:
            raise RuntimeError("All episode workers failed; inspect retained request records.")
        result = aggregate_episode_results(cases, repeats, results, self.config, self.case_workers)
        result["wall_seconds"] = round(time.monotonic() - started, 3)
        if self.interrupted or self.failures or self.snapshot()["pending_requests"]:
            result["complete"], result["status"] = False, "interrupted"
            result["worker_failures"] = copy.deepcopy(self.failures)
        return result

    def __exit__(self, *exc):
        if self.manager is not None:
            self.manager.shutdown()
        return False
