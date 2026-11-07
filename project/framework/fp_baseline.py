"""Registered Public allowance; historical measurement is identified separately."""
from .fp_cases import FP_PUBLIC_CASES
from .evaluation_protocol import cost_allowance
FP_BASELINE = cost_allowance(FP_PUBLIC_CASES)
