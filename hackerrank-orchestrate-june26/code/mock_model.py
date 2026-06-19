"""
mock_model.py - Deterministic zero-network model client.

WHAT:  This module will implement a mock model client that returns structured
       outputs derived from claim context and image availability.
WHY:   The build order is mock-first so the full pipeline can run, test, and
       evaluate deterministically before any paid Claude API calls are wired.
STEPS: Stub for STEPS.md Phase 4; created in Phase 0 item 3.
IN:    The same claim context and image list passed to the real model client.
OUT:   Deterministic schema-shaped responses in later phases.
"""
