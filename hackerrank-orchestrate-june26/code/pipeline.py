"""
pipeline.py - End-to-end per-claim orchestration.

WHAT:  This module orchestrates loading context, pre-filtering images,
       extracting claims, invoking the injected model client, aggregating,
       validating, caching, and returning one output row per input claim.
WHY:   The full design pipeline needs a single coordination layer while keeping
       IO, image checks, model calls, aggregation, validation, and cache logic
       independently testable.
STEPS: Implements STEPS.md Phase 7 item 1.
IN:    Claim rows, supporting data indexes, and a model client implementation.
OUT:   Validated output rows.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from aggregate import aggregate
from cache import cache_key, load_cached_response, write_cached_response
from claim_extraction import extract_claim
from constants import (
    CACHE_DIR,
    CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
    CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
    COL_CLAIM_OBJECT,
    COL_CLAIM_STATUS,
    COL_CLAIM_STATUS_JUSTIFICATION,
    COL_EVIDENCE_STANDARD_MET,
    COL_EVIDENCE_STANDARD_MET_REASON,
    COL_IMAGE_PATHS,
    COL_ISSUE_TYPE,
    COL_OBJECT_PART,
    COL_RISK_FLAGS,
    COL_SEVERITY,
    COL_SUPPORTING_IMAGE_IDS,
    COL_USER_CLAIM,
    COL_USER_ID,
    COL_VALID_IMAGE,
    ISSUE_TYPE_UNKNOWN,
    MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT,
    MODEL_CONTEXT_KEY_EXTRACTED_CLAIM,
    MODEL_CONTEXT_KEY_HISTORY,
    MODEL_CONTEXT_KEY_INPUT_ROW,
    MODEL_CONTEXT_KEY_PREFILTER,
    OBJECT_PART_UNKNOWN,
    OUTPUT_BOOLEAN_FALSE,
    PIPELINE_FALLBACK_EVIDENCE_REASON,
    PIPELINE_FALLBACK_STATUS_JUSTIFICATION,
    RISK_FLAG_MANUAL_REVIEW_REQUIRED,
    SEVERITY_UNKNOWN,
    VALIDATE_SUPPORTING_IMAGE_IDS_NONE,
)
from io_loaders import (
    EvidenceRequirementIndex,
    Row,
    load_claims,
    load_evidence_requirements,
    load_history,
    match_evidence_requirement,
    resolve_image_paths,
)
from mock_model import MockModelClient
from model_client import ModelClient
from prefilter import prefilter_claim
from validate import OutputRow, clamp_and_validate


HistoryIndex = Mapping[str, Row]


def _fallback_output_row(row: Mapping[str, str]) -> OutputRow:
    """Return a valid deterministic fallback row for one failed claim.

    Phase 7 must not abort the batch for a single row failure. The fallback is
    deliberately conservative: no usable evidence, no supporting image, and a
    manual-review risk.
    """
    raw_output = {
        COL_USER_ID: row.get(COL_USER_ID, ""),
        COL_IMAGE_PATHS: row.get(COL_IMAGE_PATHS, ""),
        COL_USER_CLAIM: row.get(COL_USER_CLAIM, ""),
        COL_CLAIM_OBJECT: row.get(COL_CLAIM_OBJECT, ""),
        COL_EVIDENCE_STANDARD_MET: OUTPUT_BOOLEAN_FALSE,
        COL_EVIDENCE_STANDARD_MET_REASON: PIPELINE_FALLBACK_EVIDENCE_REASON,
        COL_RISK_FLAGS: [RISK_FLAG_MANUAL_REVIEW_REQUIRED],
        COL_ISSUE_TYPE: ISSUE_TYPE_UNKNOWN,
        COL_OBJECT_PART: OBJECT_PART_UNKNOWN,
        COL_CLAIM_STATUS: CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
        COL_CLAIM_STATUS_JUSTIFICATION: PIPELINE_FALLBACK_STATUS_JUSTIFICATION,
        COL_SUPPORTING_IMAGE_IDS: VALIDATE_SUPPORTING_IMAGE_IDS_NONE,
        COL_VALID_IMAGE: OUTPUT_BOOLEAN_FALSE,
        COL_SEVERITY: SEVERITY_UNKNOWN,
    }
    return clamp_and_validate(raw_output)


def _claim_context(
    row: Mapping[str, str],
    history: Mapping[str, str],
    prefilter_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Assemble the context object passed into the model client.

    This keeps `process_claim` readable while making the exact context fields
    explicit for prompt construction and cache debugging.
    """
    extracted_claim = extract_claim(row[COL_USER_CLAIM], row[COL_CLAIM_OBJECT])
    return {
        MODEL_CONTEXT_KEY_INPUT_ROW: dict(row),
        MODEL_CONTEXT_KEY_EXTRACTED_CLAIM: extracted_claim,
        MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT: match_evidence_requirement(
            row[COL_CLAIM_OBJECT],
            extracted_claim[CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE],
        ),
        MODEL_CONTEXT_KEY_HISTORY: dict(history),
        MODEL_CONTEXT_KEY_PREFILTER: prefilter_result,
    }


def process_claim(
    row: Row,
    history: HistoryIndex,
    requirements: EvidenceRequirementIndex,
    model_client: ModelClient,
    cache_dir: Path = CACHE_DIR,
) -> OutputRow:
    """Run the full Phase 7 pipeline for one claim row.

    Args:
        row: Input claim row from claims.csv.
        history: User-history rows keyed by user_id.
        requirements: Evidence requirement index loaded before processing.
        model_client: Injected model client, mock-only in Phase 7.
        cache_dir: Directory for local model response cache files.

    Returns:
        A validated output row in exact output schema order.
    """
    try:
        if not requirements:
            load_evidence_requirements()
        images = resolve_image_paths(row[COL_IMAGE_PATHS])
        prefilter_result = prefilter_claim(images)
        history_row = history.get(row[COL_USER_ID], {})
        claim_context = _claim_context(row, history_row, prefilter_result)
        key = cache_key(row, images)
        cached_response = load_cached_response(key, cache_dir)
        if cached_response is None:
            model_response = model_client.predict(claim_context, images)
            write_cached_response(key, model_response, cache_dir)
        else:
            model_response = cached_response
        return clamp_and_validate(
            aggregate(model_response, prefilter_result, history_row)
        )
    except Exception:
        return _fallback_output_row(row)


def run_smoke_test() -> None:
    """Exercise the Phase 7 per-row mock pipeline on a real test claim.

    Raises:
        AssertionError: If processing fails to return a validated row or if the
            cache path changes output across repeated calls.
    """
    rows = load_claims()
    history = load_history()
    requirements = load_evidence_requirements()
    client = MockModelClient()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        first_output = process_claim(rows[0], history, requirements, client, cache_dir)
        second_output = process_claim(rows[0], history, requirements, client, cache_dir)
        assert first_output == second_output


if __name__ == "__main__":
    run_smoke_test()
