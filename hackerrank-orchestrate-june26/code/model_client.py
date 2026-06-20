"""
model_client.py - Model client interface boundary.

WHAT:  This module defines the shared model-client interface for claim-review
       model implementations. The real Claude implementation is intentionally
       left for STEPS Phase 8 so Phase 4 stays zero-network.
WHY:   A single interface lets the mock and real model clients be swapped
       without changing pipeline, aggregation, or evaluation logic.
STEPS: Implements STEPS.md Phase 4 item 1.
IN:    Claim context dictionaries and resolved usable image payloads.
OUT:   Per-image plus claim-level response dictionaries.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ModelClient(ABC):
    """Define the one model boundary used by mock and real VLM clients.

    The interface stays deliberately small because the pipeline should not know
    whether responses come from a deterministic mock or a paid API call. Phase 4
    only establishes the contract; concrete clients decide how to interpret the
    context and image payloads.
    """

    @abstractmethod
    def predict(
        self,
        claim_context: Dict[str, Any],
        images: List[Any],
    ) -> Dict[str, Any]:
        """Return per-image and claim-level JSON-like model output.

        Args:
            claim_context: Structured row, extraction, history, prefilter, and
                requirement context assembled by later pipeline phases.
            images: Resolved image references or metadata records in input order.

        Returns:
            A dictionary with per-image and claim-level response sections.
        """
