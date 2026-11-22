# Team 2 final project experiment log

The target is a 100/100 benchmark score on the staff evaluation. The development gate is 60/60 complete Public episodes with cache-neutral grading cost at or below $0.02407475. The staff evaluation uses 120 episodes and a $0.04814950 allowance. See the [staff scoring guide](https://github.com/jhleepidl/CE2026F/blob/7b0f4197de9826f3ff3081f2317ddcb74f678da7/project/README.md#7-understand-the-100-point-score).

## November 15, 2026 baseline

Staff v10 commit `7b0f4197de9826f3ff3081f2317ddcb74f678da7`. At this stage, the working solver used GPT-5.6 Luna at low effort, a combined interpreter, context refresh, precaution, and a prompt requiring literal consent and current waiver evidence. The original v10 solver remains available as a historical control.

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

## Move beyond wording-specific parsers

The branch removed parsers that matched specific contract wording. GPT-6 Luna reads the current spending and arrival authorities alongside their linked documents. Its compact expressions preserve ordered exceptions and are validated before the planner evaluates live quotes. Scoped amendment and weather requests carry forward unchanged rules. When refreshed arrivals corroborate an operating delay, the weather update uses that evidence. The planner can evaluate several delays from the same forecast report together.

Forecast compilation produces fare rules by source and version so compatible new offers can use the same rules. The booking-first path defers refund interpretation until a plausible replacement needs it, then uses the fare terms observed at purchase. The booking-only path uses GPT-6 Luna. A failed no-reasoning initial call gets a low-effort retry only when recorded usage shows that it reached its output limit.

## Forecast spending scope and client-clock repair

The pre-repair Public run passed 59/60 and scored 97.33/100. The missed episode applied the original ticket's weather exposure to the replacement spending allowance and subtracted terminal transfer from a client-site deadline. That combination blocked a recovery hold before the sale closed.

The repair checks for those patterns and sends only the affected spending or arrival fields for review, with their observed authorities and linked definitions. The review distinguishes the service whose delay triggers an allowance from the tickets the allowance covers. The planner adds transfer to the itinerary's terminal arrival. A written offset can still change the deadline. The offline replay recovered the missed episode, and a second fixture verified that an invalid mode could be retried in isolation while keeping the accepted spending rule.

## Current solver verification

The November 16 Dev and Public reports both recorded the exact three solver files in `eb357ec`. Their implementation SHA-256 is `a9320e9c433675b32c74be6acb3cd6815c594b28d3988f9e19711683f2632dfd`.

| Run | Successful episodes | Outcome points | Model calls | Grading cost (USD) | Public score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dev | 9/9 | 90/90 | 21 | $0.00484690 | — |
| Public before the scope and clock repair | 59/60 | 89.33/90 | 132 | $0.03012000 | 97.33/100 |
| Public with the repair | 60/60 | 90/90 | 133 | $0.03038830 | 97.92/100 |

The current solver passed both repetitions of the previously missed Public case. It earned full outcome points, with grading cost above the $0.02407475 allowance. Separate local stress runs passed 9/9 on the new wording variations, 9/9 on the linked-source Forecast repeat, and 7/9 on the combined-condition repeat. Both remaining misses involved interpreting the wording around an operator name as part of its identifier. These runs measure local performance. See the [course scoring guide](project/README.md#7-understand-the-100-point-score) for the official evaluation.

## Recording future experiments

For each candidate, record the date, pinned baseline and candidate, one hypothesis, source diff, input scope, evidence checks, repeat counts, outcome and cost, what the trace shows, and whether the change was kept. Use the runner's fresh output directories as the supporting evidence. Record discarded variants and incomplete runs alongside promoted ones.
