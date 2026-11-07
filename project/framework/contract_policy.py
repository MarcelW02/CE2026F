"""Observed-source memory, conditional arithmetic, reservations, and monitoring.

Use this controller or supply a custom loop in solution/policy.py. Interpretation
and advance preparation are policy choices; no agent count or API is required.
"""
import copy
import math

from .operational_expressions import evaluate_expression
from .contract_interpreter import compile_contract, role_source_ids


def action(tool, **arguments):
    return dict(tool=tool, arguments=arguments)


class Controller:
    def __init__(self, world, interpret, trace, *, refresh_context=True, max_decisions=12, prepare=True):
        self.world, self.interpret, self.trace = world, interpret, trace
        self.refresh_context, self.max_decisions = refresh_context, max_decisions
        self.advance_preparation = prepare
        self.documents, self.offers, self.sale_ids = {}, {}, set()
        self.offer_weather = {}
        self.program, self.revision, self.serial = None, None, 0
        self.interpreted_documents = {}
        self.booked_programs = {}
        self.booked_evidence = {}
        self.prepared_forecasts = set()

    def batch(self, actions):
        rows = self.world.batch(actions)
        self.trace.append(dict(kind="actions", rows=copy.deepcopy(rows)))
        for row in rows:
            result = row["result"]
            if result.get("ok") and row["tool"] == "read":
                source = result["source"]
                self.documents[source["id"]] = copy.deepcopy(source)
            if result.get("ok") and row["tool"] == "search":
                self.sale_ids = {offer["id"] for offer in result["options"]}
                for offer in result["options"]:
                    self.offers[offer["id"]] = dict(copy.deepcopy(offer), observed_at=result["observed_at"])
        return [row["result"] for row in rows]

    def call(self, tool, **arguments):
        return self.batch([action(tool, **arguments)])[0]

    def refresh(self, initial=False):
        observation = self.world.observe()
        if initial:
            ids = {source["id"] for source in observation["source_catalog"]}
            first = [action("search")]
            if "hotel-terms" in ids:
                first.append(action("read", id="hotel-terms"))
            spend_source = observation["operational_sources"]["budget_limit"]["id"]
            if spend_source != "hotel-terms":
                first.append(action("read", id=spend_source))
            self.batch(first)
        else:
            # Search and changed-source reads share the same public worker slots.
            pending = [action("read", id=source["id"]) for source in observation["source_catalog"]
                       if source["id"] not in self.documents or self.documents[source["id"]]["version"] != source["version"]]
            self.batch([action("search")] + pending)
        while not self.world.finished:
            observation = self.world.observe()
            pending = [action("read", id=source["id"]) for source in observation["source_catalog"]
                       if source["id"] not in self.documents or self.documents[source["id"]]["version"] != source["version"]]
            if not pending:
                break
            self.batch(pending)
        observation = self.world.observe()
        payload_observation = copy.deepcopy(observation)
        payload_observation.pop("case_id", None)
        payload = dict(observation=payload_observation, documents=copy.deepcopy(list(self.documents.values())),
                       offers=copy.deepcopy(list(self.offers.values())), previous=copy.deepcopy(self.program))
        if self.program is None or self.refresh_context:
            self.program = self.interpret(payload)
            self.interpreted_documents = copy.deepcopy(self.documents)
        for identifier in self.sale_ids:
            self.offer_weather[identifier] = copy.deepcopy(self.facts["weather"])
        self.revision = observation["revision"]
        # A newly purchased version can be read now, but an unavailable older
        # version must never be replaced with current terms by assumption.
        if self.program is None:
            return
        for booking in self.world.observe()["bookings"]:
            if booking.get("status") != "confirmed" or booking.get("kind") != "transport":
                continue
            if self.booked_programs.get(booking["id"]) is not None:
                continue
            reference = booking.get("refund_contract_source", {})
            source = self.interpreted_documents.get(reference.get("id"))
            if source and source["version"] == reference.get("version"):
                expression = self.program["refund_terms"].get(booking["option_id"])
                self.booked_programs[booking["id"]] = copy.deepcopy(expression)
                self.booked_evidence[booking["id"]] = dict(purchased_source=copy.deepcopy(reference),
                    read_source=copy.deepcopy(source), interpreted_version_matches=True)


    @property
    def facts(self):
        return self.program["facts"]

    def active(self, observation):
        values = [booking for booking in observation["bookings"]
                  if booking.get("kind") == "transport" and booking.get("status") == "confirmed"]
        return values[0] if len(values) == 1 else None

    def offer_facts(self, value, weather=None):
        identifier = value.get("option_id", value.get("id"))
        result = copy.deepcopy(self.offers.get(identifier, {}))
        result.update(copy.deepcopy(value))
        desired_weather = self.facts["weather"] if weather is None else weather
        # Confirmed booking arrivals come from current world observations. Cached
        # offers/holds may predate a weather change or disappear from later search.
        observed_weather = (self.facts["weather"] if value.get("confirmed_at") is not None
                            else self.offer_weather.get(identifier, self.facts["weather"]))
        if result.get("weather_exposed"):
            result["arrival_minute"] += desired_weather[result["mode"]] - observed_weather[result["mode"]]
        result["meeting_arrival"] = result["arrival_minute"] + self.facts["transfer"][result["mode"]]
        result.setdefault("available_from", 0)
        return result

    def context(self, observation, candidate, booking=None, *, at=None, weather=None, extra_hold=None, state_changes=None):
        at = observation["virtual_minute"] if at is None else at
        weather = self.facts["weather"] if weather is None else weather
        holds = [self.offer_facts(hold, weather) for hold in observation["holds"]
                 if hold["status"] == "held" and hold["expires_at"] > at]
        if extra_hold is not None:
            holds.append(self.offer_facts(extra_hold, weather))
        candidate = self.offer_facts(candidate, weather)
        offers = [self.offer_facts(self.offers[identifier], weather) for identifier in self.sale_ids
                  if self.offers[identifier].get("available_from", 0) <= at < self.offers[identifier]["expires_at"]]
        chosen_id = candidate.get("option_id", candidate["id"])
        if any(hold.get("option_id") == chosen_id for hold in holds) and chosen_id not in {offer["id"] for offer in offers}:
            offers.append(self.offer_facts(self.offers[chosen_id], weather))
        state = dict(now=at, net_spend=observation["net_transport_spend_usd"], hotel_fee=observation["hotel_fee"],
                     retained_fees=observation["retained_cancel_fees_usd"], total_refunds=observation["transport_refunds_usd"],
                     uncredited_hold_deposits=observation.get("uncredited_hold_deposits_usd", 0),
                     retained_hold_fees=observation.get("retained_hold_fees_usd", 0),
                     total_retained_loss=observation.get("total_retained_loss_usd", 0), weather=copy.deepcopy(weather))
        state.update(state_changes or {})
        return dict(candidate=candidate, booking=self.offer_facts(booking, weather) if booking else {},
                    offers=offers, holds=holds, state=state)

    def number(self, expression, context):
        value = evaluate_expression(expression, context)
        return value if type(value) in (int, float) and math.isfinite(value) else None

    def physically_usable(self, candidate, context):
        limit = self.number(self.program["arrival_deadline"], context)
        return (limit is not None and context["candidate"]["meeting_arrival"] <= limit
                and (not self.facts["requires_step_free"] or candidate["step_free"])
                and candidate["carrier"] not in self.facts["avoid_carriers"])

    def keep_valid(self, observation, booking, weather=None, at=None):
        context = self.context(observation, booking, booking, at=at, weather=weather)
        # A later spending amendment cannot revoke an already accepted payment.
        # Arrival, accessibility and carrier suitability still apply to the trip.
        return self.physically_usable(booking, context)

    def projected_state(self, observation, *, added_deposit=0, booking=None, retained=0, at=None):
        refund = booking["price"] - retained if booking else 0
        uncredited = observation.get("uncredited_hold_deposits_usd", 0) + added_deposit
        cancellation_loss = observation["retained_cancel_fees_usd"] + (retained if booking else 0)
        expired_deposits = observation.get("retained_hold_fees_usd", 0)
        if at is not None:
            expired_deposits += sum(hold.get("deposit_paid_usd", hold.get("hold_fee_usd", 0))
                for hold in observation["holds"]
                if hold["status"] == "held" and hold["expires_at"] <= at)
        return dict(net_spend=observation["net_transport_spend_usd"] + added_deposit - refund,
                    retained_fees=cancellation_loss,
                    total_refunds=observation["transport_refunds_usd"] + refund,
                    uncredited_hold_deposits=uncredited,
                    retained_hold_fees=expired_deposits,
                    total_retained_loss=cancellation_loss + expired_deposits)


    def purchase_plan(self, observation, candidate, booking=None, *, weather=None, at=None, assume_hold=False):
        now = observation["virtual_minute"] if at is None else at
        held = next((hold for hold in observation["holds"] if hold["status"] == "held"
            and hold["option_id"] == candidate["id"] and hold["expires_at"] > now + (4 if booking else 2)), None)
        if held is None and not assume_hold:
            if candidate["id"] not in self.sale_ids or now + 1 >= candidate["expires_at"]:
                return None
        fee = 0 if held else candidate.get("hold_fee_usd", 0)
        deposit = held.get("deposit_paid_usd", held.get("hold_fee_usd", 0)) if held else fee
        hypothetical = None if held else dict(candidate, id="planned-hold", option_id=candidate["id"],
            held_at=now + 1, expires_at=observation["horizon"], status="held")
        before_hold = self.context(observation, candidate, at=now + 1, weather=weather)
        hold_limit = self.number(self.program["budget_limit"], before_hold) if fee else None
        if fee and (hold_limit is None or observation["net_transport_spend_usd"] + observation["hotel_fee"] + fee > hold_limit):
            return None
        retained = 0
        cancel_at = now + (2 if held else 3)
        if booking:
            old_id = booking["option_id"]
            expression = (self.booked_programs[booking["id"]] if booking["id"] in self.booked_programs
                          else self.program["refund_terms"].get(old_id))
            context = self.context(observation, booking, booking, at=cancel_at, weather=weather,
                extra_hold=hypothetical, state_changes=self.projected_state(observation, added_deposit=fee, at=cancel_at))
            retained = self.number(expression, context)
            if retained is None or retained < 0 or retained > booking["price"]:
                return None
        commit_at = cancel_at + 2 if booking else now + (2 if held else 3)
        state = self.projected_state(observation, added_deposit=fee, booking=booking, retained=retained, at=commit_at)
        expense = state["net_spend"] + candidate["price"] - deposit + observation["hotel_fee"]
        held_candidate = dict(candidate, **(held or hypothetical))
        context = self.context(observation, held_candidate, at=commit_at, weather=weather,
                               extra_hold=hypothetical, state_changes=state)
        limit = self.number(self.program["budget_limit"], context)
        # Arrival is checked on a confirmed ticket, after its reservation deposit
        # has been credited and its hold consumed. Budget is checked before that.
        arrival_context = copy.deepcopy(context)
        arrived = dict(arrival_context["candidate"], confirmed_at=commit_at, status="confirmed")
        arrival_context["candidate"] = arrived
        arrival_context["booking"] = copy.deepcopy(arrived)
        arrival_context["holds"] = [hold for hold in arrival_context["holds"]
                                     if hold.get("option_id") != candidate["id"]]
        arrival_context["state"].update(net_spend=expense - observation["hotel_fee"],
            uncredited_hold_deposits=state["uncredited_hold_deposits"] - deposit,
            total_retained_loss=state["total_retained_loss"])
        if (limit is None or expense > limit or not self.physically_usable(candidate, arrival_context)
                or commit_at > observation["horizon"]):
            return None
        return dict(option=candidate, hold=held, expense=expense,
                    loss=state["retained_fees"] + state["uncredited_hold_deposits"] - deposit, retained=retained,
                    commit_at=commit_at, preferred=candidate["mode"] == self.facts["preferred"])


    def candidates(self, observation):
        held_ids = {hold["option_id"] for hold in observation["holds"] if hold["status"] == "held"}
        return [offer for identifier, offer in self.offers.items() if identifier in self.sale_ids or identifier in held_ids]

    def choose_plan(self, observation, booking):
        plans = [plan for offer in self.candidates(observation)
                 if not booking or offer["id"] != booking["option_id"]
                 if (plan := self.purchase_plan(observation, offer, booking)) is not None]
        plans.sort(key=lambda plan: (not plan["preferred"], plan["expense"], plan["loss"], plan["option"]["arrival_minute"]))
        if booking and self.keep_valid(observation, booking):
            if booking["mode"] == self.facts["preferred"] or not plans or not plans[0]["preferred"]:
                return None
        return plans[0] if plans else None

    def implement(self, plan, booking):
        # Re-evaluate dependencies after actual hold/cancel results, especially
        # when an external update occurs during a preceding action.
        offer, held = plan["option"], plan["hold"]
        if held is None:
            result = self.call("hold", id=offer["id"])
            if not result.get("ok"):
                return False
            held = result["hold"]
        if self.world.observe()["revision"] != self.revision:
            self.refresh()
        current = self.active(self.world.observe())
        revised = self.purchase_plan(self.world.observe(), self.offers[offer["id"]], current)
        if revised is None:
            return False
        if current:
            result = self.call("cancel", id=current["id"], code=self.facts["consent"])
            if not result.get("ok"):
                return False
            if self.world.observe()["revision"] != self.revision:
                self.refresh()
            revised = self.purchase_plan(self.world.observe(), self.offers[offer["id"]])
            if revised is None:
                return False
        offer, held = revised["option"], revised["hold"]
        if held is None:
            return False
        self.serial += 1
        key = "contract-booking-" + str(self.serial)
        self.call("confirm", id=held["id"], code=self.facts["consent"], key=key)
        receipt = self.call("status", key=key)
        if receipt.get("booking") and receipt["booking"]["status"] == "confirmed":
            booking = receipt["booking"]
            reference = booking.get("refund_contract_source", {})
            evidence = self.interpreted_documents.get(reference.get("id"))
            matches = evidence is not None and evidence["version"] == reference.get("version")
            # A notice may arrive during confirmation. Do not label an earlier
            # interpretation as the newly purchased version in that situation.
            self.booked_programs[booking["id"]] = (
                copy.deepcopy(self.program["refund_terms"][offer["id"]]) if matches else None)
            self.booked_evidence[booking["id"]] = dict(
                purchased_source=copy.deepcopy(reference),
                read_source=copy.deepcopy(evidence), interpreted_version_matches=matches)
            return True
        return False


    def prepare(self, observation, booking):
        """Reserve only when a publicly described possibility has a viable recovery."""
        opportunities = []
        for forecast in self.facts["forecasts"]:
            when, delay = forecast.get("at"), forecast.get("delay")
            if type(when) not in (int, float) or type(delay) not in (int, float) or when <= self.world.now:
                continue
            mode = forecast["mode"]
            scenario = dict(self.facts["weather"], **{mode: delay})
            if self.keep_valid(observation, booking, weather=scenario, at=when):
                continue
            covered = False
            for hold in observation["holds"]:
                if hold["status"] == "held" and hold["expires_at"] > when+4:
                    candidate = self.offers.get(hold["option_id"])
                    if candidate and self.purchase_plan(observation, candidate, booking, weather=scenario, at=when) is not None:
                        covered = True
                        break
            if covered:
                continue
            for offer in self.candidates(observation):
                if offer["id"] == booking["option_id"]:
                    continue
                if any(hold["option_id"] == offer["id"] and hold["status"] == "held" and hold["expires_at"] > when+4
                       for hold in observation["holds"]):
                    continue
                # An offer still on sale after the possible event can be acquired
                # then. Closing inventory needs a paid preparation decision now.
                if offer["expires_at"] > when+1 or self.world.now+1 >= offer["expires_at"]:
                    continue
                context = self.context(observation, offer, at=self.world.now+1)
                fee = offer.get("hold_fee_usd", 0)
                limit = self.number(self.program["budget_limit"], context) if fee else None
                if fee and (limit is None or observation["net_transport_spend_usd"] + observation["hotel_fee"] + fee > limit):
                    continue
                # Simulate the paid hold as an observed resource in the announced
                # adverse scenario. Its eventual expiry is checked after the real call.
                imagined = copy.deepcopy(observation)
                imagined["virtual_minute"] = when
                imagined["net_transport_spend_usd"] += fee
                imagined["uncredited_hold_deposits_usd"] = imagined.get("uncredited_hold_deposits_usd", 0) + fee
                imagined["holds"].append(dict(offer, id="anticipated-hold", option_id=offer["id"], held_at=self.world.now+1,
                                               expires_at=observation["horizon"], deposit_paid_usd=fee, status="held"))
                plan = self.purchase_plan(imagined, offer, booking, weather=scenario, at=when)
                if plan is not None:
                    opportunities.append((not plan["preferred"], fee, plan["expense"], offer["expires_at"], offer))
        if not opportunities:
            return None
        opportunities.sort(key=lambda row: row[:4])
        # No stated probability is invented: this is a disclosed robust hedge
        # against an announced possible physical event, subject to actual costs.
        chosen = opportunities[:1]
        latest_start = min(row[3]-2 for row in chosen)
        if self.world.now < latest_start:
            return int(latest_start)
        for row in chosen:
            result = self.call("hold", id=row[4]["id"])
            self.trace.append(dict(kind="preparation", strategy="one affordable recovery",
                                   option_id=row[4]["id"], result=copy.deepcopy(result)))
        return self.world.now

    def run(self):
        self.refresh(initial=True)
        if self.world.finished:
            return
        observation = self.world.observe()
        if observation["hotel_fee"]:
            waiver = self.facts["waiver"]
            self.call("claim", topic=waiver["topic"], code=waiver["code"], version=waiver["version"])
        for iteration in range(self.max_decisions):
            if self.world.finished:
                break
            observation = self.world.observe()
            if observation["revision"] != self.revision:
                # Protect an already observed, imminently closing recovery before
                # a two-minute source refresh. This uses the prior announced
                # possibility, never the unseen new source or future outcome.
                current = self.active(observation)
                if current and self.advance_preparation:
                    self.prepare(observation, current)
                self.refresh()
                observation = self.world.observe()
            if any(booking.get("status") == "pending_verification" for booking in observation["bookings"]):
                self.call("status")
                observation = self.world.observe()
            booking = self.active(observation)
            plan = self.choose_plan(observation, booking)
            if plan:
                self.trace.append(dict(kind="planned_purchase", at=self.world.now, plan=copy.deepcopy(plan)))
                self.implement(plan, booking)
                continue
            if observation["virtual_minute"] >= observation["handoff_minute"]:
                self.call("finish")
                break
            wake = None
            if booking and self.advance_preparation:
                wake = self.prepare(observation, booking)
                if wake == self.world.now:
                    continue
            observation = self.world.observe()
            next_time = min(observation["handoff_minute"], self.world.now+2)
            if wake is not None and wake > self.world.now:
                next_time = min(next_time, wake)
            for forecast in self.facts["forecasts"]:
                when = forecast.get("at")
                if type(when) in (int, float) and when > self.world.now:
                    next_time = min(next_time, when)
            self.call("wait", minutes=max(1, min(36, int(next_time-self.world.now))))


        if not self.world.finished:
            self.call("finish")


def run_operational_hybrid(world, api, config, route_fn):
    """Keep interpretation, observed memory and tool effects inspectable."""
    traces, memory, seen_versions = [], {}, {}

    def interpret(payload):
        observation = payload["observation"]
        domains = list(dict.fromkeys(route_fn(observation, copy.deepcopy(memory))))
        if any(domain not in ("traveler", "transport", "hotel") for domain in domains):
            raise ValueError("Route to traveler, transport, or hotel.")
        if payload.get("previous") is None:
            domains = ["traveler", "transport", "hotel"]
        # An authoritative source amendment needs its scope reconsidered even
        # when a notice uses a word absent from a custom keyword router.
        scopes = role_source_ids(payload)
        for source in payload["documents"]:
            if seen_versions.get(source["id"]) != source["version"]:
                for domain, identifiers in scopes.items():
                    if source["id"] in identifiers and domain not in domains:
                        domains.append(domain)
        # New inventory can share an unchanged fare source. Its refund mapping
        # still needs transport interpretation, even without a source revision.
        previous_refunds = (payload.get("previous") or {}).get("refund_terms", {})
        if (set(previous_refunds) != {offer["id"] for offer in payload["offers"]}
                and "transport" not in domains):
            domains.append("transport")
        result = compile_contract(payload, api, config, domains, traces)
        seen_versions.update({source["id"]: source["version"] for source in payload["documents"]})
        memory.update(investigated=True, revision=observation["revision"],
                      investigated_at=observation["virtual_minute"])
        return result

    controller = Controller(world, interpret, traces, refresh_context=config["refresh_context"],
                            max_decisions=config["max_decisions"],
                            prepare=config.get("forecast_strategy", "precaution") != "cheapest")
    controller.run()
    memory.update(documents=copy.deepcopy(controller.documents), compiled=copy.deepcopy(controller.program),
                  purchased_refund_terms=copy.deepcopy(controller.booked_programs),
                  purchased_refund_evidence=copy.deepcopy(controller.booked_evidence))
    return dict(traces=traces, working_memory=memory,
                context=dict(architecture=config["architecture"], source_versions=seen_versions))
