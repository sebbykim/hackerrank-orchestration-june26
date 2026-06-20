"""
mock_model.py - Deterministic zero-network model client.

WHAT:  This module implements a mock model client that returns structured
       outputs derived from claim context and image availability. It never
       calls a network service and never uses randomness.
WHY:   The build order is mock-first so the full pipeline can run, test, and
       evaluate deterministically before any paid Claude API calls are wired.
STEPS: Implements STEPS.md Phase 4 items 2-3.
IN:    The same claim context and image list passed to the real model client.
OUT:   Deterministic per-image plus claim-level response dictionaries.
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping

from claim_extraction import extract_claim
from constants import (
    ALLOWED_ISSUE_TYPES,
    ALLOWED_OBJECT_PARTS_BY_OBJECT,
    ALLOWED_SEVERITY,
    CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
    CLAIM_STATUS_SUPPORTED,
    CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
    CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART,
    CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED,
    CLAIM_EXTRACTION_KEY_SEVERITY_HINT,
    CLAIM_EXTRACTION_KEY_UNCERTAINTY,
    CLAIM_UNCERTAINTY_LOW,
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
    MOCK_EVIDENCE_REASON_NOT_ENOUGH_INFORMATION,
    MOCK_EVIDENCE_REASON_SUPPORTED,
    MOCK_REASON_NON_SUPPORTING_IMAGE,
    MOCK_REASON_SUPPORTING_IMAGE,
    MOCK_REASON_UNUSABLE_IMAGE,
    MOCK_STATUS_JUSTIFICATION_NOT_ENOUGH_INFORMATION,
    MOCK_STATUS_JUSTIFICATION_SUPPORTED,
    MODEL_CLAIM_KEY_EVIDENCE_NEEDED,
    MODEL_CLAIM_KEY_UNCERTAINTY,
    MODEL_CONFIDENCE_NOT_SUPPORTING,
    MODEL_CONFIDENCE_SUPPORTING,
    MODEL_CONTEXT_KEY_EXTRACTED_CLAIM,
    MODEL_CONTEXT_KEY_INPUT_ROW,
    MODEL_IMAGE_KEY_CONFIDENCE,
    MODEL_IMAGE_KEY_EVIDENCE_STANDARD_MET,
    MODEL_IMAGE_KEY_IMAGE_ID,
    MODEL_IMAGE_KEY_ISSUE_TYPE,
    MODEL_IMAGE_KEY_OBJECT_PART,
    MODEL_IMAGE_KEY_REASON,
    MODEL_IMAGE_KEY_RISK_FLAGS,
    MODEL_IMAGE_KEY_SEVERITY,
    MODEL_IMAGE_KEY_SUPPORTS_CLAIM,
    MODEL_IMAGE_KEY_VALID_IMAGE,
    MODEL_RESPONSE_KEY_CLAIM_LEVEL,
    MODEL_RESPONSE_KEY_PER_IMAGE,
    MODEL_UNKNOWN_IMAGE_ID,
    OBJECT_PART_UNKNOWN,
    PREFILTER_KEY_DECODE_OK,
    PREFILTER_KEY_IMAGE_ID,
    RISK_FLAG_NONE,
    SAMPLE_CSV,
    SEVERITY_UNKNOWN,
)
from io_loaders import load_sample_claims, resolve_image_paths
from model_client import ModelClient


ImagePayload = Any


def _image_id(image: ImagePayload) -> str:
    """Extract a stable image ID from supported Phase 4 image payload shapes.

    The smoke path passes resolved `(image_id, path)` tuples, while later
    phases may pass dictionaries from the prefilter. Supporting both keeps this
    mock deterministic without forcing a premature pipeline payload class.
    """
    if isinstance(image, Mapping):
        return str(
            image.get(MODEL_IMAGE_KEY_IMAGE_ID)
            or image.get(PREFILTER_KEY_IMAGE_ID)
            or MODEL_UNKNOWN_IMAGE_ID
        )
    if isinstance(image, tuple) and image:
        return str(image[0])
    if isinstance(image, Path):
        return image.stem
    return MODEL_UNKNOWN_IMAGE_ID


def _image_is_usable(image: ImagePayload) -> bool:
    """Decide mock usability from prefilter metadata when it is present.

    Raw resolved image tuples have no prefilter signal in Phase 4, so the mock
    treats them as usable. When later phases pass prefilter dictionaries, an
    explicit decode failure is honored.
    """
    if isinstance(image, Mapping) and PREFILTER_KEY_DECODE_OK in image:
        return bool(image[PREFILTER_KEY_DECODE_OK])
    return True


def _extract_claim_from_context(claim_context: Dict[str, Any]) -> Dict[str, str]:
    """Read or derive the extracted-claim block used by the mock response.

    Phase 4 smoke tests build context from rows directly, but later phases can
    provide a precomputed extraction. Deriving only when missing keeps the mock
    deterministic while preserving the intended pipeline dependency.
    """
    extracted_claim = claim_context.get(MODEL_CONTEXT_KEY_EXTRACTED_CLAIM)
    if isinstance(extracted_claim, dict):
        return {
            CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE: str(
                extracted_claim.get(
                    CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
                    ISSUE_TYPE_UNKNOWN,
                )
            ),
            CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART: str(
                extracted_claim.get(
                    CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART,
                    OBJECT_PART_UNKNOWN,
                )
            ),
            CLAIM_EXTRACTION_KEY_SEVERITY_HINT: str(
                extracted_claim.get(
                    CLAIM_EXTRACTION_KEY_SEVERITY_HINT,
                    SEVERITY_UNKNOWN,
                )
            ),
            CLAIM_EXTRACTION_KEY_UNCERTAINTY: str(
                extracted_claim.get(
                    CLAIM_EXTRACTION_KEY_UNCERTAINTY,
                    CLAIM_UNCERTAINTY_LOW,
                )
            ),
            CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED: str(
                extracted_claim.get(CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED, "")
            ),
        }

    input_row = claim_context.get(MODEL_CONTEXT_KEY_INPUT_ROW, claim_context)
    user_claim = str(input_row.get(COL_USER_CLAIM, ""))
    claim_object = str(input_row.get(COL_CLAIM_OBJECT, ""))
    return extract_claim(user_claim, claim_object)


def _allowed_issue_type(issue_type: str) -> str:
    """Clamp mock issue output to the locked allowed-value list.

    The mock echoes extraction when possible, but the interface must already be
    safe against out-of-vocabulary values before the validator phase exists.
    """
    if issue_type in ALLOWED_ISSUE_TYPES:
        return issue_type
    return ISSUE_TYPE_UNKNOWN


def _allowed_object_part(claim_object: str, object_part: str) -> str:
    """Clamp object-part output using the object-specific allowed set.

    Object part values are scoped by claim object in the problem contract, so a
    globally valid-looking value still has to be checked against the row object.
    """
    allowed_parts = ALLOWED_OBJECT_PARTS_BY_OBJECT.get(claim_object, frozenset())
    if object_part in allowed_parts:
        return object_part
    return OBJECT_PART_UNKNOWN


def _allowed_severity(severity: str) -> str:
    """Clamp severity output to the locked allowed-value list.

    This keeps Phase 4 response values compatible with the output validator that
    will be added later.
    """
    if severity in ALLOWED_SEVERITY:
        return severity
    return SEVERITY_UNKNOWN


def _per_image_response(
    image: ImagePayload,
    supports_claim: bool,
    issue_type: str,
    object_part: str,
    severity: str,
) -> Dict[str, Any]:
    """Build one deterministic per-image response record.

    The first usable image is marked supporting by design for Phase 4. Other
    images remain available as context without pretending the mock inspected
    them visually.
    """
    usable = _image_is_usable(image)
    if not usable:
        reason = MOCK_REASON_UNUSABLE_IMAGE
    elif supports_claim:
        reason = MOCK_REASON_SUPPORTING_IMAGE
    else:
        reason = MOCK_REASON_NON_SUPPORTING_IMAGE

    return {
        MODEL_IMAGE_KEY_IMAGE_ID: _image_id(image),
        MODEL_IMAGE_KEY_VALID_IMAGE: usable,
        MODEL_IMAGE_KEY_SUPPORTS_CLAIM: supports_claim,
        MODEL_IMAGE_KEY_EVIDENCE_STANDARD_MET: supports_claim,
        MODEL_IMAGE_KEY_ISSUE_TYPE: issue_type if supports_claim else ISSUE_TYPE_UNKNOWN,
        MODEL_IMAGE_KEY_OBJECT_PART: object_part if supports_claim else OBJECT_PART_UNKNOWN,
        MODEL_IMAGE_KEY_SEVERITY: severity if supports_claim else SEVERITY_UNKNOWN,
        MODEL_IMAGE_KEY_RISK_FLAGS: [RISK_FLAG_NONE],
        MODEL_IMAGE_KEY_CONFIDENCE: (
            MODEL_CONFIDENCE_SUPPORTING
            if supports_claim
            else MODEL_CONFIDENCE_NOT_SUPPORTING
        ),
        MODEL_IMAGE_KEY_REASON: reason,
    }


class MockModelClient(ModelClient):
    """Return deterministic model-shaped responses without calling an API.

    The mock exists so loaders, pipeline wiring, aggregation, and evaluation can
    be developed against the model boundary before any Claude client is added.
    It deliberately uses simple input-derived behavior: first usable image
    supports the extracted claim, all other fields are clamped defaults.
    """

    def predict(
        self,
        claim_context: Dict[str, Any],
        images: List[Any],
    ) -> Dict[str, Any]:
        """Produce a stable per-image plus claim-level response.

        Args:
            claim_context: Input row and optional extracted claim context.
            images: Resolved image tuples or prefilter image dictionaries.

        Returns:
            A deterministic response dictionary with `per_image` and
            `claim_level` sections.
        """
        extracted_claim = _extract_claim_from_context(claim_context)
        input_row = claim_context.get(MODEL_CONTEXT_KEY_INPUT_ROW, claim_context)
        claim_object = str(input_row.get(COL_CLAIM_OBJECT, ""))

        issue_type = _allowed_issue_type(
            extracted_claim[CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE]
        )
        object_part = _allowed_object_part(
            claim_object,
            extracted_claim[CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART],
        )
        severity = _allowed_severity(
            extracted_claim[CLAIM_EXTRACTION_KEY_SEVERITY_HINT]
        )

        first_usable_image_id = None
        per_image = []
        for image in images:
            is_first_supporting = first_usable_image_id is None and _image_is_usable(image)
            if is_first_supporting:
                first_usable_image_id = _image_id(image)
            per_image.append(
                _per_image_response(
                    image,
                    is_first_supporting,
                    issue_type,
                    object_part,
                    severity,
                )
            )

        has_supporting_image = first_usable_image_id is not None
        claim_level = {
            COL_USER_ID: str(input_row.get(COL_USER_ID, "")),
            COL_IMAGE_PATHS: str(input_row.get(COL_IMAGE_PATHS, "")),
            COL_USER_CLAIM: str(input_row.get(COL_USER_CLAIM, "")),
            COL_CLAIM_OBJECT: claim_object,
            COL_EVIDENCE_STANDARD_MET: has_supporting_image,
            COL_EVIDENCE_STANDARD_MET_REASON: (
                MOCK_EVIDENCE_REASON_SUPPORTED
                if has_supporting_image
                else MOCK_EVIDENCE_REASON_NOT_ENOUGH_INFORMATION
            ),
            COL_RISK_FLAGS: [RISK_FLAG_NONE],
            COL_ISSUE_TYPE: issue_type if has_supporting_image else ISSUE_TYPE_UNKNOWN,
            COL_OBJECT_PART: object_part if has_supporting_image else OBJECT_PART_UNKNOWN,
            COL_CLAIM_STATUS: (
                CLAIM_STATUS_SUPPORTED
                if has_supporting_image
                else CLAIM_STATUS_NOT_ENOUGH_INFORMATION
            ),
            COL_CLAIM_STATUS_JUSTIFICATION: (
                MOCK_STATUS_JUSTIFICATION_SUPPORTED
                if has_supporting_image
                else MOCK_STATUS_JUSTIFICATION_NOT_ENOUGH_INFORMATION
            ),
            COL_SUPPORTING_IMAGE_IDS: (
                [first_usable_image_id] if has_supporting_image else []
            ),
            COL_VALID_IMAGE: has_supporting_image,
            COL_SEVERITY: severity if has_supporting_image else SEVERITY_UNKNOWN,
            MODEL_CLAIM_KEY_UNCERTAINTY: extracted_claim[
                CLAIM_EXTRACTION_KEY_UNCERTAINTY
            ],
            MODEL_CLAIM_KEY_EVIDENCE_NEEDED: extracted_claim[
                CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED
            ],
        }
        return {
            MODEL_RESPONSE_KEY_PER_IMAGE: per_image,
            MODEL_RESPONSE_KEY_CLAIM_LEVEL: claim_level,
        }


def _sample_context(row: Dict[str, str]) -> Dict[str, Any]:
    """Build the minimal Phase 4 context used by the smoke test.

    The later pipeline will add history, requirements, and prefilter context;
    this smoke test only needs enough structure to prove the mock contract is
    stable for every labeled sample row.
    """
    return {
        MODEL_CONTEXT_KEY_INPUT_ROW: row,
        MODEL_CONTEXT_KEY_EXTRACTED_CLAIM: extract_claim(
            row[COL_USER_CLAIM],
            row[COL_CLAIM_OBJECT],
        ),
    }


def run_smoke_test() -> None:
    """Exercise the deterministic mock over every labeled sample row.

    Raises:
        AssertionError: If the mock response shape is incomplete, non-
            deterministic, or missing one response per submitted image.
    """
    client = MockModelClient()
    required_claim_keys = {
        COL_USER_ID,
        COL_IMAGE_PATHS,
        COL_USER_CLAIM,
        COL_CLAIM_OBJECT,
        COL_EVIDENCE_STANDARD_MET,
        COL_EVIDENCE_STANDARD_MET_REASON,
        COL_RISK_FLAGS,
        COL_ISSUE_TYPE,
        COL_OBJECT_PART,
        COL_CLAIM_STATUS,
        COL_CLAIM_STATUS_JUSTIFICATION,
        COL_SUPPORTING_IMAGE_IDS,
        COL_VALID_IMAGE,
        COL_SEVERITY,
        MODEL_CLAIM_KEY_UNCERTAINTY,
        MODEL_CLAIM_KEY_EVIDENCE_NEEDED,
    }
    required_image_keys = {
        MODEL_IMAGE_KEY_IMAGE_ID,
        MODEL_IMAGE_KEY_VALID_IMAGE,
        MODEL_IMAGE_KEY_SUPPORTS_CLAIM,
        MODEL_IMAGE_KEY_EVIDENCE_STANDARD_MET,
        MODEL_IMAGE_KEY_ISSUE_TYPE,
        MODEL_IMAGE_KEY_OBJECT_PART,
        MODEL_IMAGE_KEY_SEVERITY,
        MODEL_IMAGE_KEY_RISK_FLAGS,
        MODEL_IMAGE_KEY_CONFIDENCE,
        MODEL_IMAGE_KEY_REASON,
    }

    for row in load_sample_claims(SAMPLE_CSV):
        images = resolve_image_paths(row[COL_IMAGE_PATHS])
        context = _sample_context(row)
        first_result = client.predict(context, images)
        second_result = client.predict(context, images)

        assert first_result == second_result
        assert set(first_result) == {
            MODEL_RESPONSE_KEY_PER_IMAGE,
            MODEL_RESPONSE_KEY_CLAIM_LEVEL,
        }
        assert len(first_result[MODEL_RESPONSE_KEY_PER_IMAGE]) == len(images)
        assert set(first_result[MODEL_RESPONSE_KEY_CLAIM_LEVEL]) == required_claim_keys
        for image_response in first_result[MODEL_RESPONSE_KEY_PER_IMAGE]:
            assert set(image_response) == required_image_keys


if __name__ == "__main__":
    run_smoke_test()
