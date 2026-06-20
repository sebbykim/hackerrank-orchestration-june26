"""
metrics.py - Evaluation metrics for labeled sample claims.

WHAT:  This module computes per-field exact accuracy, claim_status macro-F1,
       confusion matrices, and set-overlap metrics for multi-value fields.
       It is pure Python and has no model, filesystem, or network dependency.
WHY:   Evaluation is required as a deliverable, and keeping metrics isolated
       makes model-configuration comparisons reproducible and inspectable.
STEPS: Implements STEPS.md Phase 9 item 1.
IN:    Predicted output rows and labeled sample_claims.csv rows.
OUT:   Metric summaries used by the evaluation report.
"""

import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from constants import (
    COL_CLAIM_STATUS,
    COL_RISK_FLAGS,
    COL_SUPPORTING_IMAGE_IDS,
    EVALUATION_CLAIM_STATUS_LABELS,
    EVALUATION_ERROR_ROW_COUNT_MISMATCH,
    EVALUATION_EXACT_ACCURACY_FIELDS,
    EVALUATION_METRIC_CLAIM_STATUS_CONFUSION_MATRIX,
    EVALUATION_METRIC_CLAIM_STATUS_MACRO_F1,
    EVALUATION_METRIC_FIELD_ACCURACY,
    EVALUATION_METRIC_RISK_FLAGS_JACCARD,
    EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD,
    EVALUATION_NONE_VALUE,
    IMAGE_PATH_SEPARATOR,
    MODEL_UNKNOWN_IMAGE_ID,
    PREFILTER_DUPLICATE_TEST_SUFFIX,
    RISK_FLAG_BLURRY_IMAGE,
    RISK_FLAG_LOW_LIGHT_OR_GLARE,
)


Row = Mapping[str, str]
MetricSummary = Dict[str, object]


def _validate_row_counts(predicted_rows: Sequence[Row], expected_rows: Sequence[Row]) -> None:
    """Reject mismatched row counts before computing positional metrics.

    The sample CSV and pipeline outputs are compared by row order, so different
    lengths would make every downstream metric ambiguous instead of merely low.
    """
    if len(predicted_rows) != len(expected_rows):
        raise ValueError(EVALUATION_ERROR_ROW_COUNT_MISMATCH)


def _normalized_value(row: Row, field: str) -> str:
    """Return a stripped string value for exact field comparison.

    Metrics should measure semantic output differences, not incidental leading
    or trailing whitespace from CSV or model output serialization.
    """
    return str(row.get(field, "")).strip()


def _split_multi_value(value: str) -> Set[str]:
    """Convert a semicolon-delimited output field into a normalized set.

    The output contract uses `none` for an empty multi-value set. Treating that
    as empty lets Jaccard score absence correctly and avoids rewarding the
    literal marker as if it were a risk flag or image ID.
    """
    normalized_value = str(value).strip()
    if not normalized_value or normalized_value == EVALUATION_NONE_VALUE:
        return set()
    return {
        part.strip()
        for part in normalized_value.split(IMAGE_PATH_SEPARATOR)
        if part.strip() and part.strip() != EVALUATION_NONE_VALUE
    }


def _jaccard(expected_values: Set[str], predicted_values: Set[str]) -> float:
    """Return set Jaccard overlap with an exact-empty match scored as perfect.

    Multi-value fields should not be penalized when both sides correctly emit
    no values; otherwise the usual intersection-over-union score applies.
    """
    if not expected_values and not predicted_values:
        return 1.0
    union = expected_values | predicted_values
    if not union:
        return 1.0
    return len(expected_values & predicted_values) / len(union)


def field_accuracy(
    predicted_rows: Sequence[Row],
    expected_rows: Sequence[Row],
    fields: Iterable[str] = EVALUATION_EXACT_ACCURACY_FIELDS,
) -> Dict[str, float]:
    """Compute exact-match accuracy for each requested output field.

    Args:
        predicted_rows: Pipeline output rows in sample order.
        expected_rows: Labeled sample rows in the same order.
        fields: Output fields scored by exact normalized string match.

    Returns:
        A dictionary mapping field name to accuracy in the inclusive range
        [0.0, 1.0].
    """
    _validate_row_counts(predicted_rows, expected_rows)
    row_count = len(expected_rows)
    if row_count == 0:
        return {field: 0.0 for field in fields}
    return {
        field: sum(
            1
            for predicted_row, expected_row in zip(predicted_rows, expected_rows)
            if _normalized_value(predicted_row, field) == _normalized_value(expected_row, field)
        )
        / row_count
        for field in fields
    }


def confusion_matrix(
    predicted_rows: Sequence[Row],
    expected_rows: Sequence[Row],
    field: str = COL_CLAIM_STATUS,
    labels: Sequence[str] = EVALUATION_CLAIM_STATUS_LABELS,
) -> Dict[str, Dict[str, int]]:
    """Compute a label-by-label confusion matrix for a categorical field.

    Args:
        predicted_rows: Pipeline output rows in sample order.
        expected_rows: Labeled sample rows in the same order.
        field: Categorical field to score.
        labels: Ordered labels to include as rows and columns.

    Returns:
        Nested dictionaries keyed first by expected label, then predicted label.
        Unknown labels are ignored so the matrix remains bound to the contract.
    """
    _validate_row_counts(predicted_rows, expected_rows)
    matrix = {
        expected_label: {predicted_label: 0 for predicted_label in labels}
        for expected_label in labels
    }
    label_set = set(labels)
    for predicted_row, expected_row in zip(predicted_rows, expected_rows):
        expected_label = _normalized_value(expected_row, field)
        predicted_label = _normalized_value(predicted_row, field)
        if expected_label in label_set and predicted_label in label_set:
            matrix[expected_label][predicted_label] += 1
    return matrix


def macro_f1(
    predicted_rows: Sequence[Row],
    expected_rows: Sequence[Row],
    field: str = COL_CLAIM_STATUS,
    labels: Sequence[str] = EVALUATION_CLAIM_STATUS_LABELS,
) -> float:
    """Compute unweighted macro-F1 for claim_status-style labels.

    Args:
        predicted_rows: Pipeline output rows in sample order.
        expected_rows: Labeled sample rows in the same order.
        field: Categorical field to score.
        labels: Ordered labels to average across.

    Returns:
        The arithmetic mean of per-label F1 scores. A label with no precision
        or recall support contributes 0.0, which keeps weak minority-class
        behavior visible in the headline score.
    """
    matrix = confusion_matrix(predicted_rows, expected_rows, field, labels)
    f1_scores: List[float] = []
    for label in labels:
        true_positive = matrix[label][label]
        false_positive = sum(
            matrix[other_label][label]
            for other_label in labels
            if other_label != label
        )
        false_negative = sum(
            matrix[label][other_label]
            for other_label in labels
            if other_label != label
        )
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = (
            true_positive / precision_denominator
            if precision_denominator
            else 0.0
        )
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        if precision + recall == 0.0:
            f1_scores.append(0.0)
        else:
            f1_scores.append(2 * precision * recall / (precision + recall))
    if not f1_scores:
        return 0.0
    return sum(f1_scores) / len(f1_scores)


def jaccard_for_field(
    predicted_rows: Sequence[Row],
    expected_rows: Sequence[Row],
    field: str,
) -> float:
    """Compute average row-level Jaccard for a multi-value output field.

    Args:
        predicted_rows: Pipeline output rows in sample order.
        expected_rows: Labeled sample rows in the same order.
        field: Semicolon-delimited output field to compare.

    Returns:
        Mean Jaccard overlap across rows, with two empty sets scored as 1.0.
    """
    _validate_row_counts(predicted_rows, expected_rows)
    if not expected_rows:
        return 0.0
    scores = [
        _jaccard(
            _split_multi_value(_normalized_value(expected_row, field)),
            _split_multi_value(_normalized_value(predicted_row, field)),
        )
        for predicted_row, expected_row in zip(predicted_rows, expected_rows)
    ]
    return sum(scores) / len(scores)


def evaluate_predictions(
    predicted_rows: Sequence[Row],
    expected_rows: Sequence[Row],
) -> MetricSummary:
    """Return the complete Phase 9 metric bundle for one config.

    Args:
        predicted_rows: Pipeline output rows in sample order.
        expected_rows: Labeled sample rows in the same order.

    Returns:
        A dictionary containing per-field accuracy, claim_status macro-F1 and
        confusion matrix, plus Jaccard scores for multi-value fields.
    """
    return {
        EVALUATION_METRIC_FIELD_ACCURACY: field_accuracy(predicted_rows, expected_rows),
        EVALUATION_METRIC_CLAIM_STATUS_MACRO_F1: macro_f1(
            predicted_rows,
            expected_rows,
        ),
        EVALUATION_METRIC_CLAIM_STATUS_CONFUSION_MATRIX: confusion_matrix(
            predicted_rows,
            expected_rows,
        ),
        EVALUATION_METRIC_RISK_FLAGS_JACCARD: jaccard_for_field(
            predicted_rows,
            expected_rows,
            COL_RISK_FLAGS,
        ),
        EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD: jaccard_for_field(
            predicted_rows,
            expected_rows,
            COL_SUPPORTING_IMAGE_IDS,
        ),
    }


def run_smoke_test() -> None:
    """Verify metric math on a tiny deterministic fixture.

    The fixture exercises one correct claim_status, one class confusion, one
    partial multi-value overlap, and one exact-empty multi-value match.
    """
    expected_rows = [
        {
            COL_CLAIM_STATUS: EVALUATION_CLAIM_STATUS_LABELS[0],
            COL_RISK_FLAGS: IMAGE_PATH_SEPARATOR.join(
                (RISK_FLAG_BLURRY_IMAGE, RISK_FLAG_LOW_LIGHT_OR_GLARE)
            ),
            COL_SUPPORTING_IMAGE_IDS: EVALUATION_NONE_VALUE,
        },
        {
            COL_CLAIM_STATUS: EVALUATION_CLAIM_STATUS_LABELS[1],
            COL_RISK_FLAGS: EVALUATION_NONE_VALUE,
            COL_SUPPORTING_IMAGE_IDS: MODEL_UNKNOWN_IMAGE_ID,
        },
    ]
    predicted_rows = [
        {
            COL_CLAIM_STATUS: EVALUATION_CLAIM_STATUS_LABELS[0],
            COL_RISK_FLAGS: RISK_FLAG_BLURRY_IMAGE,
            COL_SUPPORTING_IMAGE_IDS: EVALUATION_NONE_VALUE,
        },
        {
            COL_CLAIM_STATUS: EVALUATION_CLAIM_STATUS_LABELS[2],
            COL_RISK_FLAGS: EVALUATION_NONE_VALUE,
            COL_SUPPORTING_IMAGE_IDS: f"{MODEL_UNKNOWN_IMAGE_ID}{PREFILTER_DUPLICATE_TEST_SUFFIX}",
        },
    ]
    summary = evaluate_predictions(predicted_rows, expected_rows)
    matrix = summary[EVALUATION_METRIC_CLAIM_STATUS_CONFUSION_MATRIX]
    assert matrix[EVALUATION_CLAIM_STATUS_LABELS[0]][EVALUATION_CLAIM_STATUS_LABELS[0]] == 1
    assert matrix[EVALUATION_CLAIM_STATUS_LABELS[1]][EVALUATION_CLAIM_STATUS_LABELS[2]] == 1
    assert summary[EVALUATION_METRIC_RISK_FLAGS_JACCARD] == 0.75
    assert summary[EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD] == 0.5


if __name__ == "__main__":
    run_smoke_test()
