"""
pipeline.py - End-to-end per-claim orchestration.

WHAT:  This module will orchestrate loading context, pre-filtering images,
       extracting claims, invoking the injected model client, aggregating,
       validating, caching, and returning one output row per input claim.
WHY:   The full design pipeline needs a single coordination layer while keeping
       IO, image checks, model calls, aggregation, validation, and cache logic
       independently testable.
STEPS: Stub for STEPS.md Phase 7; created in Phase 0 item 3.
IN:    Claim rows, supporting data indexes, and a model client implementation.
OUT:   Validated output rows in later phases.
"""
