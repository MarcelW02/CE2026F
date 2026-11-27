"""EDITABLE: instructions and role-specific extraction prompts."""
from framework.fp_agents import FP_EXTRACTION_ROLE_PROMPTS
from copy import deepcopy

PROJECT_PROMPT = (
    "Help the traveler repair the trip. Reply with ONLY the single JSON object required by the schema: no text, preamble or explanation before or after it. "
    "FORMAT RULE: facts.consent and facts.waiver.code must each be ONLY the bare literal code "
    "token copied from the observed text (one word, no spaces), e.g. 'consent-123456' or "
    "'proof-123456'. Never copy the sentence around the code, such as 'covers the outbound...'. "
    "ARRIVAL RULE: the base deadline T1 applies to every ticket unless an exception condition is met. "
    "Text like 'arrive by T1; I can accept T2 when C; that concession is withdrawn when D' compiles to "
    "if (C and not D) then T2 else T1. Tickets outside C (other modes, other price ranges) keep the "
    "stricter T1; never give the relaxed time to tickets that fail the stated condition. "
    "TIME RULE: a condition such as 'by virtual minute N' or 'no later than minute N' compares the clock "
    "variable state.now with N (state.now <= N). Never compare a fee, price or other field with a minute number."
)
ROLE_PROMPTS = deepcopy(FP_EXTRACTION_ROLE_PROMPTS)

# TODO: replace PROJECT_PROMPT and/or edit ROLE_PROMPTS for your context design.
# PROJECT_PROMPT is appended to every supplied hybrid extraction request.
# ROLE_PROMPTS applies only to separately scoped, non-Basic hybrid_multi calls
# when the requested domain count meets ROUTE_THRESHOLD. Basic, hybrid_single
# and combined fallback requests use the provided combined extractor instead.
# Inspect the saved request role/instructions to check which prompt was used.
