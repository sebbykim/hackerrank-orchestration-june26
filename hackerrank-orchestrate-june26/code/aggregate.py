"""
aggregate.py - Claim-level aggregation from model and pre-filter outputs.

WHAT:  This module turns per-image model judgments plus deterministic
       pre-filter signals into a raw claim-level output row.
WHY:   Aggregation is separated from validation so business decisions such as
       selective supporting image IDs and history-as-risk remain reviewable.
STEPS: Implements STEPS.md Phase 6 item 1.
IN:    Model responses, pre-filter results, extracted claim data, and history.
OUT:   Raw output dictionaries ready for validation.
"""

from typing import Any, Dict, Iterable, List, Mapping

from constants import (
    AGGREGATE_DEFAULT_REASON,
    AGGREGATE_INTERNAL_IMAGE_IDS,
    CLAIM_STATUS_CONTRADICTED,
    CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
    CLAIM_STATUS_SUPPORTED,
    COL_ACCEPT_CLAIM,
    COL_CLAIM_STATUS,
    COL_CLAIM_STATUS_JUSTIFICATION,
    COL_EVIDENCE_STANDARD_MET,
    COL_EVIDENCE_STANDARD_MET_REASON,
    COL_HISTORY_FLAGS,
    COL_IMAGE_PATHS,
    COL_LAST_90_DAYS_CLAIM_COUNT,
    COL_MANUAL_REVIEW_CLAIM,
    COL_PAST_CLAIM_COUNT,
    COL_REJECTED_CLAIM,
    COL_RISK_FLAGS,
    COL_SUPPORTING_IMAGE_IDS,
    COL_VALID_IMAGE,
    HISTORY_NO_FLAGS,
    HISTORY_RISK_ZERO_COUNT,
    IMAGE_PATH_SEPARATOR,
    MODEL_AUTHENTICITY_KEY_NON_ORIGINAL_IMAGE,
    MODEL_AUTHENTICITY_KEY_POSSIBLE_MANIPULATION,
    MODEL_AUTHENTICITY_KEY_TEXT_INSTRUCTION_PRESENT,
    MODEL_DAMAGE_KEY_VISIBLE,
    MODEL_IMAGE_KEY_AUTHENTICITY,
    MODEL_IMAGE_KEY_DAMAGE,
    MODEL_IMAGE_KEY_EVIDENCE_STANDARD_MET,
    MODEL_IMAGE_KEY_IMAGE_ID,
    MODEL_IMAGE_KEY_OBJECT_CHECK,
    MODEL_IMAGE_KEY_PART_CHECK,
    MODEL_IMAGE_KEY_RISK_FLAGS,
    MODEL_IMAGE_KEY_SUPPORTS_CLAIM,
    MODEL_IMAGE_KEY_USEFULNESS,
    MODEL_OBJECT_CHECK_KEY_WRONG_OBJECT,
    MODEL_PART_CHECK_KEY_SHOWS_CLAIMED_PART,
    MODEL_PART_CHECK_KEY_WRONG_ANGLE,
    MODEL_RESPONSE_KEY_CLAIM_LEVEL,
    MODEL_RESPONSE_KEY_PER_IMAGE,
    MODEL_USEFULNESS_CONTRADICTS_CLAIM,
    MODEL_USEFULNESS_SUPPORTS_CLAIM,
    OUTPUT_BOOLEAN_TRUE,
    PREFILTER_KEY_DECODE_OK,
    PREFILTER_KEY_EXIF,
    PREFILTER_KEY_FLAGS,
    PREFILTER_KEY_IMAGE_ID,
    PREFILTER_KEY_NON_ORIGINAL_SIGNAL,
    PREFILTER_KEY_PER_IMAGE,
    RISK_FLAG_CLAIM_MISMATCH,
    RISK_FLAG_DAMAGE_NOT_VISIBLE,
    RISK_FLAG_MANUAL_REVIEW_REQUIRED,
    RISK_FLAG_NONE,
    RISK_FLAG_NON_ORIGINAL_IMAGE,
    RISK_FLAG_POSSIBLE_MANIPULATION,
    RISK_FLAG_TEXT_INSTRUCTION_PRESENT,
    RISK_FLAG_USER_HISTORY_RISK,
    RISK_FLAG_WRONG_ANGLE,
    RISK_FLAG_WRONG_OBJECT,
    RISK_FLAG_WRONG_OBJECT_PART,
)


RawOutput = Dict[str, Any]


def _as_list(value: Any) -> List[Any]:
    """Normalize model scalar/list fields into a list for aggregation.

    Model clients may use JSON arrays or semicolon strings; aggregation treats
    both as evidence lists and lets validation handle final serialization.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(IMAGE_PATH_SEPARATOR) if item.strip()]
    return [value]


def _as_bool(value: Any) -> bool:
    """Interpret model boolean fields from JSON or CSV-like strings.

    Aggregation receives both mock JSON booleans and possible string values, so
    a small normalizer keeps decision logic deterministic.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == OUTPUT_BOOLEAN_TRUE


def _risk_flags_from_values(values: Iterable[Any]) -> List[str]:
    """De-duplicate risk flags while discarding the placeholder `none` value.

    Concrete risks must survive aggregation even if the claim is otherwise
    supported; validation later clamps unknown flags to the allowed set.
    """
    flags: List[str] = []
    seen = set()
    for value in values:
        for flag in _as_list(value):
            flag_text = str(flag)
            if flag_text == RISK_FLAG_NONE or flag_text in seen:
                continue
            seen.add(flag_text)
            flags.append(flag_text)
    if not flags:
        return [RISK_FLAG_NONE]
    return flags


def _per_image_id(image_result: Mapping[str, Any]) -> str:
    """Return the image ID from a model or prefilter image record.

    Both Phase 4 mock and Phase 5 schema use `image_id`, matching the prefilter
    key, so this helper documents the shared assumption.
    """
    return str(
        image_result.get(MODEL_IMAGE_KEY_IMAGE_ID)
        or image_result.get(PREFILTER_KEY_IMAGE_ID)
        or ""
    )


def _per_image_supports_decision(image_result: Mapping[str, Any]) -> bool:
    """Detect whether a per-image model record supports the final decision.

    Rich prompt responses use `usefulness`; the Phase 4 mock uses
    `supports_claim`. Both paths keep supporting image IDs selective.
    """
    usefulness = image_result.get(MODEL_IMAGE_KEY_USEFULNESS)
    if usefulness in (MODEL_USEFULNESS_SUPPORTS_CLAIM, MODEL_USEFULNESS_CONTRADICTS_CLAIM):
        return True
    return _as_bool(image_result.get(MODEL_IMAGE_KEY_SUPPORTS_CLAIM))


def _image_risks(image_result: Mapping[str, Any]) -> List[str]:
    """Extract risk flags implied by a per-image model record.

    The VLM reports semantic risks in structured booleans; aggregation converts
    them into output risk flags while preserving any explicit risk list.
    """
    risks = list(_as_list(image_result.get(MODEL_IMAGE_KEY_RISK_FLAGS)))
    object_check = image_result.get(MODEL_IMAGE_KEY_OBJECT_CHECK, {})
    part_check = image_result.get(MODEL_IMAGE_KEY_PART_CHECK, {})
    damage = image_result.get(MODEL_IMAGE_KEY_DAMAGE, {})
    authenticity = image_result.get(MODEL_IMAGE_KEY_AUTHENTICITY, {})

    if isinstance(object_check, Mapping) and _as_bool(
        object_check.get(MODEL_OBJECT_CHECK_KEY_WRONG_OBJECT)
    ):
        risks.append(RISK_FLAG_WRONG_OBJECT)
    if isinstance(part_check, Mapping):
        if _as_bool(part_check.get(MODEL_PART_CHECK_KEY_WRONG_ANGLE)):
            risks.append(RISK_FLAG_WRONG_ANGLE)
        if part_check.get(MODEL_PART_CHECK_KEY_SHOWS_CLAIMED_PART) is False:
            risks.append(RISK_FLAG_WRONG_OBJECT_PART)
    if isinstance(damage, Mapping) and damage.get(MODEL_DAMAGE_KEY_VISIBLE) is False:
        risks.append(RISK_FLAG_DAMAGE_NOT_VISIBLE)
    if isinstance(authenticity, Mapping):
        if _as_bool(authenticity.get(MODEL_AUTHENTICITY_KEY_POSSIBLE_MANIPULATION)):
            risks.append(RISK_FLAG_POSSIBLE_MANIPULATION)
        if _as_bool(authenticity.get(MODEL_AUTHENTICITY_KEY_NON_ORIGINAL_IMAGE)):
            risks.append(RISK_FLAG_NON_ORIGINAL_IMAGE)
        if _as_bool(authenticity.get(MODEL_AUTHENTICITY_KEY_TEXT_INSTRUCTION_PRESENT)):
            risks.append(RISK_FLAG_TEXT_INSTRUCTION_PRESENT)
    return risks


def _prefilter_risks(prefilter_result: Mapping[str, Any]) -> List[str]:
    """Collect programmatic quality/authenticity risks from prefilter output.

    Prefilter signals are preserved regardless of whether another image supports
    the claim, matching design §13's "one bad image doesn't auto-sink" rule.
    """
    risks: List[str] = []
    for image_result in prefilter_result.get(PREFILTER_KEY_PER_IMAGE, ()):
        risks.extend(_as_list(image_result.get(PREFILTER_KEY_FLAGS)))
        exif_signal = image_result.get(PREFILTER_KEY_EXIF, {})
        if isinstance(exif_signal, Mapping) and _as_bool(
            exif_signal.get(PREFILTER_KEY_NON_ORIGINAL_SIGNAL)
        ):
            risks.append(RISK_FLAG_NON_ORIGINAL_IMAGE)
    return risks


def _prefilter_image_ids(prefilter_result: Mapping[str, Any]) -> List[str]:
    """Return image IDs available in the prefilter result.

    Aggregation carries these IDs to validation so supporting IDs can be checked
    even before Phase 7 wires a full pipeline.
    """
    return [
        _per_image_id(image_result)
        for image_result in prefilter_result.get(PREFILTER_KEY_PER_IMAGE, ())
        if _per_image_id(image_result)
    ]


def _has_valid_prefilter_image(prefilter_result: Mapping[str, Any]) -> bool:
    """Report whether any prefilter image decoded successfully.

    The model remains the semantic authority, but a fully dead image set cannot
    be considered valid automated evidence.
    """
    per_image = prefilter_result.get(PREFILTER_KEY_PER_IMAGE, ())
    if not per_image:
        return False
    return any(_as_bool(image_result.get(PREFILTER_KEY_DECODE_OK)) for image_result in per_image)


def _history_count(history: Mapping[str, Any], key: str) -> int:
    """Parse a user-history count field safely for risk-only decisions.

    History should never flip the visual claim status, but non-zero concerning
    counts are useful risk context.
    """
    try:
        return int(str(history.get(key, HISTORY_RISK_ZERO_COUNT)).strip() or HISTORY_RISK_ZERO_COUNT)
    except ValueError:
        return HISTORY_RISK_ZERO_COUNT


def _history_risks(history: Mapping[str, Any]) -> List[str]:
    """Convert user history into risk flags without changing claim status.

    Per design §14, history is context only: it can add user_history_risk and
    manual_review_required, but visual evidence remains the status driver.
    """
    risks: List[str] = []
    history_flags = str(history.get(COL_HISTORY_FLAGS, "")).strip().lower()
    if history_flags and history_flags != HISTORY_NO_FLAGS:
        risks.append(RISK_FLAG_USER_HISTORY_RISK)

    rejected_claims = _history_count(history, COL_REJECTED_CLAIM)
    manual_reviews = _history_count(history, COL_MANUAL_REVIEW_CLAIM)
    recent_claims = _history_count(history, COL_LAST_90_DAYS_CLAIM_COUNT)
    accepted_claims = _history_count(history, COL_ACCEPT_CLAIM)
    past_claims = _history_count(history, COL_PAST_CLAIM_COUNT)
    if rejected_claims or manual_reviews:
        risks.append(RISK_FLAG_USER_HISTORY_RISK)
    if rejected_claims and (manual_reviews or recent_claims or past_claims > accepted_claims):
        risks.append(RISK_FLAG_MANUAL_REVIEW_REQUIRED)
    return risks


def _supporting_image_ids(
    claim_level: Mapping[str, Any],
    per_image_results: Iterable[Mapping[str, Any]],
) -> List[str]:
    """Select image IDs that support the model's final decision.

    Explicit per-image usefulness takes precedence. If the model only provides a
    claim-level supporting list, that list is used as the fallback.
    """
    selected = [
        _per_image_id(image_result)
        for image_result in per_image_results
        if _per_image_id(image_result) and _per_image_supports_decision(image_result)
    ]
    if selected:
        return selected
    return [str(image_id) for image_id in _as_list(claim_level.get(COL_SUPPORTING_IMAGE_IDS))]


def _claim_status(claim_level: Mapping[str, Any], risks: List[str]) -> str:
    """Choose a claim status while preserving the severity-mismatch branch.

    The VLM can directly set `contradicted`; additionally, a claim_mismatch risk
    is treated as contradiction when the model otherwise says supported.
    """
    status = str(claim_level.get(COL_CLAIM_STATUS, CLAIM_STATUS_NOT_ENOUGH_INFORMATION))
    if status == CLAIM_STATUS_SUPPORTED and RISK_FLAG_CLAIM_MISMATCH in risks:
        return CLAIM_STATUS_CONTRADICTED
    return status


def aggregate(
    model_response: Mapping[str, Any],
    prefilter_result: Mapping[str, Any],
    history: Mapping[str, Any],
) -> RawOutput:
    """Aggregate model, prefilter, and history context into a raw output row.

    Args:
        model_response: Per-image plus claim-level response from ModelClient.
        prefilter_result: Deterministic Phase 2 prefilter output for the claim.
        history: User-history row joined by user_id.

    Returns:
        A raw output dictionary ready for clamp_and_validate().
    """
    claim_level = model_response.get(MODEL_RESPONSE_KEY_CLAIM_LEVEL, {})
    per_image_results = list(model_response.get(MODEL_RESPONSE_KEY_PER_IMAGE, ()))

    risks = _risk_flags_from_values(
        [
            claim_level.get(COL_RISK_FLAGS),
            *(_image_risks(image_result) for image_result in per_image_results),
            _prefilter_risks(prefilter_result),
            _history_risks(history),
        ]
    )
    status = _claim_status(claim_level, risks)
    valid_image = _as_bool(claim_level.get(COL_VALID_IMAGE)) and _has_valid_prefilter_image(
        prefilter_result
    )
    if not valid_image:
        status = CLAIM_STATUS_NOT_ENOUGH_INFORMATION

    raw_output: RawOutput = dict(claim_level)
    raw_output.update(
        {
            COL_EVIDENCE_STANDARD_MET: claim_level.get(
                COL_EVIDENCE_STANDARD_MET,
                any(
                    _as_bool(image_result.get(MODEL_IMAGE_KEY_EVIDENCE_STANDARD_MET))
                    for image_result in per_image_results
                ),
            ),
            COL_EVIDENCE_STANDARD_MET_REASON: claim_level.get(
                COL_EVIDENCE_STANDARD_MET_REASON,
                AGGREGATE_DEFAULT_REASON,
            ),
            COL_RISK_FLAGS: risks,
            COL_CLAIM_STATUS: status,
            COL_CLAIM_STATUS_JUSTIFICATION: claim_level.get(
                COL_CLAIM_STATUS_JUSTIFICATION,
                AGGREGATE_DEFAULT_REASON,
            ),
            COL_SUPPORTING_IMAGE_IDS: _supporting_image_ids(
                claim_level,
                per_image_results,
            ),
            COL_VALID_IMAGE: valid_image,
            AGGREGATE_INTERNAL_IMAGE_IDS: _prefilter_image_ids(prefilter_result),
        }
    )
    return raw_output


def run_smoke_test() -> None:
    """Exercise aggregation with mock-shaped inputs.

    Raises:
        AssertionError: If risk preservation, selective supporting IDs, history
            context, or valid-image handling regresses.
    """
    model_response = {
        MODEL_RESPONSE_KEY_CLAIM_LEVEL: {
            COL_IMAGE_PATHS: "images/test/case/img_1.jpg;images/test/case/img_2.jpg",
            COL_EVIDENCE_STANDARD_MET: True,
            COL_EVIDENCE_STANDARD_MET_REASON: "reason",
            COL_RISK_FLAGS: [RISK_FLAG_NONE],
            COL_CLAIM_STATUS: CLAIM_STATUS_SUPPORTED,
            COL_CLAIM_STATUS_JUSTIFICATION: "justification",
            COL_SUPPORTING_IMAGE_IDS: ["img_1", "img_2"],
            COL_VALID_IMAGE: True,
        },
        MODEL_RESPONSE_KEY_PER_IMAGE: [
            {
                MODEL_IMAGE_KEY_IMAGE_ID: "img_1",
                MODEL_IMAGE_KEY_SUPPORTS_CLAIM: True,
                MODEL_IMAGE_KEY_RISK_FLAGS: [RISK_FLAG_NONE],
            },
            {
                MODEL_IMAGE_KEY_IMAGE_ID: "img_2",
                MODEL_IMAGE_KEY_SUPPORTS_CLAIM: False,
                MODEL_IMAGE_KEY_RISK_FLAGS: [RISK_FLAG_WRONG_OBJECT],
            },
        ],
    }
    prefilter_result = {
        PREFILTER_KEY_PER_IMAGE: (
            {
                PREFILTER_KEY_IMAGE_ID: "img_1",
                PREFILTER_KEY_DECODE_OK: True,
                PREFILTER_KEY_FLAGS: (),
            },
            {
                PREFILTER_KEY_IMAGE_ID: "img_2",
                PREFILTER_KEY_DECODE_OK: True,
                PREFILTER_KEY_FLAGS: (RISK_FLAG_WRONG_ANGLE,),
            },
        )
    }
    history = {
        COL_HISTORY_FLAGS: "high_frequency",
        COL_REJECTED_CLAIM: "1",
        COL_MANUAL_REVIEW_CLAIM: "1",
    }
    raw_output = aggregate(model_response, prefilter_result, history)
    assert raw_output[COL_CLAIM_STATUS] == CLAIM_STATUS_SUPPORTED
    assert raw_output[COL_SUPPORTING_IMAGE_IDS] == ["img_1"]
    assert RISK_FLAG_WRONG_OBJECT in raw_output[COL_RISK_FLAGS]
    assert RISK_FLAG_WRONG_ANGLE in raw_output[COL_RISK_FLAGS]
    assert RISK_FLAG_USER_HISTORY_RISK in raw_output[COL_RISK_FLAGS]
    assert RISK_FLAG_MANUAL_REVIEW_REQUIRED in raw_output[COL_RISK_FLAGS]


if __name__ == "__main__":
    run_smoke_test()
