"""
aggregate.py - Claim-level aggregation from model and pre-filter outputs.

WHAT:  This module will turn per-image model judgments plus deterministic
       pre-filter signals into a raw claim-level output row.
WHY:   Aggregation is separated from validation so business decisions such as
       selective supporting image IDs and history-as-risk remain reviewable.
STEPS: Stub for STEPS.md Phase 6; created in Phase 0 item 3.
IN:    Model responses, pre-filter results, extracted claim data, and history.
OUT:   Raw output dictionaries ready for validation in later phases.
"""
