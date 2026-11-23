# Team 2 final project experiment log

The target is a 100/100 benchmark score on the staff evaluation. The development gate is 60/60 complete Public episodes with cache-neutral grading cost at or below $0.02407475. The staff evaluation uses 120 episodes and a $0.04814950 allowance. See the [staff scoring guide](https://github.com/jhleepidl/CE2026F/blob/7b0f4197de9826f3ff3081f2317ddcb74f678da7/project/README.md#7-understand-the-100-point-score).

## November 15, 2026 baseline

Staff v10 commit `7b0f4197de9826f3ff3081f2317ddcb74f678da7`. The working solver uses GPT-5.6 Luna at low effort, a combined interpreter, context refresh, precaution, and a prompt requiring literal consent and current waiver evidence. The original v10 solver remains available as a historical control.

| Run | Change | Complete episodes | Mean outcome /90 | Grading cost | Local score /100 |
|---|---|---:|---:|---:|---:|
| Vanilla Dev | Staff defaults | 3/9 | 40.00 | $0.02566060 | |
| Refresh Dev | Enabled refresh | 4/9 | 47.78 | $0.04210760 | |
| Combined Dev | Combined interpreter and more specific evidence instructions, with refresh enabled | 9/9 | 90.00 | $0.02894120 | |
| Cheaper model Dev | Switched to GPT-6 Luna with no reasoning effort | 7/9 | 80.00 | $0.01111590 | |
| Combined Public | Same implementation as Combined Dev | 56/60 | 86.17 | $0.15355200 | 87.73 |

- The strongest Dev candidate still lost four Public episodes. Two expanded a coach-only arrival concession to flights, one truncated a literal consent token, and one returned an incomplete refund mapping with a duplicate offer ID.
- The combined candidate changed multiple factors together. Its improvement establishes a new baseline. The individual effects of routing and the evidence prompt remain unmeasured.
- The arrival scope experiment passed one targeted replay. The compiled expression also passed four offline checks across mode and fare boundaries. The extra prompt is in an isolated candidate because broader performance is unmeasured.

## Experiment 01 — Refund rules keyed by short offer references

- **Hypothesis.** A response field for each observed offer eliminates duplicate and missing refund assignments. The failing Public trace contained a repeated opaque ID and omitted a different offer.
- **Change.** The candidate gives each observed offer a short reference and requests a fixed-key object of refund expressions. Python checks coverage and binds those expressions back to original IDs for the existing controller. The original IDs remain visible where they carry meaning in source prose and executable expressions. Model, prompt file, settings, framework, and published cases are held fixed.
- **Offline checks.** Passed round-trip binding, explicit zero versus forbidden cancellation, rejection of missing and unknown references, and preservation of the input and supplied schema.
- **Live checks.** The control and candidate each solved 1/2 episodes and averaged 55/90. Each made four calls. Grading cost was $0.00683660 for the control and $0.00722020 for the candidate. The case with the historical refund-mapping error passed in both fresh runs. Both runs dropped the same character from the consent token in the other case. This comparison therefore shows the consent failure recurs and provides no measured outcome lift from the refund format.
- **Provenance.** Control implementation `b9ebc77464a6c6eb06e9d67bba9070be3f4f05a9e3089f3b241e383eb0b03d31`. Candidate implementation `7c13856d0e37b9a70862f3220515f611fc95587eedab26e1df6a5291d9067aaf`. Both used the same two published cases as diagnostic inputs.
- **Dev check.** The candidate solved 8/9 and scored 85.56/90 at $0.02893940, compared with the recorded baseline's 9/9, 90/90, and $0.02894120. Dev was run once for this candidate.
- **Failure trace.** In Reactive case `dev-d1e8acd8cc`, the candidate assigned a $20 conditional cancellation charge to another offer and assigned $65 to the ticket it bought. The refreshed interpretation corrected the mapping, but the controller retained the terms interpreted at purchase. With that $65 charge, the planner found no affordable timely replacement. The baseline bound the $20 clause to the correct ticket and completed the exchange. Coverage checks verify that an expression exists for each offer. A separate evidence check is needed to verify which clause supports each assignment.
- **Decision.** Discard this candidate from the working solver and keep the artifacts. The targeted cases showed no score gain, the Dev run regressed, and cost was effectively flat on Dev. A full Public run was skipped. The next experiment will target the reproducible consent-token truncation from the current baseline.

## Experiment 02 — Bind consent tokens to the observed notice

- **Hypothesis.** A short reference at the original position in each notice will let the model choose the applicable approval while Python preserves the exact code. The same truncation recurred on the Public Forecast case in the baseline and both Experiment 01 runs.
- **Change.** In the combined operational interpreter, replace standard-format consent codes in arrived notices with distinct references. Bind a returned reference back to the original text before the controller acts. Translate any previous interpreted approval to the same reference for partial amendments. Keep the existing interpretation path for custom formats or existing reference markers.
- **Offline checks.** Passed exact restoration with two codes in different scopes, preservation of approval memory across a partial update, preservation of input, and fallback for custom codes and marker collisions.
- **First live comparison.** The targeted run solved the previously failing consent case at 90/90. The other case scored 10/90 because the response duplicated refund offer IDs and omitted an offer. That distinct failure was also observed in the historical Public baseline. The candidate averaged 50/90 across the pair at $0.00531620 in grading cost across three calls. The recent control averaged 55/90 at $0.00683660 and solved the other case instead.
- **Dev check.** The candidate solved 9/9 and scored 90/90 at $0.02915720 across 18 calls. The recorded baseline cost was $0.02894120 for the same case set and outcome.
- **Repeat.** The second targeted run passed both cases at $0.00763440 across four calls. The reproducible consent failure passed in both candidate runs. The refund mapping remained variable across runs.
- **Decision.** Promote to the working solver. Dev stayed at 9/9 and the targeted consent error cleared twice. The working copy was verified against tested implementation `7f9107c4fa33e551546ebde06a0a4ec9fd17150d36cd8f632492baa73ceff0d0`. Full Public performance is pending.

## Experiment 03 — Align offer references across sources and structured context

- **Hypothesis.** Using the same short offer label in read source text, observed offers, previous interpretation, and the schema will prevent copying errors while keeping the clause-to-offer association visible. Experiment 01 shortened only the output reference and misassigned one clause. This candidate keeps the supplied grouped-refund response.
- **Change.** Prepare a temporary model-facing context with one consistent label for each observed staff-format offer ID. Restore original IDs in the returned refund groups and expression literals before the controller reads them. Other source semantics and the controller stay on the existing baseline. Experiment 02 was kept out of this candidate to isolate the change.
- **Offline checks.** Passed label consistency across source text, offers, prior refund terms and the schema. The response restored both an offer ID and an ID used in an expression. Overlapping IDs and a longer unrelated token remained distinct.
- **Live checks.** The targeted candidate solved 2/2 at $0.00676340 across four calls. The Dev candidate solved 9/9 at $0.02754100 across 18 calls. The Reactive case that regressed in Experiment 01 passed. On Dev, input tokens dropped from 95,176 to 93,743 and grading cost fell 4.8% in one run.
- **Decision.** Test on top of the consent change using the four published cases with past failures and full Dev. This independent candidate is implementation `0c72307ba2be36c392c6c80c0abc0e7f1010c80339a51b3c847bd38c8c2f613f`. The evidence supports testing the combination. A single replay cannot establish stability.

## Experiment 04 — Add aligned offer references to the consent baseline

- **Change.** Apply Experiment 03's offer-reference mapping on top of the promoted Experiment 02 consent change. The two transformations run in sequence for the combined operational interpreter.
- **Targeted checks.** The policy compiles. The four-case replay solved 3/4 and averaged 80/90 at $0.00971100 across six calls. Both Forecast cases passed. A Basic case still extended its coach-only arrival concession to flights.
- **Dev check.** The combined candidate solved 8/9 and averaged 81.11/90 at $0.02686900. In `dev-2222f98c18`, the response used five distinct offer references for six offers. The supplied validator rejected it before any booking. Short consistent references helped in individual runs, but the grouped format still permits omissions.
- **Decision.** Keep the promoted consent-only solver. Retain the combined candidate as implementation `cb972c0078f79133aa0e4bc7fc9b0e3909c6acca0d743d0e970671eb4a946965` for analysis. The next experiment can use the Assignment 5 pattern of a bounded repair triggered by a failed coverage check. Give the repair the specific missing or conflicting reference and its source evidence.

Experiments 02–04 used $0.09554084 in estimated API cost. The staff grading allowances are scoring references. The local runner has a separate per-run guard of $2 in estimated API cost or 1,000 calls.

## Experiment 05 — One repair for unresolved refund rules

- **Hypothesis.** A bounded correction can recover a missing or contradictory refund assignment while preserving the rest of the interpretation. This applies the failed-check-and-repair pattern from Assignment 5.
- **Change.** On top of the consent baseline, collapse identical duplicate assignments locally. If a rule is missing or contradictory, ask for one typed expression per unresolved observed offer and validate the result. Keep the supplied controller and its final validation.
- **Offline checks.** Passed identical duplicates without a new model call, missing and conflicting assignments with one repair, zero versus forbidden cancellation, and preservation of unrelated fields.
- **Batch budget.** November 15 user cap is $0.25 per batch in estimated API spend. A local launcher passes per-run sublimits to the staff evaluator without editing protected files. This candidate has sublimits of $0.035 for the published replays and $0.065 for Dev.
- **Live results.** The four-case replay solved 3/4 at $0.00989580 grading cost. Dev solved 8/9 and scored 82.22/90 at $0.02907500 grading cost. The repair branch made zero live calls because the returned refund assignments already passed coverage.
- **Decision.** Keep the candidate isolated pending live evidence of repair. Reactive case `dev-d1e8acd8cc` returned the correct consent reference with the brackets missing, and the simulator refused the outbound confirmation. This exposed a narrow defect in the promoted interpreter.

## Experiment 06 — Accept consent reference punctuation variants

- **Change.** Resolve a recognized consent reference with or without brackets. Preserve a literal model value when it does not match an observed reference. This is a small change on the consent-only baseline.
- **Offline checks.** Exact and bracketless forms resolve to the original code. Incomplete punctuation and surrounding whitespace have the same result. Unknown references and unrelated literal codes remain unchanged.
- **Live results.** The published pair passed 2/2 at $0.00701800 grading cost. Dev passed 9/9 at $0.02929520. The Reactive failure from Experiment 05 passed. Implementation `5078a0541bee1d3edac2d0c75a66916c2ce048ab46ff80d2d9ad50baa118a3fa`.

## Experiment 07 — Keep conditional arrival concessions within scope

- **Change.** On top of Experiment 06, transplant the earlier prompt that distinguishes a default, an exception, and a narrower override. This targets the Basic trace that returned the later coach arrival as the default for flights. The policy code and model settings match Experiment 06.
- **Live results.** The published replay solved 4/4, including both Basic failures and both Forecast failures, at $0.00975180 grading cost. Dev passed 9/9 at $0.02972720. Implementation `e6415725a7ab8653f1329eabb803e43aeded7e77ab06d3e3286646947f06694d`.
- **Scope check.** The expression from both Basic replays evaluated to 11:00 for flight and train, 11:30 for a $130 coach, and 11:00 for a $131 coach. This verifies the concession's decision boundary.
- **Full Public check.** The complete run solved 59/60 and scored **90.85/100**, up from 56/60 and 87.73. All Reactive and Forecast episodes passed. Grading cost rose to $0.15861920, versus $0.15355200 for the earlier baseline. The run made 100 calls with $0.10951412 in estimated API spend. The effective estimated API guard was $0.1787.
- **Remaining failure.** In the second repeat of `travel-0ad5c8598537cc7671de`, the interpreter assigned the coach-only 11:30 concession to all modes except expensive coaches. It booked a flight that reached the client after the 11:00 deadline. The first repeat evaluated the same rule correctly and booked an eligible coach. The four-case targeted success did not eliminate this failure mode.
- **Decision.** Promote the exact tested implementation `e6415725a7ab8653f1329eabb803e43aeded7e77ab06d3e3286646947f06694d` to the working solver. Protected-file verification passed. The score gain came from travel outcomes while efficiency declined slightly.

## Experiment 08 — Send only the observation fields used for interpretation

- **Hypothesis.** The controller can evaluate bookings, holds, and ledger balances locally. The interpreter needs the arrived notices, current source references, case tier, and current virtual minute alongside the read documents and observed offers.
- **Change.** Project the model-facing observation to those four keys. Retain all documents, offers, and previous interpreted rules. The controller still uses the full simulator observation. Candidate branch point is Experiment 07.
- **Offline check.** Replayed 98 saved request packets through a stub API. Verified the exact retained fields, preserved documents and offers, and no mutation of original packets. The projection reduced serialized packet size from 804,384 to 631,437 bytes, or 21.5%. These are payload bytes. Actual token use, outcome, and dollars require a model run.
- **Cost finding.** In the previous full Public baseline, the 60 initial calls accounted for $0.08664240 of grading cost and the 39 subsequent calls accounted for $0.06690960. Initial calls alone exceeded the full Public efficiency allowance. Reducing refreshes will help, and initial interpretation also needs to get cheaper.
- **Live checks.** The batch had $0.06924364 available after reconciliation. A $0.025 estimated guard covers five targeted published cases, including the new coach-rule failure. A $0.040 guard covers Dev. The model and settings match the promoted Public baseline.
- **Results.** The targeted replay solved 4/5, with one recurrence of the coach-only arrival error. The promoted solver had solved 9/10 across its two repeats of the same five cases, also with one recurrence. Dev passed 9/9 with 18 calls. Dev input tokens fell from 97,246 to 85,354, or 12.2%. Grading cost fell from $0.02972720 to $0.02706800, or 8.9%.
- **Decision.** Keep this isolated until a stronger scope check and a more representative comparison verify the cost improvement without sacrificing arrivals. The highest verified full Public score remains Experiment 07's 90.85.

The batch used **$0.20686948 in estimated API spend** against the $0.25 cap. The full Public run accounted for $0.10951412. All reports completed with zero pending requests.

## Experiment 09 — Compact expression schema

- **Change.** On the projected observation candidate, use a shallow response schema. Allow compound contract expressions as JSON strings and decode them into the original expression form with duplicate-key rejection and the supplied validator. Scalar values remain typed.
- **Offline checks.** Confirmed rejection of duplicate expression keys, malformed JSON, invalid variables, and invalid scalar types. The original supplied schema remains intact.
- **Results.** GPT-5.6 Luna passed 4/5 targeted and 3/9 Dev, with $0.01434840 Dev grading cost. GPT-6 Luna at no reasoning passed 3/5 targeted and 3/9 Dev, with $0.00740680 Dev grading cost. Early failures ended episodes before a refresh, so the apparent spend reduction includes fewer completed calls.
- **Decision.** Discard both variants. The strict grammar was carrying useful constraints. Invalid operator objects, variable names, and malformed JSON suppressed correct interpretation before booking. Preserve the strict schema for the measured solver.

## Experiment 10 — Resolve a standalone weather update locally

- **Hypothesis.** Reuse the interpreted rules when a fresh operating report only resolves an explicit delay and no other evidence changes. The last full Public run had 20 such weather refreshes.
- **Change.** Keep episode-local prior evidence. When the current notice and versioned weather source both match the supported operating-report form and agree on mode, delay and time, update realized weather and clear that mode's resolved forecast. Require the same offers, unchanged non-weather documents and operational references, and refund authorities independent of the weather document. Fall back to the supplied interpreter for mixed, unfamiliar or conflicting evidence.
- **Offline checks.** Replayed all 60 previous Public episodes with recorded model replies. All outcomes reproduced and 20 refresh calls were bypassed, representing $0.03802720 of historical grading cost. Six modified packets with stale versions, amended sources, changed offers, mixed notices, or dependent contracts correctly stayed on the model path.
- **Live check.** The full Public run solved 60/60 and scored **92.01/100**. It used 80 calls and $0.11986240 in grading cost, down from 100 calls and $0.15861920 in Experiment 07. Estimated spend was $0.05101852 under a $0.135 guard. All 90 travel outcome points passed for the first time.
- **Decision.** Promote the tested implementation `dfa212651f0d786cda2fce43aaa5ee2bbec34372af6ad44fb8883ff53a4c449c`. Protected-file and loaded-source checks passed.

## Experiment 11 — GPT-6 Luna under the strict schema

- **Change.** Change only the model to GPT-6 Luna in Experiment 08's projected-context candidate. Preserve low reasoning effort and the typed expression schema.
- **Live checks.** The published regressions passed 5/5 at $0.004968 grading cost. Dev passed 9/9 at $0.01254290, down from $0.02706800 for the same projected packet and GPT-5.6 Luna. The Dev reduction was 53.7%.
- **Decision.** Advance the strict-schema model and projected context to the combined Public test.

## Experiment 12 — Combine local weather reuse with the cheaper typed interpreter

- **Change.** Start from Experiment 10 and apply Experiment 11's projected context only on paid interpreter calls. Switch the model to GPT-6 Luna at low effort. Weather reuse still checks the full operational evidence.
- **Budget check.** Earlier reconciled runs used $0.050302245 in estimated spend. The $0.135 Experiment 10 guard and $0.063 combined guard bring worst-case batch allocation to $0.248302245. Both Public runs use the same staff benchmark and three isolated workers.
- **Live check.** The complete Public run scored **94.73/100** with **60/60** complete episodes and full outcome points. The 80 calls cost $0.05088730 for grading and $0.03765112 in estimated API spend. Grading cost fell 67.9% from Experiment 07's $0.15861920.
- **Decision.** Promote the exact tested implementation `f49344c742a0f91e669a9e09d9648554fe2d912ebcff4ca24a35533218008404`. Verified the loaded source against the report and confirmed protected files were intact. The first 60 model calls contributed $0.03852170 and the other 20 contributed $0.01236560. The remaining $0.02681255 gap to the grading allowance calls for reducing initial interpretation costs as well as refreshes.

Experiments 09–12 used $0.13897188 in estimated API spend against the $0.25 batch cap. All runs completed with zero pending requests.

The local budget launcher now accepts an explicit worker count. This batch uses three isolated case workers. Each episode still uses the staff runner and shared run-level cost guard. Report and grade comparisons use cache-neutral costs. This batch observed $0.03320533 estimated spend on Experiment 09 before allocating $0.190 to the two independent runs.

## Experiment 13 — Compile complete initial requests from observed documents

- **Change.** Add a deterministic interpreter for supported initial requests. It requires complete matching clauses, agreement between the request and traveller profile, exact current spending and arrival source references, a consistent waiver version, and one matching fare authority across the available offers. It compiles the fixed or quote-based spending ceiling, the plain or mode-specific arrival requirement, and a fixed retained fare into the existing controller's expression format. The model path remains available for other forms.
- **Offline checks.** Replayed all 60 previous Public episodes against saved replies. All passed, and the candidate skipped 40 initial calls across Basic and Reactive. A newly appended restriction forced fallback. A quote test with a different carrier, deadline, uplift, and ceiling produced the revised answer from the source. Arrival concession boundaries were also checked.
- **Live results.** The full Public run scored **98.52/100** with all 60 outcomes, 40 calls, $0.02824230 grading cost and $0.01412086 estimated spend. Dev passed 9/9 at $0.01218990 grading cost. Implementation `d5f7c88e6b109b2a98f785bec8ab31e6502be774718874df2534359e7c7033bb`.
- **Decision.** Advance this candidate as the parent of the spending-amendment experiment. The remaining Public cost still exceeded the allowance by $0.00416755.

## Experiment 14 — Apply matching spending and carrier amendments locally

- **Change.** When a locally supported initial request receives its two recognized notices, check that the spending authority is newly versioned, all other source material is unchanged, the new document names the earlier ceiling, and every current offer still has the same fare authority. Compile the updated supplement with its mode, accessibility, arrival, and retained-fee conditions. Apply the independent carrier restriction and retain the other facts. Mixed or unfamiliar amendments continue through the model.
- **Offline checks.** All 60 previous outcomes replayed successfully with model replies needed only for 20 Forecast initializations. Tests covered the mode, price-independent accessibility check, arrival and retained-fee boundaries, an appended instruction, and changed fare authority. A counterfactual changed the supplemental ceiling, time and fee threshold and verified the expressions used the new values.
- **Live results.** The full Public run scored **100/100**, with 60/60 complete episodes, 90/90 outcome points, and 10/10 efficiency. The 20 calls used $0.01482420 grading cost against the $0.02407475 allowance, and $0.00671322 estimated spend. Dev passed 9/9.
- **Promotion and repeat.** Verified working solver digest `cff6c80e46f8fd52d34da1f800aa29f541ff431b07531ff051cf6e77553aeb82` against the perfect run and verified the protected files. The second full Public run scored **99.33/100**, solving 59/60 with full efficiency. Grading cost was $0.01432770. In the failed Forecast repeat, the initial model response compared a cancellation fee to the virtual deadline. That made the eligible recovery appear too expensive, so the planner kept the late itinerary. The first perfect score is verified, but the exact source did not repeat it.
- **Budget.** Experiments 13–14 reconciled to $0.03671908 estimated API spend.

## Experiment 15 — Compile the observed weather refund clause locally

- **Change.** For the supported provider clause, bind each offer to its observed, versioned fare document. Compile a refund only for exposed offers in the stated mode, with both the virtual cancellation deadline and actual operating-delay threshold. Preserve the ordinary retained charge for other offers. Override the interpreter's refund output only when every offer's clause is understood from its read authority. Other rules still use the typed model output.
- **Offline checks.** Replayed all 60 episodes from the 99.33 report with its recorded replies, including the originally faulty response. All 60 passed. Verified both condition boundaries, sheltered offers, and fallback for a missing current fare version. Changing the refund amount, cutoff, and threshold changed the compiled expression. Adding a new waiver clause triggered fallback.
- **Live checks.** The first full Public run and confirmation run each scored **100/100**, with 60/60 episodes and full points on every criterion. Each took 20 calls. Grading costs were **$0.01507370** and **$0.01428070** against the **$0.02407475** allowance. Dev passed 9/9. All runs completed with zero pending requests.
- **Decision.** Keep implementation `6e0a4e52286860b9db16d156791ee57e4eed67f96cb53bc20a9ffde6c9f522a7`. Verified that the working source and verified solver ZIP match both perfect runs. The ZIP contains the three allowed Python files and their manifest. Protected files passed verification.

Experiments 13–15 used **$0.05450615 in estimated API spend**, within the $0.25 batch cap. The verified result covers the published Public bank. The solver falls back to the model on unfamiliar documents, and staff evaluation on team-contributed and hidden cases remains unverified.

## Experiment L1 — Scope the interpreter instructions to the requested keys (2026-11-23)

- **Baseline.** `branch_louisa` at `443103b`. Public uses 0 calls, because local readers compile every Public document. On unseen wording (Dev plus team cases), cost is $0.000666 per episode, 1.66× the allowance. Recorded calls were about one third instructions, one third strict schema and one third case data.
- **Change.** `scoped_instructions` now builds instructions for only the keys and facts in the call's schema. It no longer repeats the expression grammar and field lists, which the strict schema already fixes. It keeps every semantic rule: candidate and booking meaning, `now`, quantifier binding, the ceiling example, and the refund and ceiling rules. `PROJECT_PROMPT` is split into named parts in `prompts.py`; the full-path text is unchanged. Scoped calls drop the waiver part when the waiver is not asked, and drop the exception-branch part for facts-only calls.
- **Offline.** Across the 27 recorded calls, instruction tokens fell from 26,523 to 15,072 (−43%).
- **Validation on the model path.** Two diagnostic solution copies, never submitted, switch off the wording-specific readers, so all 60 Public episodes go through the model. They differ only in the prompt.

  | Run | Success | Grading | Change |
  |---|---:|---:|---:|
  | Public diagnostic, old prompt | 60/60 | $0.04631 | |
  | Public diagnostic, new prompt | 60/60 | $0.04222 | −8.8% |
  | Dev, real solution (old run: $0.00617) | 9/9 | $0.00527 | −14.6% |
  | Team cases, real solution (old run: $0.00315) | 5/5 | $0.00267 | −15.4% |

- **Result.** Unseen-wording cost fell to $0.000567 per episode (1.41× the allowance, efficiency about 7.1, up from 6.0), with no outcome loss in 74 episodes. Output tokens, which include reasoning, did not change and are now 32–39% of cost.
- **Decision.** Keep.

## Experiment L2 — Read forecast and operating updates locally (2026-11-23)

- **Baseline.** L1 (`ee2bcba`). Each Forecast episode makes two weather-only calls: one when the forecast is still open, one when the outcome is reported. These are about 35% of Forecast cost.
- **Change.** `read_weather_event` handles an update made only of forecast/weather notices, with the weather forecast as the only changed document, without the model. Two forms are recognized, in any wording:
  - **Still open:** an uncertainty marker, no settled-outcome words, and no number (minute stamps included) that the earlier forecast did not already contain. The facts are kept.
  - **Resolved:** one announced mode, a realized-outcome marker, no hedge words, and a single delay value. Every free number in each text must be explained by the delay pattern, and the notice and document must agree. The reader sets `weather[mode]` and removes that mode's forecast.

  Anything else goes to the model as before.
- **Offline.** Replaying all 56 recorded weather calls gave the same weather values as the model in every case, with none deferred. The model kept a resolved forecast in 24 of the 56 calls. That is harmless, because the planner ignores a forecast whose `at` has passed. 14 hand-written traps all go to the model: a new estimate, a moved report time, a preliminary or hedged report, two modes, notice and document conflicting, unexplained figures, "did not exceed", an unannounced mode, and a mixed user update.
- **Live.**

  | Run | Success | Calls | Grading | Change vs L1 |
  |---|---:|---:|---:|---:|
  | Public, real solution | 60/60 (100/100) | 0 | $0 | |
  | Public, model-path diagnostic | 60/60 | 80 (was 100) | $0.03833 | −9.2% |
  | Dev | 9/9 | 12 | $0.00416 | −21% |
  | Team cases | 5/5 | 7 | $0.00245 | −8% |

  Forecast cost per episode on the model path fell from $0.000781 to $0.000566.
- **Result.** Unseen-wording cost (Dev plus team) is $0.000472 per episode, 1.18× the allowance (efficiency about 8.5). Cumulative change from `443103b`: −29%.
- **Decision.** Keep.

## Experiment L3 — Ask Reactive updates only for amended fields, and bind stray refund items (2026-11-23)

- **Baseline.** L2 (`4fd658c`). Every user update re-asked all three traveller facts, together with the traveller profile. Any topic word also triggered its field, even in "My spending authority … continue(s)". In recorded calls, the model returned those fields unchanged.
- **Change 1: `update_topics`.** Updates are split into clauses (on punctuation, plus "but", "while" and similar). A clause asks for a field when it mentions that topic; clock times count as arrival. A clause that only restates a rule is skipped: it has a continuation word (continue, unchanged, remain, keep, retain), no digits, and no change word outside the continuation phrase. Traveller facts are asked when a clause mentions access, carriers or preference, or names a carrier from the offers or the avoid list, in the update or in a changed document. Documents whose authority changed are still always re-asked.
- **Check.** I tested 27 update texts: those in Public, Dev and the team cases, the framework generator's templates, and 3 traps that pair a continuation word with a real change. No changed field is missed. One bug, a colon split inside "09:30", was found and fixed. The only extras are harmless over-asks.
- **Change 2: `bind_refund_items`.** The model-path Public diagnostic had 2 of 100 refund groups use `item.mode`/`item.weather_exposed` outside a quantifier. The framework rejects that ("item is available only inside a quantifier"), and the episode fails at 10/90. Nothing binds `item` there, so in a refund rule it can only mean the cancelled ticket, and the solver now renames it to `booking.*`. Across 398 recorded refund groups, both faulty ones are repaired to the form used by the passing repeats, and the other 396 are unchanged. The initial prompt is identical between the L2 and L3 runs (0/100 vs 2/100), so this is random variation between runs, not caused by L3. A third diagnostic failure was a Basic quote rule ("min" instead of "add"), also random; there is no local repair for it.
- **Live (final code).**

  | Run | Success | Grading |
  |---|---:|---:|
  | Public, real solution | 60/60 (100/100), 0 calls | $0 |
  | Dev | 9/9 | $0.00404 |
  | Team cases | 5/5 | $0.00224 |

  The model-path diagnostic of change 1 alone ran 57/60, the 3 failures described above. Reactive model-path cost did not move, because both Public updates genuinely amend budget and carriers. Team Reactive fell 15%, from $0.000656 to $0.000559 per episode.
- **Result.** Unseen-wording cost is $0.000449 per episode (1.12× the allowance, efficiency about 8.9). Cumulative change from `443103b`: −33%.
- **Decision.** Keep both.

## Submission of 2026-11-23

`f70eb4e` (L1–L3 on top of `branch_louisa`) was emailed for leaderboard grading. Its leaderboard result is still pending.

## Local stress banks (tools/stress_builder*.py, gitignored output in local_cases/)

The official set is 30 Public plus 90 cases we cannot see. Dev and team cases underestimate their cost and difficulty: Louisa's version scored 91.04 on the leaderboard, with $0.00102 per non-Public episode against $0.000666 locally. Three generated banks keep the template offers and correct contract answers, and each is validated and checked for solvable offers:

- **stress_v1 (19):** all text reworded, renamed documents, other line formats, and structural events Public and Dev never use (extra linked document, provider notice, transfer change, hotel bulletin replacement, a carrier ban only in a message, unfamiliar weather report wording). Louisa's version cost 1.40× its Dev and team cost here, against 1.53× on the leaderboard, so this bank predicts unfamiliar-case cost well.
- **stress_v2 (18):** harder rule logic: added and tiered supplements, derived deadlines, grouped ticket terms, relative or spelled amendments, split or combined updates.
- **stress_v3 (15):** the Reactive situations from the course slides at realistic times: an amendment, carrier ban or revised forecast at minute 6 or 8, interrupted confirmations, warned sellouts, mid-trip carrier bans, transfer changes and waiver revisions.

| Bank | Louisa `443103b` | Submitted `f70eb4e` |
|---|---|---|
| stress_v1 | 17/19, $0.000934 per episode | 17/19, $0.000774 per episode (−17%) |
| stress_v2 | 17/18 ×2, $0.000740 | 17/18 ×2, $0.000514 (−31%) |
| stress_v3 | — | **6/15 in both runs** |

The two stress_v1 failures and the one stress_v2 failure are case-design or timing issues explained below. **In stress_v3 all 9 failures were deterministic planner timing:** the supplied boot reads every source (minutes 0–6) and then claims the waiver alone (6–8). Any notice before minute 8 adds a 2-minute refresh, so the first confirmation lands at minute 13, after the minute-12 deadline. In Forecast, the recovery sales (closing at 14) are then missed as well.

## Experiment L4 — TimelyController and degenerate-expression repairs (2026-11-23)

- **TimelyController** (a subclass of the framework Controller in `policy.py`; offer choice, budgets, refunds and preparation rules are unchanged):
  1. The hotel bulletin leads the second read round, and when its evidence is unambiguous (one evidence type, one proof code, no archived or superseded wording) the claim fills the slot the last read round leaves idle.
  2. Otherwise the claim and the first hold share one batch. The plan assumes the claim succeeds, which only affects its budget check.
  3. A failed or superseded claim is retried once with the current interpreted evidence.
  4. A `stock_update` warning ("… for trip-X at virtual minute N") caps that offer's planning expiry at N.
  5. When the recovery window is closing as the first confirmation completes, the recovery is held in the same batch as the `status` check. The choice is the supplied `prepare()` logic without deferral.

  First confirmation moves from minute 11 to 9 (Basic, Reactive) and to 10 (Forecast). A wrong claim is harmless (`ok=False`, no violation).
- **Repairs of degenerate model output** (applied to every interpretation; across 946 recorded outputs, none becomes invalid and 3 crashing ones become valid):
  - a free `item.*` becomes `booking.*` in refund rules and `candidate.*` in spending or arrival rules;
  - inside the `holds` pool, expiry-versus-now and `item.status` tests become `true`, because the pool holds only live holds (the model sometimes inverted them or used status "live");
  - a `minimum` whose filter uses `item` but whose value is constant becomes `item.price`.
- **First attempt regressed** (Public 93.33): `hotel-bulletin` only enters the catalog after `hotel-terms` is read, so the original first batch is kept.

| Bank (final code) | Result |
|---|---|
| Public | 100/100, 0 calls (three runs) |
| Dev | 9/9 (two runs) |
| Team cases | 5/5 and 4/5 (team2-5, zero-reasoning misreading) |
| stress_v1 | 17/19 (stress-05 and stress-07: zero-reasoning outputs, both repaired by the final repairs) |
| stress_v2 | 18/18 |
| stress_v3 | **15/15** (was 6/15) |

  Cost per episode is unchanged.
- **Remaining risk: zero-reasoning calls.** At effort low, about 11% of calls return 0 reasoning tokens. Episodes with such a call failed 14% of the time (14/102), against 5% otherwise (27/548). Every random misreading in L4's runs came from one. Repairs cover the recurring structural forms; plain value errors (610 for 09:50, 145 for a conditional ceiling) remain.
- **Decision.** Keep.

## Experiment L5 — More planner rounds and no full interpretations for non-contract events (2026-11-23)

- **MAX_DECISIONS 12 → 30** (no API cost). Reactive and Forecast stress episodes already used up to 10 of the 12 planner rounds. One more event or rebooking would end the loop before the minute-28 handoff.
- **`compile_partially` accepts more update shapes** instead of returning None, which falls back to the full combined interpreter at about $0.0007 per call. In the L4 runs, 14 such calls made up about 21% of cost.
  - **No call** for provider notices, stock warnings and sellouts: no contract terms, so the previous interpretation is reused.
  - **Scoped calls:** `transfer` for a `transport_update`, `waiver` for a `document_update`.
  - **Extra documents** are sent as context with any expression request. An authority that links one is always interpreted, never read locally.
  - **A message-only user update** gets a scoped call: traveller facts always, plus the recognised topics, or every rule when no topic is recognisable.
  - **Weather facts** are re-asked only for forecast or weather events.
  - A changed document of unknown scope still uses the full call.

| Bank | L4 (`93f7ddf`) | L5 |
|---|---|---|
| Public | 100/100 | 100/100, 0 calls |
| Dev | 9/9 | 9/9 |
| Team cases | 5/5 | 5/5 |
| stress_v1 | 17/19 | 19/19, −7% cost |
| stress_v2 | 18/18 | 18/18 |
| stress_v3 | 15/15 | 15/15, −32% cost |
| All 66 model-path episodes | $0.000636 per episode, 14 full calls | **$0.000568 per episode (−11%), 3 full calls** |

- **Decision.** Keep.

## stress_v4 and Experiment L6 — claim before an early waiver cutoff (2026-11-23)

- **stress_v4 (9 cases, `tools/stress_builder_v4.py`)** covers situations not in stress_v1–v3:
  - a mid-trip preference switch, with a suitable offer in the new mode;
  - a preferred-mode offer that opens for sale at minute 16;
  - a budget cut for new commitments only;
  - 5-minute holds;
  - a waiver cutoff at minute 8 (Forecast and Reactive);
  - three events in one minute (amendment, transfer change, provider notice);
  - the deadline moved earlier and then later again;
  - step-free access required mid-trip while the booked ticket is not step-free.

  The truth fields, documents, fare lines and contract are updated together, and each case is validated and checked for feasible offers.
- **Results.** Submitted `f70eb4e`: 7/9; both early-waiver cases fail at 10/90. `73bf026`: 8/9 in two runs; its early claim saves the Reactive case. The Forecast case still fails, because no read slot is idle, so the claim rides with the first hold and completes exactly at the cutoff (minute 8). The unwaived USD 55 then counts against every ceiling, and nothing is affordable.
- **Change.** At boot, the claim also goes first when claiming after the reads would reach the bulletin's stated "before (virtual) minute N" cutoff. The reads then end at 8 instead of 6, and the first confirmation still lands at 11. With the usual minute-30 cutoff, nothing changes.
- **Result.** stress_v4 9/9; Public 100/100, 0 calls. **Decision.** Keep.

## Experiment L7 — Lean expression grammar for scoped calls (2026-11-23)

- **Measurement.** The initial call averages about 2,750 input tokens: schema about 1,080, instructions about 780, documents about 400, offers about 220 and the request notice about 200. Input is 66% of its cost. Across 1,862 recorded outputs, the following never appeared:
  - the predicate-level and value-level `if`, `in`, list values, `or` and `max`;
  - more than half of the variable names.

  Pruning only the names saved 130 tokens, because enums render compactly. Removing grammar branches saved more. Paired test calls on identical requests:

  | Request | Original | Lean | Saving |
  |---|---:|---:|---:|
  | With refunds | 3,630 tokens | 3,381 tokens | −6.9% |
  | Budget and arrival only | 2,200 tokens | 1,909 tokens | −13.2% |

- **Change.** `lean_definitions` drops:
  - the predicate `in` and `if` branches, and the value list and `if` branches;
  - timestamp, status and base-fare fields, `*.id`, `candidate/booking.expires_at` and four ledger subtotals;
  - all of `booking.*` unless refund groups are requested, because booking is empty before purchase.

  `or`, `max`, `sub`, `not`, `booking.price`, `hold_fee_usd`, `state.retained_fees` and `state.net_spend` stay. Only scoped calls use it; the full fallback keeps the supplied grammar. Every lean output is valid under the supplied grammar.
- **Live.** The first attempt was interrupted by an API connection outage (`request_error`, then the unknown-cost guard) and says nothing about the change. The rerun:

  | Runs | Episodes passed | Calls | Input tokens per call | Cost per episode |
  |---|---|---:|---:|---:|
  | L6 (`T6` + `T7_s4`) | 75/75 | 120 | 2,396 | $0.000559 |
  | **L7 (`T9`)** | **75/75** | 120 | 2,150 (−10%) | **$0.000519 (−7%)** |

  Dev and team cases now cost about the allowance (projected total 100).
- **Decision.** Keep.

## Leaderboard of `f70eb4e` and Experiment L8 — compact full call at effort medium (2026-11-23)

- **Leaderboard result for `f70eb4e`:** 89.14 (Louisa 91.04). Grading cost was $0.0914 against $0.0917, with 136 calls against 135, so the cost was unchanged. The scoped-path savings of L1–L3 therefore never reached the 90 non-Public cases. Their cost per call ($0.00067) matches a full fallback call (about $0.0007 locally), not a scoped one ($0.00042). The outcome drop (arrival −1.0, reliability −0.25, Basic −1.2) runs through code paths the version did not change, so it is most likely run-to-run variation in the full call.
- **Forced-full-path diagnostic.** A copy of the solver with `compile_partially` returning None routes every call through the full fallback, as the hidden cases do. It was run on Dev and stress_v1–v3 (61 episodes, 128 calls).

  | Full call | Success | Cost per episode | Zero-reasoning calls |
  |---|---|---:|---:|
  | Supplied instructions, low | 61/61 | $0.001416 | 25% |
  | Compact (scoped instructions with consent, lean grammar, trimmed offers), low | 58/61 and 57/61 | $0.001224 | 26–30% |
  | **Compact, medium** | **61/61 and 61/61** | $0.001536 | **0%** |

  At effort low, a quarter of the full calls return no reasoning at all (against about 11% of scoped calls), and those carried the misreadings.
- **Change.** `compact_full_request` gives the full call compact instructions (all keys and facts, including consent and waiver), the lean grammar with `booking.*` kept, and offers trimmed to `OFFER_KEYS`. `FULL_CALL_EFFORT = "medium"` applies to the full call only; scoped calls stay at the configured effort (low).
- **Expected leaderboard effect.** Efficiency about −0.4. If reasoning-free misreadings explain even half of the 13 arrival and 10 reliability failures, outcome rises 2–4 points.
- **stress_v5 (12 cases, `tools/stress_builder_v5.py`):**
  - **Full-path triggers:** an `approval-…` token format, two approval tokens, an amendment at minute 4 (before the first interpretation), two fare documents, archived bulletin evidence.
  - **Size:** 18–20 offers, long documents with distracting figures, 12 sources.
  - **Rule types:** a locked cheapest fare, refunds by carrier, two forecast modes.

  The approval format, the two tokens and the early amendment do reach the full path. Result: 10/12 with the real code and 10/12 forced full, with the same two deterministic planner failures:
  - **12 sources:** five extra boot reads delay the first confirmation past minute 12.
  - **Locked cheapest preferred flight:** booked first, so the minute-16 amendment cannot be met.
- **Decision.** Keep the compact full call at medium. Fix the two stress_v5 planner failures next.

## Experiment L9 — Read only contract sources before acting, and keep first bookings cancellable (2026-11-23)

- **Many sources (stress5-09).**
  - *Problem:* the supplied boot reads every catalog source before the first booking, and after a notice the supplied refresh reads all unread sources before interpreting. Five unrelated reference documents pushed the first confirmation past minute 12. Once they were deferred, they delayed the reaction to the minute-16 amendment past a refund cutoff instead.
  - *Fix:* `boot_sources` gives the sources a contract can depend on: the fixed trip sources, the operational and fare authorities, their `related` links, and any catalog ID named in a notice or in a source already read. Before an interpretation, only those (plus revised sources already held) are read. Other sources are read in idle time, replacing a wait of at least 2 minutes, which costs no virtual time. A source first read after boot counts as new context in `compile_partially`, not as an amendment.
- **Locked fare (stress5-10).**
  - *Problem:* the cheapest preferred flight was locked (refund null). The planner booked it, so the minute-16 amendment could not be met.
  - *Fix:* the first booking in Reactive and Forecast sorts by preference, then cancellability, then price. Basic, which has no later changes, is unchanged.
- **Result (two full runs).** Public 100/100. Dev, team and stress_v1–v5: **87/87 in both runs (174/174)**, at $0.000522 and $0.000528 per episode (unchanged).
- **Coverage audit of all 117 local cases.** Structural settings barely vary:
  - transfer equal for all modes (117/117);
  - fares 729 fee, 1 locked, 0 flexible;
  - step-free required in 116;
  - first-booking deadline always 12;
  - hold duration 16 in 116;
  - exposure mostly flight;
  - evidence type always cancel-reference;
  - 6 offers in 113.

  stress_v6 targets these settings, plus unusual scenarios.
- **Decision.** Keep.

## stress_v6 — varied case settings and unusual scenarios (2026-11-23)

- **Bank (17 cases, `tools/stress_builder_v6.py`):**
  - **Settings:** transfer differing by mode (also with a road closure); mixed flexible, fee and locked fares; step-free not required; first booking due at minute 9 or 10; 6-minute holds; evidence type disruption-letter; a single seat sold at minute 7.
  - **Unusual scenarios:** the preferred mode affordable only after a budget raise; a distracting message about the colleague; a deadline stated as terminal arrival; a per-ticket price cap besides the total; a weather report revised from 40 to 60 minutes; an amendment at minute 1; an interrupted reply plus an early amendment; a locked exposed flight under a forecast.
- **Result.**

  | Version | Success |
  |---|---|
  | Submitted `f70eb4e` | 12/17 (four first-service timing failures, plus the locked exposed flight) |
  | `7b036f8` | **17/17 in both runs** |

## Recording future experiments

For each candidate, record the date, pinned baseline and candidate, one hypothesis, source diff, input scope, evidence checks, repeat counts, outcome and cost, what the trace shows, and whether the change was kept. Use the runner's fresh output directories as the supporting evidence. Record discarded variants and incomplete runs alongside promoted ones.
