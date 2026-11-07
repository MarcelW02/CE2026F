"""Operational prose contracts with action-time authorization and real refunds."""
import copy
import math

from .fp_cases import FP_OUTCOME_MAX, FP_OUTCOME_POINTS
from .fp_world import TravelWorld

from .operational_expressions import evaluate_expression, validate_expression


CONTRACT_REVISION = "operational-travel-20261106"
CONTRACT_KEYS = frozenset(("budget_limit", "arrival_deadline", "refund_terms"))
PRIVATE_RESULT_KEYS = frozenset((
    "budget_at_commit", "preferred_at_commit", "operational_contract",
    "operational_documents", "resolved_budget_limit", "resolved_arrival_deadline",
    "resolved_retained_loss_limit",
))


def validate_operational_case(case):
    """Validate program/source shape; semantic equivalence needs independent review."""
    contract = case.get("operational_contract", {})
    sources = case.get("operational_sources", {})
    if (not isinstance(contract, dict) or not isinstance(sources, dict)
            or set(contract) != CONTRACT_KEYS
            or set(sources) != set(contract)):
        raise ValueError("Operational contracts and sources require exactly budget_limit, arrival_deadline and refund_terms.")
    option_ids = {option["id"] for option in case["options"]}
    if (not isinstance(contract["refund_terms"], dict) or not isinstance(sources["refund_terms"], dict)
            or set(contract["refund_terms"]) != option_ids or set(sources["refund_terms"]) != option_ids):
        raise ValueError("Every option needs exactly one refund expression and source.")
    documents = copy.deepcopy(case["documents"])
    def check_source(source_id):
        if not isinstance(source_id, str):
            raise ValueError("Operational source references must be strings.")
        document = documents.get(source_id)
        if (not isinstance(document, dict) or document.get("id") != source_id
                or not document.get("text") or type(document.get("version")) is not int
                or document["version"] < 1 or source_id in {
                    "hotel-terms", "hotel-bulletin", "transport-guide", "traveler-profile", "weather-forecast"}):
            raise ValueError("Operational sources must be valid, independently catalogued prose documents.")
    for source_id in (sources["budget_limit"], sources["arrival_deadline"], *sources["refund_terms"].values()):
        check_source(source_id)
    operational_ids = {sources["budget_limit"], sources["arrival_deadline"], *sources["refund_terms"].values()}
    for option in case["options"]:
        fee = option.get("hold_fee_usd", 0)
        if type(fee) not in (int, float) or not math.isfinite(fee) or not 0 <= fee <= option["price"]:
            raise ValueError("A visible hold fee must be finite and between zero and the fare price.")
    def check_patch(patch):
        if not isinstance(patch, dict) or set(patch) - set(contract):
            raise ValueError("Unknown operational contract field.")
        for key, expression in patch.items():
            if key == "refund_terms":
                if not isinstance(expression, dict) or set(expression) - option_ids:
                    raise ValueError("Refund updates must refer to known options.")
                for program in expression.values():
                    validate_expression(program, result_kind="refund")
            else:
                validate_expression(expression, result_kind="number")
    check_patch(contract)
    last_at = -1
    for event in case["events"]:
        if event["at"] < last_at:
            raise ValueError("Events must be ordered by virtual time.")
        last_at = event["at"]
        changes = event["changes"]
        patch = changes.get("operational_contract", {})
        check_patch(patch)
        replaced = set()
        for document in changes.get("operational_documents", []):
            source_id = document["id"]
            if source_id not in operational_ids:
                raise ValueError("Operational document amendments must revise a linked contract source.")
            if source_id in replaced:
                raise ValueError("An event cannot revise the same source twice.")
            if source_id not in documents or document["version"] <= documents[source_id]["version"]:
                raise ValueError("Document amendments require an existing source and a larger version.")
            documents[source_id] = copy.deepcopy(document)
            check_source(source_id)
            replaced.add(source_id)
        # Changes of semantic terms must be visibly announced and readable.
        required = set()
        for key, expression in patch.items():
            if key == "refund_terms":
                required.update(sources[key][option_id] for option_id in expression)
            else:
                required.add(sources[key])
        if not required <= replaced or (patch and not event.get("text")):
            raise ValueError("Every changed program needs an arrived notice and a replaced prose source.")
    return True


class OperationalTravelWorld(TravelWorld):
    """Actual commitments/refunds with expression-based operational conditions."""

    def __init__(self, case, concurrency=3):
        from .world_factory import validate_case
        validate_case(case)
        self._contract = copy.deepcopy(case["operational_contract"])
        self._contract_sources = copy.deepcopy(case["operational_sources"])
        self._booked_refund_programs = {}
        self._booked_refund_sources = {}
        self._held_deposits = {}
        self._choice_limits = {}
        super().__init__(case, concurrency=concurrency)
        for option in self._options.values():
            option.setdefault("hold_fee_usd", 0)

    def _retained_hold_fees(self):
        return sum(fee for identifier, fee in self._held_deposits.items()
                   if self.finished or self._holds[identifier]["status"] == "expired")

    def _total_retained_loss(self):
        return self._retained_cancel_fees + self._retained_hold_fees()

    def _source_reference(self, source_id):
        return dict(id=source_id, version=self._docs[source_id]["version"])

    def _public_view(self, value):
        if isinstance(value, list):
            return [self._public_view(item) for item in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        result = {key: self._public_view(item) for key, item in value.items()
                  if key not in PRIVATE_RESULT_KEYS}
        option_id = value.get("option_id", value.get("id"))
        if option_id in self._contract_sources["refund_terms"]:
            source_id = self._contract_sources["refund_terms"][option_id]
            reference = self._booked_refund_sources.get(value.get("id"), self._source_reference(source_id))
            result["refund_contract_source"] = copy.deepcopy(reference)
            result["fare_fields_scope"] = "base terms; the linked conditional refund contract takes precedence"
        return result

    def observe(self):
        result = super().observe()
        result["operational_contract_revision"] = CONTRACT_REVISION
        result["operational_sources"] = {
            "budget_limit": self._source_reference(self._contract_sources["budget_limit"]),
            "arrival_deadline": self._source_reference(self._contract_sources["arrival_deadline"]),
        }
        result["uncredited_hold_deposits_usd"] = sum(self._held_deposits.values())
        result["retained_hold_fees_usd"] = self._retained_hold_fees()
        result["total_retained_loss_usd"] = self._total_retained_loss()
        return self._public_view(result)

    def batch(self, actions):
        return self._public_view(super().batch(actions))

    def _advance(self, target):
        cursor = self._event_cursor
        super()._advance(target)
        for event in self._spec["events"][cursor:self._event_cursor]:
            changes = event["changes"]
            for key, expression in changes.get("operational_contract", {}).items():
                if key == "refund_terms":
                    self._contract[key].update(copy.deepcopy(expression))
                else:
                    self._contract[key] = copy.deepcopy(expression)
            for document in changes.get("operational_documents", []):
                self._docs[document["id"]] = copy.deepcopy(document)

    def _offer_facts(self, value):
        option_id = value.get("option_id", value.get("id"))
        facts = copy.deepcopy(self._options.get(option_id, {}))
        facts.update(copy.deepcopy(value))
        facts.pop("inventory", None)
        if "arrival_minute" in facts and "mode" in facts:
            facts["meeting_arrival"] = facts["arrival_minute"] + self._rules["transfer"][facts["mode"]]
        facts.setdefault("available_from", 0)
        return facts

    def _context(self, candidate=None, booking=None):
        candidate = self._offer_facts(candidate) if candidate else {}
        booking = self._offer_facts(booking) if booking else {}
        chosen_id = candidate.get("option_id", candidate.get("id"))
        offers = [self._offer_facts(option) for option in self._options.values()
                  if option["inventory"] > 0 and option.get("available_from", 0) <= self.now < option["expires_at"]]
        # A held candidate remains a purchasable alternative after public sale ends.
        chosen_held = any(hold["option_id"] == chosen_id and hold["status"] == "held"
                          and self.now < hold["expires_at"] for hold in self._holds.values())
        if chosen_held and chosen_id not in {option["id"] for option in offers}:
            offers.append(self._offer_facts(self._options[chosen_id]))
        holds = [self._offer_facts(hold) for hold in self._holds.values()
                 if hold["status"] == "held" and self.now < hold["expires_at"]]
        return dict(candidate=candidate, booking=booking, offers=offers, holds=holds,
                    state=dict(now=self.now, net_spend=self._net_transport_spend,
                               hotel_fee=0 if self._fee_waived else self._fee,
                               retained_fees=self._retained_cancel_fees,
                               total_refunds=self._transport_refunds,
                               uncredited_hold_deposits=sum(self._held_deposits.values()),
                               retained_hold_fees=self._retained_hold_fees(),
                               total_retained_loss=self._total_retained_loss(),
                               weather=copy.deepcopy(self._weather_delays)))

    def _number(self, program, context, label):
        value = evaluate_expression(program, context)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(label + " must evaluate to a finite nonnegative number.")
        return value

    def _limit(self, candidate):
        return min(self._rules["budget"], self._number(self._contract["budget_limit"],
                   self._context(candidate, candidate if candidate.get("confirmed_at") is not None else None), "Budget limit"))

    def _deadline(self, candidate):
        return min(self._rules["deadline"], self._number(self._contract["arrival_deadline"],
                   self._context(candidate, candidate if candidate.get("confirmed_at") is not None else None), "Arrival deadline"))

    def _execute(self, tool, args):
        if tool == "hold":
            option = self._options.get(args.get("id"))
            # Invalid inventory follows the original denial without charging.
            if (option and option["inventory"] > 0 and option.get("available_from", 0) <= self.now < option["expires_at"]):
                fee = option["hold_fee_usd"]
                expense = self._net_transport_spend + fee + (0 if self._fee_waived else self._fee)
                if fee and expense > self._limit(option):
                    return dict(ok=False, error="This reservation deposit would exceed the current spending authorization.")
                result = super()._execute(tool, args)
                if result.get("ok"):
                    hold = self._holds[result["hold"]["id"]]
                    hold["hold_fee_usd"] = fee
                    hold["deposit_paid_usd"] = fee
                    self._held_deposits[hold["id"]] = fee
                    self._net_transport_spend += fee
                    self._transport_payments += fee
                    if fee:
                        self._transport_ledger.append(dict(at=self.now, kind="hold_payment", hold_id=hold["id"], amount_usd=fee))
                    result["hold"] = copy.deepcopy(hold)
                return result
        if tool == "confirm":
            hold = self._holds.get(args.get("id"))
            if (hold and hold["status"] == "held" and args.get("code") == self._spec["consent"]
                    and args.get("key") not in self._request_receipts):
                original_budget = self._rules["budget"]
                choice_limits = {option_id: self._limit(option) for option_id, option in self._options.items()}
                self._rules["budget"] = self._limit(hold)
                before = set(self._bookings)
                deposit = self._held_deposits.get(hold["id"], 0)
                # The original confirmation charges the full quoted fare. Credit
                # its already-paid deposit exactly once, restoring it on failure.
                self._net_transport_spend -= deposit
                try:
                    result = super()._execute(tool, args)
                finally:
                    self._rules["budget"] = original_budget
                    if set(self._bookings) == before:
                        self._net_transport_spend += deposit
                for identifier in set(self._bookings) - before:
                    booking = self._bookings[identifier]
                    booking["deposit_credited_usd"] = deposit
                    self._transport_payments -= deposit
                    self._held_deposits.pop(hold["id"], None)
                    self._transport_ledger[-1]["amount_usd"] -= deposit
                    self._transport_ledger[-1]["deposit_credit_usd"] = deposit
                    self._request_receipts[booking["request_key"]] = copy.deepcopy(booking)
                    if "booking" in result:
                        result["booking"] = copy.deepcopy(booking)
                    option_id = booking["option_id"]
                    self._booked_refund_programs[identifier] = copy.deepcopy(self._contract["refund_terms"][option_id])
                    self._booked_refund_sources[identifier] = self._source_reference(self._contract_sources["refund_terms"][option_id])
                    self._choice_limits[identifier] = choice_limits
                return result
        if tool == "cancel":
            booking = self._bookings.get(args.get("id"))
            if (booking and booking["kind"] == "transport" and booking["status"] == "confirmed"
                    and args.get("code") == self._spec["consent"]):
                program = self._booked_refund_programs[booking["id"]]
                context = self._context(booking, booking)
                retained = evaluate_expression(program, context)
                if retained is None:
                    return dict(ok=False, error="Cancellation is not permitted under the applicable fare contract.")
                retained = self._number(retained, context, "Retained cancellation amount")
                if retained > booking["price"]:
                    raise ValueError("A retained cancellation amount cannot exceed the booked fare.")
                # Reuse original actual payment/refund/idempotency/safety handling.
                original_policy, original_fee = booking["change_policy"], booking["cancel_fee_usd"]
                booking["change_policy"] = "fee" if retained else "flexible"
                booking["cancel_fee_usd"] = retained
                try:
                    result = super()._execute(tool, args)
                finally:
                    booking["change_policy"], booking["cancel_fee_usd"] = original_policy, original_fee
                    self._request_receipts[booking["request_key"]] = copy.deepcopy(booking)
                result["booking"] = copy.deepcopy(booking)
                return result
        return super()._execute(tool, args)

    def evaluate(self):
        """Post-episode deterministic outcome checks; never sent to a policy."""
        result = super().evaluate()
        active = [booking for booking in self._bookings.values()
                  if booking["kind"] == "transport" and booking["status"] == "confirmed"]
        current = active[0] if len(active) == 1 else None
        checks = result["checks"]
        # A later authorization change applies to new charged actions only.
        # It never revokes a purchase approved when that purchase completed.
        checks["budget"] = bool(current) and all(
            booking["expense_at_commit"] <= booking["budget_at_commit"]
            for booking in self._bookings.values() if "expense_at_commit" in booking)
        checks["arrival"] = bool(current) and checks["accessibility"] and checks["avoided_carriers"] and (
            self._offer_facts(current)["meeting_arrival"] <= self._deadline(current))
        # Preserve the ordinary soft mode preference. Its feasibility comparison
        # uses the same real authorization/deadline rules for every alternative.
        preferred = bool(current) and current["mode"] == self._rules["preferred"]
        if current and not preferred:
            def feasible(option):
                on_sale = (option["inventory"] > 0 and option.get("available_from", 0) <= self.now < option["expires_at"])
                earlier_choice = (option["id"] in self._booking_choice_stock[current["id"]] and any(
                    option.get("available_from", 0) <= at < option["expires_at"]
                    for at in (current["held_at"], current["confirmed_at"])))
                spend = self._net_transport_spend - current["price"] + option["price"] + (0 if self._fee_waived else self._fee)
                limit = self._limit(option) if on_sale else self._choice_limits[current["id"]][option["id"]]
                return ((on_sale or earlier_choice) and spend <= limit
                        and self._offer_facts(option)["meeting_arrival"] <= self._deadline(option)
                        and (not self._rules["requires_step_free"] or option["step_free"])
                        and option["carrier"] not in self._rules["avoid_carriers"])
            preferred = not any(option["mode"] == self._rules["preferred"] and feasible(option)
                                for option in self._options.values())
        checks["preference"] = bool(preferred)
        # Evaluation is terminal even when a policy returns before finish. All
        # remaining deposits are then abandoned; public mid-run telemetry keeps
        # distinguishing active deposits from already expired fees.
        terminal_hold_loss = sum(self._held_deposits.values())
        terminal_total_loss = self._retained_cancel_fees + terminal_hold_loss
        result["components"]["arrival"] = float(checks["arrival"])
        result["components"]["requests"] = sum(checks[key] for key in
            ("budget", "preference", "accessibility", "avoided_carriers")) / 4
        result["outcome_points"] = sum(FP_OUTCOME_POINTS[key] * value for key, value in result["components"].items())
        result["quality"] = round(result["outcome_points"] / FP_OUTCOME_MAX, 9)
        result["success"] = all(checks.values())
        result["operational_contract_revision"] = CONTRACT_REVISION
        result["retained_hold_fees_usd"] = terminal_hold_loss
        result["uncredited_hold_deposits_usd"] = sum(self._held_deposits.values())
        result["total_retained_loss_usd"] = terminal_total_loss
        result["operational_assessment"] = dict(
            service_present=len(active) == 1, verified_service=len(active) == 1 and result["commitments_verified"],
            usable_arrival=checks["arrival"], budget=checks["budget"],
            initial_service=checks["initial_service"] and any("confirmed_at" in booking for booking in self._bookings.values()),
            preference=checks["preference"], safety=checks["safety"],
            verified_handoff=result["commitments_verified"] and result["handoff_complete"])
        return result
