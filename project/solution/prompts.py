"""EDITABLE: instructions and role-specific extraction prompts."""
from framework.fp_agents import FP_EXTRACTION_ROLE_PROMPTS
from copy import deepcopy

PROJECT_PROMPT = """Interpret the current lead outbound using the supplied evidence.
For consent, copy just the literal approval token from the applicable request.
Exclude surrounding prose, punctuation, and the word "approval" itself.
Preserve the current token when a partial update does not replace it.
For the waiver, copy the exact evidence type and proof token from the current
hotel bulletin, and use that source's version. The evidence type is the named
item the hotel requires. Do not output a description of the charge or waiver.
Apply only arrived amendments and keep unrelated rules. Preserve every stated
condition in the spending, arrival, and refund expressions.
For a default with an exception and an exception to that exception, test each
branch: default for candidates outside the exception, modified value only
for candidates satisfying the full exception, and the stated override for
the narrower condition. In particular, a mode-specific later arrival applies
only to that mode, even when another condition restricts the concession."""
ROLE_PROMPTS = deepcopy(FP_EXTRACTION_ROLE_PROMPTS)

# TODO: replace PROJECT_PROMPT and/or edit ROLE_PROMPTS for your context design.
# PROJECT_PROMPT is appended to every supplied hybrid extraction request.
# ROLE_PROMPTS applies only to separately scoped, non-Basic hybrid_multi calls
# when the requested domain count meets ROUTE_THRESHOLD. Basic, hybrid_single
# and combined fallback requests use the provided combined extractor instead.
# Inspect the saved request role/instructions to check which prompt was used.
