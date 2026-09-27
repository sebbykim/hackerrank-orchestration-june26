"""
validate.py - Output clamping and consistency invariants.

WHAT:  This module clamps output fields to allowed values and enforces row
       consistency invariants before CSV writing or metric comparison.
WHY:   Deterministic validation is the hard guard against model drift,
       out-of-vocabulary labels, unsupported image IDs, and schema mismatch.
STEPS: Implements STEPS.md Phase 6 item 2.
IN:    Raw output dictionaries and the set of image IDs present in the claim.
OUT:   Schema-valid rows in the exact output column order.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List

from constants import (
    ALLOWED_CLAIM_STATUS,
    ALLOWED_ISSUE_TYPES,
    ALLOWED_OBJECT_PARTS_BY_OBJECT,
    ALLOWED_RISK_FLAGS,
    ALLOWED_SEVERITY,
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
    IMAGE_PATH_SEPARATOR,
    ISSUE_TYPE_UNKNOWN,
    OBJECT_PART_UNKNOWN,
    OUTPUT_BOOLEAN_FALSE,
    OUTPUT_BOOLEAN_TRUE,
    OUTPUT_COLUMNS,
    OUTPUT_EMPTY_VALUE,
    RISK_FLAG_NONE,
    SEVERITY_UNKNOWN,
    VALIDATE_SUPPORTING_IMAGE_IDS_NONE,
)


OutputRow = Dict[str, str]


def _as_text(value: Any) -> str:
    """Convert scalar output values to stable CSV text.

    Validation owns final serialization, so callers can pass booleans, lists, or
    model strings without leaking Python-specific forms into `output.csv`.
    """
    if value is None:
        return OUTPUT_EMPTY_VALUE
    return str(value)


def _as_bool_text(value: Any) -> str:
    """Clamp boolean-like values to the required true/false CSV strings.

    Model JSON uses booleans while sample labels use lowercase strings, so this
    helper bridges both representations deterministically.
    """
    if isinstance(value, bool):
        return OUTPUT_BOOLEAN_TRUE if value else OUTPUT_BOOLEAN_FALSE
    normalized = _as_text(value).strip().lower()
    if normalized == OUTPUT_BOOLEAN_TRUE:
        return OUTPUT_BOOLEAN_TRUE
    return OUTPUT_BOOLEAN_FALSE


def _split_values(value: Any) -> List[str]:
    """Normalize semicolon strings or JSON arrays into a flat string list.

    Risk flags and supporting image IDs can arrive from the model as arrays, but
    the final CSV representation uses the existing semicolon separator.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_as_text(item).strip() for item in value if _as_text(item).strip()]
    return [
        item.strip()
        for item in _as_text(value).split(IMAGE_PATH_SEPARATOR)
        if item.strip()
    ]


def _claim_image_ids(image_paths: str) -> List[str]:
    """Extract allowed supporting IDs from the row's image_paths field.

    The validator uses filename stems, matching the project definition of image
    IDs, so model outputs cannot cite images absent from the current row.
    """
    return [
        Path(raw_path.strip()).stem
        for raw_path in image_paths.split(IMAGE_PATH_SEPARATOR)
        if raw_path.strip()
    ]


def _clamp_enum(value: Any, allowed_values: Iterable[str], fallback: str) -> str:
    """Clamp one categorical field to an allowed set.

    This is the code-level enforcement of the problem statement's "closest
    allowed value" rule when a model emits an invalid or missing value.
    """
    normalized = _as_text(value).strip()
    if normalized in allowed_values:
        return normalized
    return fallback


def _clamp_object_part(raw_row: Dict[str, Any]) -> str:
    """Clamp object_part using the row's object-specific enum list.

    Object parts are only valid in the context of car/laptop/package, so this
    check is stricter than a global union of part names.
    """
    claim_object = _as_text(raw_row.get(COL_CLAIM_OBJECT)).strip()
    allowed_parts = ALLOWED_OBJECT_PARTS_BY_OBJECT.get(claim_object, frozenset())
    return _clamp_enum(
        raw_row.get(COL_OBJECT_PART),
        allowed_parts,
        OBJECT_PART_UNKNOWN,
    )


def _clamp_risk_flags(value: Any) -> str:
    """Clamp, de-duplicate, and serialize risk flags.

    `none` is only retained when no concrete risk flag survives, which prevents
    contradictory outputs such as `none;blurry_image`.
    """
    seen = set()
    clamped = []
    for flag in _split_values(value):
        if flag == RISK_FLAG_NONE:
            continue
        if flag in ALLOWED_RISK_FLAGS and flag not in seen:
            seen.add(flag)
            clamped.append(flag)
    if not clamped:
        return RISK_FLAG_NONE
    return IMAGE_PATH_SEPARATOR.join(clamped)


def _clamp_supporting_image_ids(raw_row: Dict[str, Any]) -> str:
    """Keep only supporting image IDs present in this row.

    This prevents a model from citing stale or hallucinated image IDs and keeps
    `supporting_image_ids` selective by construction.
    """
    allowed_ids = _claim_image_ids(_as_text(raw_row.get(COL_IMAGE_PATHS)))
    allowed_set = set(allowed_ids)
    seen = set()
    kept = []
    for image_id in _split_values(raw_row.get(COL_SUPPORTING_IMAGE_IDS)):
        if image_id in allowed_set and image_id not in seen:
            seen.add(image_id)
            kept.append(image_id)
    if not kept:
        return VALIDATE_SUPPORTING_IMAGE_IDS_NONE
    return IMAGE_PATH_SEPARATOR.join(kept)


def clamp_and_validate(raw_output_dict: Dict[str, Any]) -> OutputRow:
    """Clamp one raw aggregate output into the exact output schema.

    Args:
        raw_output_dict: Claim output fields from aggregation, potentially still
            containing model-native booleans, arrays, or invalid categorical
            values.

    Returns:
        A string-only row dictionary ordered like OUTPUT_COLUMNS and consistent
        with Phase 6 invariants.
    """
    output_row: OutputRow = {
        column: _as_text(raw_output_dict.get(column, OUTPUT_EMPTY_VALUE))
        for column in OUTPUT_COLUMNS
    }
    output_row[COL_EVIDENCE_STANDARD_MET] = _as_bool_text(
        raw_output_dict.get(COL_EVIDENCE_STANDARD_MET)
    )
    output_row[COL_VALID_IMAGE] = _as_bool_text(raw_output_dict.get(COL_VALID_IMAGE))
    output_row[COL_RISK_FLAGS] = _clamp_risk_flags(raw_output_dict.get(COL_RISK_FLAGS))
    output_row[COL_ISSUE_TYPE] = _clamp_enum(
        raw_output_dict.get(COL_ISSUE_TYPE),
        ALLOWED_ISSUE_TYPES,
        ISSUE_TYPE_UNKNOWN,
    )
    output_row[COL_OBJECT_PART] = _clamp_object_part(raw_output_dict)
    output_row[COL_CLAIM_STATUS] = _clamp_enum(
        raw_output_dict.get(COL_CLAIM_STATUS),
        ALLOWED_CLAIM_STATUS,
        CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
    )
    output_row[COL_SEVERITY] = _clamp_enum(
        raw_output_dict.get(COL_SEVERITY),
        ALLOWED_SEVERITY,
        SEVERITY_UNKNOWN,
    )
    output_row[COL_SUPPORTING_IMAGE_IDS] = _clamp_supporting_image_ids(raw_output_dict)

    if output_row[COL_VALID_IMAGE] == OUTPUT_BOOLEAN_FALSE:
        output_row[COL_EVIDENCE_STANDARD_MET] = OUTPUT_BOOLEAN_FALSE
        output_row[COL_SUPPORTING_IMAGE_IDS] = VALIDATE_SUPPORTING_IMAGE_IDS_NONE
        output_row[COL_CLAIM_STATUS] = CLAIM_STATUS_NOT_ENOUGH_INFORMATION
        output_row[COL_SEVERITY] = SEVERITY_UNKNOWN

    return {column: output_row[column] for column in OUTPUT_COLUMNS}


def run_smoke_test() -> None:
    """Exercise validation clamping and invariants without invoking a model.

    Raises:
        AssertionError: If output order, allowed-value clamping, risk flag
            de-duplication, or invalid-image invariants fail.
    """
    raw_row = {
        COL_USER_ID: "user",
        COL_IMAGE_PATHS: "images/test/case/img_1.jpg;images/test/case/img_2.jpg",
        COL_USER_CLAIM: "claim",
        COL_CLAIM_OBJECT: "car",
        COL_EVIDENCE_STANDARD_MET: True,
        COL_EVIDENCE_STANDARD_MET_REASON: "reason",
        COL_RISK_FLAGS: ["none", "blurry_image", "blurry_image", "bad_flag"],
        COL_ISSUE_TYPE: "invalid",
        COL_OBJECT_PART: "screen",
        COL_CLAIM_STATUS: "invalid",
        COL_CLAIM_STATUS_JUSTIFICATION: "justification",
        COL_SUPPORTING_IMAGE_IDS: ["img_2", "other", "img_2"],
        COL_VALID_IMAGE: False,
        COL_SEVERITY: "high",
    }
    output_row = clamp_and_validate(raw_row)
    assert tuple(output_row) == OUTPUT_COLUMNS
    assert output_row[COL_EVIDENCE_STANDARD_MET] == OUTPUT_BOOLEAN_FALSE
    assert output_row[COL_VALID_IMAGE] == OUTPUT_BOOLEAN_FALSE
    assert output_row[COL_RISK_FLAGS] == "blurry_image"
    assert output_row[COL_ISSUE_TYPE] == ISSUE_TYPE_UNKNOWN
    assert output_row[COL_OBJECT_PART] == OBJECT_PART_UNKNOWN
    assert output_row[COL_CLAIM_STATUS] == CLAIM_STATUS_NOT_ENOUGH_INFORMATION
    assert output_row[COL_SUPPORTING_IMAGE_IDS] == VALIDATE_SUPPORTING_IMAGE_IDS_NONE
    assert output_row[COL_SEVERITY] == SEVERITY_UNKNOWN


if __name__ == "__main__":
    run_smoke_test()
