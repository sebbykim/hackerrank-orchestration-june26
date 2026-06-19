"""
validate.py - Output clamping and consistency invariants.

WHAT:  This module will clamp output fields to allowed values and enforce row
       consistency invariants before CSV writing or metric comparison.
WHY:   Deterministic validation is the hard guard against model drift,
       out-of-vocabulary labels, unsupported image IDs, and schema mismatch.
STEPS: Stub for STEPS.md Phase 6; created in Phase 0 item 3.
IN:    Raw output dictionaries and the set of image IDs present in the claim.
OUT:   Schema-valid rows in the exact output column order in later phases.
"""
