"""Public, deterministic expression semantics; no case-specific programs or labels.

An interpreter may compile observed prose to this language and execute it locally.
The caller supplies facts it has obtained through ordinary world observations.
"""
import math

MAX_EXPRESSION_NODES = 128
MAX_EXPRESSION_DEPTH = 12
MAX_QUANTIFIER_DEPTH = 2
MAX_EVALUATION_STEPS = 50000


OFFER_FIELDS = frozenset((
    "id", "option_id", "price", "mode", "carrier", "step_free", "arrival_minute",
    "meeting_arrival", "available_from", "expires_at", "change_policy",
    "cancel_fee_usd", "weather_exposed", "held_at", "confirmed_at", "status", "hold_fee_usd",
))
STATE_FIELDS = frozenset((
    "now", "net_spend", "hotel_fee", "retained_fees", "total_refunds",
    "uncredited_hold_deposits", "retained_hold_fees", "total_retained_loss",
    "weather.flight", "weather.train", "weather.coach",
))
COMPARISONS = {"eq", "ne", "lt", "le", "gt", "ge", "in"}
ARITHMETIC = {"add", "sub", "min", "max"}


def _result_types(expr):
    """Check static operand kinds; optional facts may still be absent at runtime."""
    if expr is None: return {"null"}
    if type(expr) is bool: return {"boolean"}
    if type(expr) in (int, float): return {"number"}
    if isinstance(expr, str): return {"string"}
    if isinstance(expr, list):
        for item in expr: _result_types(item)
        return {"list"}
    if "var" in expr:
        field = expr["var"].partition(".")[2]
        return {"string" if field in ("id", "option_id", "mode", "carrier", "change_policy", "status")
                else "boolean" if field in ("step_free", "weather_exposed") else "number"}
    def expect(value, kind):
        if not _result_types(value) <= {kind}:
            raise ValueError("Expression operand types do not match their operator.")
    op = expr["op"]
    if op in ARITHMETIC or op in ("and", "or"):
        kind = "number" if op in ARITHMETIC else "boolean"
        for arg in expr["args"]: expect(arg, kind)
        return {kind}
    if op == "not": expect(expr["arg"], "boolean"); return {"boolean"}
    if op == "if":
        expect(expr["when"], "boolean")
        return _result_types(expr["then"]) | _result_types(expr["else"])
    if op in ("exists", "minimum"):
        expect(expr["where"], "boolean")
        if op == "exists": return {"boolean"}
        expect(expr["value"], "number"); expect(expr["default"], "number")
        return {"number"}
    if op in ("lt", "le", "gt", "ge"):
        expect(expr["left"], "number"); expect(expr["right"], "number")
    elif op == "in":
        _result_types(expr["left"]); expect(expr["right"], "list")
    else:
        _result_types(expr["left"]); _result_types(expr["right"])
    return {"boolean"}


def validate_expression(expr, depth=0, *, result_kind=None, _count=None, _quantifiers=0):
    """Reject malformed programs before running an episode, without grading prose."""
    _count = [0] if _count is None else _count
    _count[0] += 1
    if depth > MAX_EXPRESSION_DEPTH or _count[0] > MAX_EXPRESSION_NODES:
        raise ValueError("An expression may have at most 128 nodes and depth 12.")
    if depth == 0 and result_kind is not None:
        if result_kind not in ("number", "refund"):
            raise ValueError("Unknown expression result kind.")
        def check_result(value):
            if isinstance(value, dict) and value.get("op") == "if":
                check_result(value.get("then")); check_result(value.get("else")); return
            if value is None and result_kind == "refund": return
            if type(value) in (int, float): return
            if isinstance(value, dict):
                operator = value.get("op")
                if isinstance(operator, str) and (operator in ARITHMETIC or operator == "minimum"): return
                field = value.get("var", "").partition(".")[2] if isinstance(value.get("var", ""), str) else ""
                if field and field not in {"id", "option_id", "mode", "carrier", "change_policy", "status", "step_free", "weather_exposed"}: return
            raise ValueError("A numeric contract must return a number; only refunds may return null.")
        check_result(expr)
    if expr is None or type(expr) in (bool, str, int, float):
        if type(expr) in (int, float) and (not math.isfinite(expr) or abs(expr) > 1000000):
            raise ValueError("Numeric literals must be finite and within one million.")
        if isinstance(expr, str) and len(expr) > 200:
            raise ValueError("Expression strings have a 200-character limit.")
        return
    if isinstance(expr, list):
        for item in expr:
            validate_expression(item, depth + 1, _count=_count, _quantifiers=_quantifiers)
        return
    if not isinstance(expr, dict):
        raise ValueError("Expressions are JSON literals, lists, or operator objects.")
    if "var" in expr:
        if set(expr) != {"var"} or not isinstance(expr["var"], str):
            raise ValueError("A variable has exactly one string var field.")
        root, separator, field = expr["var"].partition(".")
        fields = STATE_FIELDS if root == "state" else OFFER_FIELDS
        if not separator or root not in ("state", "candidate", "booking", "item") or field not in fields:
            raise ValueError("Unsupported variable: " + expr["var"])
        if root == "item" and not _quantifiers:
            raise ValueError("item is available only inside a quantifier.")
        return
    op = expr.get("op")
    if not isinstance(op, str):
        raise ValueError("An expression needs a supported string operator.")
    if op in COMPARISONS:
        keys = {"op", "left", "right"}
    elif op in ARITHMETIC or op in ("and", "or"):
        keys = {"op", "args"}
        if not isinstance(expr.get("args"), list) or not expr["args"]:
            raise ValueError("args must be a nonempty list.")
        if op == "sub" and len(expr["args"]) != 2:
            raise ValueError("sub takes exactly two arguments.")
    elif op == "not":
        keys = {"op", "arg"}
    elif op == "if":
        keys = {"op", "when", "then", "else"}
    elif op in ("exists", "minimum"):
        if _quantifiers >= MAX_QUANTIFIER_DEPTH:
            raise ValueError("At most two nested quantifiers are supported.")
        keys = {"op", "pool", "where"}
        if op == "minimum":
            keys |= {"value", "default"}
        if expr.get("pool") not in ("offers", "holds"):
            raise ValueError("A pool must be offers or holds.")
    else:
        raise ValueError("Unsupported expression operator: " + str(op))
    if set(expr) != keys:
        raise ValueError("Unexpected or missing fields for operator " + op)
    for key, child in expr.items():
        if key not in ("op", "pool"):
            nested = _quantifiers + (op in ("exists", "minimum") and key in ("where", "value"))
            validate_expression(child, depth + 1, _count=_count, _quantifiers=nested)
    if depth == 0:
        _result_types(expr)


def evaluate_expression(expr, context, _budget=None):
    """Evaluate a validated program against supplied, current factual context.

    Boolean operators require booleans. Numeric operators reject booleans and
    nulls. Missing optional object fields evaluate to null; unknown fields are
    rejected by validation. `if`, `and`, and `or` short-circuit.
    """
    if _budget is None:
        validate_expression(expr)
        _budget = [MAX_EVALUATION_STEPS]
    _budget[0] -= 1
    if _budget[0] < 0:
        raise ValueError("Expression evaluation exceeded its operation budget.")
    if isinstance(expr, list):
        return [evaluate_expression(value, context, _budget) for value in expr]
    if not isinstance(expr, dict):
        return expr
    if "var" in expr:
        value = context
        for part in expr["var"].split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
    def ev(child):
        return evaluate_expression(child, context, _budget)
    def boolean(value):
        if type(value) is not bool:
            raise ValueError("Boolean expressions require boolean operands.")
        return value
    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Numeric expressions require finite numeric operands.")
        return value
    op = expr["op"]
    if op == "if":
        return ev(expr["then"] if boolean(ev(expr["when"])) else expr["else"])
    if op == "and":
        return all(boolean(ev(child)) for child in expr["args"])
    if op == "or":
        return any(boolean(ev(child)) for child in expr["args"])
    if op == "not":
        return not boolean(ev(expr["arg"]))
    if op in ("exists", "minimum"):
        values = []
        pool = context.get(expr["pool"])
        if not isinstance(pool, list):
            raise ValueError("Expression pools must be observed lists.")
        for item in pool:
            scoped = dict(context, item=item)
            if boolean(evaluate_expression(expr["where"], scoped, _budget)):
                if op == "exists":
                    return True
                values.append(number(evaluate_expression(expr["value"], scoped, _budget)))
        if op == "exists":
            return False
        return min(values) if values else number(ev(expr["default"]))
    if op in ARITHMETIC:
        values = [number(ev(child)) for child in expr["args"]]
        if op == "add": return sum(values)
        if op == "sub": return values[0] - values[1]
        if op == "min": return min(values)
        if op == "max": return max(values)
    left, right = ev(expr["left"]), ev(expr["right"])
    if op == "eq": return type(left) is type(right) and left == right or type(left) in (int, float) and type(right) in (int, float) and left == right
    if op == "ne": return not evaluate_expression(dict(op="eq", left=left, right=right), {}, _budget)
    if op == "in":
        if not isinstance(right, list):
            raise ValueError("in requires a list on the right.")
        return any(evaluate_expression(dict(op="eq", left=left, right=value), {}, _budget) for value in right)
    left, right = number(left), number(right)
    if op == "lt": return left < right
    if op == "le": return left <= right
    if op == "gt": return left > right
    if op == "ge": return left >= right
    raise ValueError("Unsupported expression operator: " + str(op))
