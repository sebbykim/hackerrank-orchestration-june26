"""
model_client.py - Model client interface and Claude implementation boundary.

WHAT:  This module will define the shared model-client interface and the real
       Claude vision implementation that returns structured claim-review JSON.
WHY:   A single interface lets the mock and real model clients be swapped
       without changing pipeline, aggregation, or evaluation logic.
STEPS: Stub for STEPS.md Phases 4 and 8; created in Phase 0 item 3.
IN:    Claim context dictionaries and resolved usable image payloads.
OUT:   Schema-shaped model responses in later phases.
"""
