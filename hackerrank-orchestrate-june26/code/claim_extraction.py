"""
claim_extraction.py - Deterministic text-claim extraction.

WHAT:  This module converts a user claim transcript into a structured
       extracted-claim dictionary containing claimed issue type, object part,
       severity hint, uncertainty, and evidence needs.
WHY:   Claim extraction is kept separate so raw user text and hedging signals
       can guide both the mock model and the real VLM prompt consistently.
STEPS: Implements STEPS.md Phase 3 item 1.
IN:    user_claim text and the provided claim_object value.
OUT:   A stable extracted-claim structure.
"""

from typing import Dict, Iterable, Tuple

from constants import (
    CLAIM_CONVERSATION_TURN_SEPARATOR,
    CLAIM_CUSTOMER_SPEAKER_PREFIX,
    CLAIM_EVIDENCE_NEEDED_BY_OBJECT,
    CLAIM_EVIDENCE_NEEDED_GENERIC,
    CLAIM_EVIDENCE_NEEDED_TEMPLATE,
    CLAIM_EVIDENCE_NEEDED_UNKNOWN_TEMPLATE,
    CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
    CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART,
    CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED,
    CLAIM_EXTRACTION_KEY_SEVERITY_HINT,
    CLAIM_EXTRACTION_KEY_UNCERTAINTY,
    CLAIM_ISSUE_KEYWORDS,
    CLAIM_OBJECT_PART_KEYWORDS_BY_OBJECT,
    CLAIM_SEVERITY_HIGH_KEYWORDS,
    CLAIM_SEVERITY_LOW_KEYWORDS,
    CLAIM_SEVERITY_MEDIUM_KEYWORDS,
    CLAIM_TEXT_NORMALIZED_SEPARATOR,
    CLAIM_UNCERTAINTY_HIGH,
    CLAIM_UNCERTAINTY_HIGH_KEYWORDS,
    CLAIM_UNCERTAINTY_LOW,
    CLAIM_UNCERTAINTY_MEDIUM,
    CLAIM_UNCERTAINTY_MEDIUM_KEYWORDS,
    COL_CLAIM_OBJECT,
    COL_USER_CLAIM,
    ISSUE_TYPE_UNKNOWN,
    OBJECT_PART_UNKNOWN,
    SAMPLE_CSV,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_UNKNOWN,
)
from io_loaders import load_sample_claims


ExtractedClaim = Dict[str, str]
KeywordMapping = Iterable[Tuple[str, Tuple[str, ...]]]


def _normalize_text(text: str) -> str:
    """Normalize claim text for deterministic substring matching.

    Args:
        text: Raw user claim transcript.

    Returns:
        Lowercase text with line breaks collapsed to spaces.
    """
    return CLAIM_TEXT_NORMALIZED_SEPARATOR.join(text.lower().split())


def _claim_speaker_text(user_claim: str) -> str:
    """Prefer customer turns so support questions do not become claimed facts.

    Args:
        user_claim: Raw claim conversation transcript.

    Returns:
        Customer utterances joined together, or the full transcript if no
        customer-prefixed turn exists.
    """
    customer_turns = []
    for raw_turn in user_claim.split(CLAIM_CONVERSATION_TURN_SEPARATOR):
        normalized_turn = raw_turn.strip()
        if normalized_turn.lower().startswith(CLAIM_CUSTOMER_SPEAKER_PREFIX):
            customer_turns.append(
                normalized_turn[len(CLAIM_CUSTOMER_SPEAKER_PREFIX) :].strip()
            )
    if customer_turns:
        return CLAIM_TEXT_NORMALIZED_SEPARATOR.join(customer_turns)
    return user_claim


def _contains_any(normalized_text: str, keywords: Iterable[str]) -> bool:
    """Check whether any configured keyword is present.

    Args:
        normalized_text: Lowercase normalized claim text.
        keywords: Keyword strings from constants.py.

    Returns:
        True when at least one keyword appears as a substring.
    """
    return any(keyword in normalized_text for keyword in keywords)


def _first_match(normalized_text: str, mappings: KeywordMapping, default_value: str) -> str:
    """Return the first mapped value whose keyword appears in the claim text.

    Args:
        normalized_text: Lowercase normalized claim text.
        mappings: Ordered value-to-keywords mappings.
        default_value: Value returned when no keyword matches.

    Returns:
        The first matching mapped value, preserving constants.py priority order.
    """
    for value, keywords in mappings:
        if _contains_any(normalized_text, keywords):
            return value
    return default_value


def _detect_uncertainty(normalized_text: str) -> str:
    """Capture hedged wording as a deterministic signal for later reasoning.

    Args:
        normalized_text: Lowercase normalized claim text.

    Returns:
        low, medium, or high uncertainty.
    """
    if _contains_any(normalized_text, CLAIM_UNCERTAINTY_HIGH_KEYWORDS):
        return CLAIM_UNCERTAINTY_HIGH
    if _contains_any(normalized_text, CLAIM_UNCERTAINTY_MEDIUM_KEYWORDS):
        return CLAIM_UNCERTAINTY_MEDIUM
    return CLAIM_UNCERTAINTY_LOW


def _extract_issue_type(normalized_text: str) -> str:
    """Extract a coarse claimed issue type for the mock-first pipeline.

    Args:
        normalized_text: Lowercase normalized claim text.

    Returns:
        An allowed issue_type value or unknown.
    """
    return _first_match(normalized_text, CLAIM_ISSUE_KEYWORDS, ISSUE_TYPE_UNKNOWN)


def _extract_object_part(normalized_text: str, claim_object: str) -> str:
    """Extract the object-specific claimed part when a configured keyword matches.

    Args:
        normalized_text: Lowercase normalized claim text.
        claim_object: Provided object type for object-specific part vocabulary.

    Returns:
        An allowed object_part for that object, or unknown.
    """
    mappings = CLAIM_OBJECT_PART_KEYWORDS_BY_OBJECT.get(claim_object)
    if mappings is None:
        return OBJECT_PART_UNKNOWN
    return _first_match(normalized_text, mappings, OBJECT_PART_UNKNOWN)


def _severity_hint(normalized_text: str) -> str:
    """Infer a conservative severity hint from user wording only.

    Args:
        normalized_text: Lowercase normalized claim text.

    Returns:
        low, medium, high, or unknown severity hint.
    """
    if _contains_any(normalized_text, CLAIM_SEVERITY_HIGH_KEYWORDS):
        return SEVERITY_HIGH
    if _contains_any(normalized_text, CLAIM_SEVERITY_LOW_KEYWORDS):
        return SEVERITY_LOW
    if _contains_any(normalized_text, CLAIM_SEVERITY_MEDIUM_KEYWORDS):
        return SEVERITY_MEDIUM
    return SEVERITY_UNKNOWN


def _evidence_needed(claim_object: str, issue_type: str, object_part: str) -> str:
    """Build a deterministic evidence-needed phrase for prompt context.

    Args:
        claim_object: Provided object type.
        issue_type: Extracted claimed issue type.
        object_part: Extracted claimed object part.

    Returns:
        A short evidence guidance string.
    """
    base = CLAIM_EVIDENCE_NEEDED_BY_OBJECT.get(
        claim_object,
        CLAIM_EVIDENCE_NEEDED_GENERIC,
    )
    if issue_type == ISSUE_TYPE_UNKNOWN or object_part == OBJECT_PART_UNKNOWN:
        return CLAIM_EVIDENCE_NEEDED_UNKNOWN_TEMPLATE.format(base=base)
    return CLAIM_EVIDENCE_NEEDED_TEMPLATE.format(
        base=base,
        object_part=object_part,
        issue_type=issue_type,
    )


def extract_claim(user_claim: str, claim_object: str) -> ExtractedClaim:
    """Extract a stable, keyword-based claim structure from user text.

    Args:
        user_claim: Raw claim conversation transcript.
        claim_object: Provided object type from the row.

    Returns:
        A dictionary containing claimed_issue_type, claimed_object_part,
        severity_hint, uncertainty, and evidence_needed.
    """
    normalized_text = _normalize_text(_claim_speaker_text(user_claim))
    issue_type = _extract_issue_type(normalized_text)
    object_part = _extract_object_part(normalized_text, claim_object)
    return {
        CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE: issue_type,
        CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART: object_part,
        CLAIM_EXTRACTION_KEY_SEVERITY_HINT: _severity_hint(normalized_text),
        CLAIM_EXTRACTION_KEY_UNCERTAINTY: _detect_uncertainty(normalized_text),
        CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED: _evidence_needed(
            claim_object,
            issue_type,
            object_part,
        ),
    }


def run_smoke_test() -> None:
    """Exercise claim extraction across all labeled sample rows.

    Raises:
        AssertionError: If extraction is unstable or missing required fields.
    """
    required_keys = {
        CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
        CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART,
        CLAIM_EXTRACTION_KEY_SEVERITY_HINT,
        CLAIM_EXTRACTION_KEY_UNCERTAINTY,
        CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED,
    }
    for row in load_sample_claims(SAMPLE_CSV):
        first_result = extract_claim(row[COL_USER_CLAIM], row[COL_CLAIM_OBJECT])
        second_result = extract_claim(row[COL_USER_CLAIM], row[COL_CLAIM_OBJECT])
        assert first_result == second_result
        assert set(first_result) == required_keys
        assert first_result[CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED]


if __name__ == "__main__":
    run_smoke_test()
