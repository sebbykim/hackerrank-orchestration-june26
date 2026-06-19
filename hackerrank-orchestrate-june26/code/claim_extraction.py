"""
claim_extraction.py - Deterministic text-claim extraction.

WHAT:  This module will convert a user claim transcript into a structured
       extracted-claim dictionary containing claimed issue type, object part,
       severity hint, language, uncertainty, and evidence needs.
WHY:   Claim extraction is kept separate so multilingual and hedged user text
       can guide both the mock model and the real VLM prompt consistently.
STEPS: Stub for STEPS.md Phase 3; created in Phase 0 item 3.
IN:    user_claim text and the provided claim_object value.
OUT:   A stable extracted-claim structure in later phases.
"""
