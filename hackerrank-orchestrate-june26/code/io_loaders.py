"""
io_loaders.py - Deterministic CSV and image-path loading helpers.

WHAT:  This module reads the claim, sample, history, and evidence CSV files;
       preserves input row order; indexes supporting context; and resolves
       image paths relative to the dataset directory.
WHY:   Keeping IO separate from model and validation logic makes the pipeline
       reproducible and lets later phases verify dataset contracts before any
       reasoning runs.
STEPS: Implements STEPS.md Phase 1 items 1-2.
IN:    CSV files under dataset/ and semicolon-separated image path fields.
OUT:   In-memory row dictionaries, indexed supporting data, and resolved image
       identifiers/paths.
"""

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from constants import (
    CLAIM_OBJECT_ALL,
    CLAIMS_CSV,
    COL_APPLIES_TO,
    COL_CLAIM_OBJECT,
    COL_IMAGE_PATHS,
    COL_MINIMUM_IMAGE_EVIDENCE,
    COL_USER_ID,
    DATASET_DIR,
    EVIDENCE_COLUMNS,
    EVIDENCE_CSV,
    EVIDENCE_REQUIREMENT_TEXT_SEPARATOR,
    EXPECTED_EVIDENCE_REQUIREMENTS_ROW_COUNT,
    EXPECTED_HISTORY_ROW_COUNT,
    EXPECTED_SAMPLE_CLAIMS_ROW_COUNT,
    EXPECTED_TEST_CLAIMS_ROW_COUNT,
    HISTORY_COLUMNS,
    HISTORY_CSV,
    IMAGE_PATH_SEPARATOR,
    INPUT_COLUMNS,
    OUTPUT_COLUMNS,
    SAMPLE_CSV,
)


Row = Dict[str, str]
ResolvedImage = Tuple[str, Path]
EvidenceRequirementIndex = Dict[Tuple[str, str], Row]

_EVIDENCE_REQUIREMENT_INDEX: EvidenceRequirementIndex | None = None


def _read_csv_rows(path: Path, expected_columns: Sequence[str]) -> List[Row]:
    """Read a CSV file with exact headers so downstream phases never guess schema.

    Args:
        path: CSV path to read.
        expected_columns: The exact field order required for this file.

    Returns:
        A list of row dictionaries in input order.

    Raises:
        ValueError: If the header does not match the expected contract.
    """
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if tuple(reader.fieldnames or ()) != tuple(expected_columns):
            raise ValueError(
                f"{path} columns {reader.fieldnames} do not match {tuple(expected_columns)}"
            )
        return [dict(row) for row in reader]


def _normalize_lookup_value(value: str) -> str:
    """Normalize CSV lookup keys because matching is contract-based, not case-sensitive.

    Args:
        value: Raw CSV or caller-provided lookup text.

    Returns:
        A stripped, lowercase key for deterministic dictionary lookups.
    """
    return value.strip().lower()


def _rows_by_user_id(rows: Iterable[Row]) -> Dict[str, Row]:
    """Index rows by user_id while rejecting duplicates that would make joins ambiguous.

    Args:
        rows: History rows from user_history.csv.

    Returns:
        A dictionary keyed by user_id.

    Raises:
        ValueError: If the same user_id appears more than once.
    """
    indexed: Dict[str, Row] = {}
    for row in rows:
        user_id = row[COL_USER_ID]
        if user_id in indexed:
            raise ValueError(f"duplicate user_id in history: {user_id}")
        indexed[user_id] = row
    return indexed


def load_claims(path: Path = CLAIMS_CSV) -> List[Row]:
    """Load input-only claim rows in file order for one-output-row-per-input behavior.

    Args:
        path: Path to the input claims CSV.

    Returns:
        Claim row dictionaries preserving CSV order.
    """
    return _read_csv_rows(Path(path), INPUT_COLUMNS)


def load_sample_claims(path: Path = SAMPLE_CSV) -> List[Row]:
    """Load labeled sample rows with the full output schema for evaluation.

    Args:
        path: Path to the labeled sample CSV.

    Returns:
        Sample row dictionaries preserving CSV order.
    """
    return _read_csv_rows(Path(path), OUTPUT_COLUMNS)


def load_history(path: Path = HISTORY_CSV) -> Dict[str, Row]:
    """Load user history keyed by user_id so later joins are deterministic.

    Args:
        path: Path to user_history.csv.

    Returns:
        A dictionary from user_id to the corresponding history row.
    """
    return _rows_by_user_id(_read_csv_rows(Path(path), HISTORY_COLUMNS))


def load_evidence_requirements(path: Path = EVIDENCE_CSV) -> EvidenceRequirementIndex:
    """Load evidence requirements indexed by object and issue family.

    Args:
        path: Path to evidence_requirements.csv.

    Returns:
        A dictionary keyed by normalized (claim_object, applies_to).
    """
    global _EVIDENCE_REQUIREMENT_INDEX

    rows = _read_csv_rows(Path(path), EVIDENCE_COLUMNS)
    index: EvidenceRequirementIndex = {}
    for row in rows:
        key = (
            _normalize_lookup_value(row[COL_CLAIM_OBJECT]),
            _normalize_lookup_value(row[COL_APPLIES_TO]),
        )
        if key in index:
            raise ValueError(f"duplicate evidence requirement key: {key}")
        index[key] = row
    _EVIDENCE_REQUIREMENT_INDEX = index
    return index


def resolve_image_paths(image_paths_field: str) -> List[ResolvedImage]:
    """Resolve semicolon-separated dataset-relative image paths to image IDs and paths.

    Args:
        image_paths_field: Raw image_paths CSV field, separated by IMAGE_PATH_SEPARATOR.

    Returns:
        A list of (image_id, absolute_path) tuples in input order.
    """
    resolved: List[ResolvedImage] = []
    for raw_image_path in image_paths_field.split(IMAGE_PATH_SEPARATOR):
        relative_path = Path(raw_image_path.strip())
        absolute_path = (DATASET_DIR / relative_path).resolve()
        resolved.append((absolute_path.stem, absolute_path))
    return resolved


def match_evidence_requirement(claim_object: str, issue_family: str) -> str:
    """Return the matched requirement text, falling back to general rules.

    Args:
        claim_object: Provided object type for the claim.
        issue_family: Extracted issue family used to select a requirement.

    Returns:
        The specific minimum evidence text, or joined general `all` requirement
        text when no exact object/family match exists.

    Raises:
        ValueError: If evidence_requirements.csv has no general fallback rows.
    """
    index = _EVIDENCE_REQUIREMENT_INDEX or load_evidence_requirements(EVIDENCE_CSV)
    exact_key = (
        _normalize_lookup_value(claim_object),
        _normalize_lookup_value(issue_family),
    )
    exact_row = index.get(exact_key)
    if exact_row is not None:
        return exact_row[COL_MINIMUM_IMAGE_EVIDENCE]

    fallback_texts = [
        row[COL_MINIMUM_IMAGE_EVIDENCE]
        for (indexed_object, _), row in sorted(index.items())
        if indexed_object == CLAIM_OBJECT_ALL
    ]
    if not fallback_texts:
        raise ValueError("evidence requirements have no all-object fallback rows")
    return EVIDENCE_REQUIREMENT_TEXT_SEPARATOR.join(fallback_texts)


def run_smoke_test() -> None:
    """Exercise Phase 1 loaders against real data without invoking any model.

    Raises:
        AssertionError: If row counts, evidence indexing, or image resolution
            violate the dataset facts locked in STEPS.md Phase 1.
    """
    sample_rows = load_sample_claims(SAMPLE_CSV)
    test_rows = load_claims(CLAIMS_CSV)
    history_by_user = load_history(HISTORY_CSV)
    evidence_index = load_evidence_requirements(EVIDENCE_CSV)

    assert len(sample_rows) == EXPECTED_SAMPLE_CLAIMS_ROW_COUNT
    assert len(test_rows) == EXPECTED_TEST_CLAIMS_ROW_COUNT
    assert len(history_by_user) == EXPECTED_HISTORY_ROW_COUNT
    assert len(evidence_index) == EXPECTED_EVIDENCE_REQUIREMENTS_ROW_COUNT

    first_sample_images = resolve_image_paths(sample_rows[0][COL_IMAGE_PATHS])
    assert first_sample_images
    assert first_sample_images[0][1].exists()

    specific_requirement = next(
        row
        for (indexed_object, _), row in sorted(evidence_index.items())
        if indexed_object != CLAIM_OBJECT_ALL
    )
    requirement_text = match_evidence_requirement(
        specific_requirement[COL_CLAIM_OBJECT],
        specific_requirement[COL_APPLIES_TO],
    )
    assert requirement_text

    fallback_text = match_evidence_requirement(
        specific_requirement[COL_CLAIM_OBJECT],
        COL_MINIMUM_IMAGE_EVIDENCE,
    )
    assert fallback_text
    assert fallback_text != requirement_text


if __name__ == "__main__":
    run_smoke_test()
