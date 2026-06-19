"""
cache.py - Stable content-hash result cache.

WHAT:  This module will compute cache keys from claim-row fields, image bytes,
       and the prompt version, then persist and load model results.
WHY:   Local caching makes re-runs deterministic and avoids unnecessary Claude
       calls during evaluation and final output generation.
STEPS: Stub for STEPS.md Phase 6; created in Phase 0 item 3.
IN:    Claim rows, resolved image paths, prompt version, and model responses.
OUT:   Stable cache keys and cached response records in later phases.
"""
