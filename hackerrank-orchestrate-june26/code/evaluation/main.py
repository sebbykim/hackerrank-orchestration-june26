"""
main.py - Evaluation entry point for labeled sample claims.

WHAT:  This file runs the pipeline on dataset/sample_claims.csv, compares the
       Sonnet and Opus configuration labels, computes Phase 9 metrics, and
       writes the operational evaluation report.
WHY:   The challenge requires an evaluation workflow under code/evaluation so
       reviewers can inspect quality and cost/latency tradeoffs before final
       submission. The runner supports real Claude clients when credentials
       exist and a deterministic mock fallback when they do not.
STEPS: Implements STEPS.md Phase 9 item 2 and DoD.
IN:    Labeled sample rows, supporting CSVs, local sample images, and the
       ANTHROPIC_API_KEY environment variable when real evaluation is desired.
OUT:   Printed metrics and evaluation_report.md.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from constants import (
    ANTHROPIC_API_KEY_ENV_VAR,
    CLAIMS_CSV,
    COL_IMAGE_PATHS,
    COMPARISON_CLAUDE_MODEL_ID,
    DEFAULT_CLAUDE_MODEL_ID,
    EVALUATION_API_KEY_MISSING_NOTE,
    EVALUATION_API_KEY_PRESENT_NOTE,
    EVALUATION_APPROX_IMAGE_INPUT_TOKENS_PER_IMAGE,
    EVALUATION_APPROX_OUTPUT_TOKENS_PER_CLAIM,
    EVALUATION_APPROX_TEXT_INPUT_TOKENS_PER_CLAIM,
    EVALUATION_BATCH_DISCOUNT_FACTOR,
    EVALUATION_CACHE_NOTE,
    EVALUATION_CACHE_READ_MULTIPLIER,
    EVALUATION_CACHE_WRITE_MULTIPLIER,
    EVALUATION_CLAIM_STATUS_LABELS,
    EVALUATION_CONFIG_LABEL_MOCK_SUFFIX,
    EVALUATION_CONFIG_KEY_CLIENT,
    EVALUATION_CONFIG_KEY_LABEL,
    EVALUATION_CONFIG_KEY_MODEL_ID,
    EVALUATION_CONFIG_KEY_USES_REAL_API,
    EVALUATION_CONFIG_MODEL_IDS,
    EVALUATION_CONFUSION_TABLE_SEPARATOR,
    EVALUATION_CONFUSION_TABLE_HEADER,
    EVALUATION_FIELD_TABLE_SEPARATOR,
    EVALUATION_FIELD_TABLE_HEADER,
    EVALUATION_HEADLINE_TABLE_HEADER,
    EVALUATION_METRIC_CLAIM_STATUS_CONFUSION_MATRIX,
    EVALUATION_METRIC_CLAIM_STATUS_MACRO_F1,
    EVALUATION_METRIC_FIELD_ACCURACY,
    EVALUATION_METRIC_RISK_FLAGS_JACCARD,
    EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD,
    EVALUATION_MOCK_PAID_MODEL_CALLS,
    EVALUATION_MODEL_CALLS_PER_ROW,
    EVALUATION_OPERATIONAL_BATCHING_NOTE,
    EVALUATION_OPERATIONAL_COST_NOTE,
    EVALUATION_OPERATIONAL_RETRY_NOTE,
    EVALUATION_OPUS_INPUT_PRICE_PER_MTOK,
    EVALUATION_OPUS_OUTPUT_PRICE_PER_MTOK,
    EVALUATION_REPORT,
    EVALUATION_REPORT_TITLE,
    EVALUATION_RESULT_KEY_METRICS,
    EVALUATION_RESULT_KEY_MODEL_CALLS,
    EVALUATION_RESULT_KEY_PAID_MODEL_CALLS,
    EVALUATION_RESULT_KEY_PREDICTED_ROWS,
    EVALUATION_RESULT_KEY_RUNTIME_SECONDS,
    EVALUATION_RPM_UNIT,
    EVALUATION_SECTION_CONFUSION,
    EVALUATION_SECTION_FIELD_ACCURACY,
    EVALUATION_SECTION_HEADLINE,
    EVALUATION_SECTION_OPERATIONAL,
    EVALUATION_SECTION_RUN_MODE,
    EVALUATION_SONNET_INPUT_PRICE_PER_MTOK,
    EVALUATION_SONNET_OUTPUT_PRICE_PER_MTOK,
    EVALUATION_STDOUT_WROTE_PREFIX,
    EVALUATION_TABLE_SEPARATOR,
    EVALUATION_TOKEN_KEY_INPUT,
    EVALUATION_TOKEN_KEY_OUTPUT,
    EVALUATION_TOKEN_KEY_TOTAL,
    EVALUATION_TOKENS_PER_MTOK,
    EVALUATION_TPM_UNIT,
    EXPECTED_SAMPLE_CLAIMS_ROW_COUNT,
    EXPECTED_TEST_CLAIMS_ROW_COUNT,
    INPUT_COLUMNS,
    SAMPLE_CSV,
)
from io_loaders import (
    load_claims,
    load_evidence_requirements,
    load_history,
    load_sample_claims,
    resolve_image_paths,
)
from metrics import evaluate_predictions
from mock_model import MockModelClient
from model_client import ClaudeModelClient, load_env_file
from pipeline import process_claim


EvaluationConfig = Dict[str, Any]
EvaluationResult = Dict[str, Any]


def _sample_input_row(row: Mapping[str, str]) -> Dict[str, str]:
    """Strip labels from a sample row before passing it to the pipeline.

    The evaluation must compare against labels, not leak them into extraction,
    prompts, cache keys, or model context.
    """
    return {column: row[column] for column in INPUT_COLUMNS}


def _has_api_key() -> bool:
    """Return whether real Claude evaluation can be attempted.

    Secrets are read only from the environment and never printed or included in
    the report, preserving the AGENTS/CODEX secret-handling contract.
    """
    load_env_file()
    return bool(os.environ.get(ANTHROPIC_API_KEY_ENV_VAR))


def _evaluation_configs() -> List[EvaluationConfig]:
    """Build the two required evaluation configs.

    When ANTHROPIC_API_KEY is absent, both configs intentionally use the mock
    client but keep the Sonnet/Opus labels so the report remains structurally
    comparable and runnable offline.
    """
    if _has_api_key():
        return [
            {
                EVALUATION_CONFIG_KEY_LABEL: model_id,
                EVALUATION_CONFIG_KEY_MODEL_ID: model_id,
                EVALUATION_CONFIG_KEY_CLIENT: ClaudeModelClient(model_id=model_id),
                EVALUATION_CONFIG_KEY_USES_REAL_API: True,
            }
            for model_id in EVALUATION_CONFIG_MODEL_IDS
        ]
    return [
        {
            EVALUATION_CONFIG_KEY_LABEL: f"{model_id}{EVALUATION_CONFIG_LABEL_MOCK_SUFFIX}",
            EVALUATION_CONFIG_KEY_MODEL_ID: model_id,
            EVALUATION_CONFIG_KEY_CLIENT: MockModelClient(),
            EVALUATION_CONFIG_KEY_USES_REAL_API: False,
        }
        for model_id in EVALUATION_CONFIG_MODEL_IDS
    ]


def _count_images(rows: List[Mapping[str, str]]) -> int:
    """Count resolved image references for operational reporting.

    The report uses image count to approximate vision input tokens because
    vision is billed as input under the Phase 9 pricing assumptions.
    """
    return sum(len(resolve_image_paths(row[COL_IMAGE_PATHS])) for row in rows)


def _approx_tokens(row_count: int, image_count: int) -> Dict[str, int]:
    """Estimate input and output tokens from row/image counts.

    The Anthropic SDK usage telemetry is not available in the mock path, so the
    report uses fixed transparent assumptions instead of pretending exact costs.
    """
    input_tokens = (
        row_count * EVALUATION_APPROX_TEXT_INPUT_TOKENS_PER_CLAIM
        + image_count * EVALUATION_APPROX_IMAGE_INPUT_TOKENS_PER_IMAGE
    )
    output_tokens = row_count * EVALUATION_APPROX_OUTPUT_TOKENS_PER_CLAIM
    return {
        EVALUATION_TOKEN_KEY_INPUT: input_tokens,
        EVALUATION_TOKEN_KEY_OUTPUT: output_tokens,
        EVALUATION_TOKEN_KEY_TOTAL: input_tokens + output_tokens,
    }


def _cost_estimate(
    input_tokens: int,
    output_tokens: int,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
) -> float:
    """Estimate Claude cost from token counts and MTok pricing.

    Args:
        input_tokens: Approximate input tokens, including vision.
        output_tokens: Approximate output tokens.
        input_price_per_mtok: Input price per million tokens.
        output_price_per_mtok: Output price per million tokens.

    Returns:
        Approximate dollar cost for the run.
    """
    return (
        input_tokens / EVALUATION_TOKENS_PER_MTOK * input_price_per_mtok
        + output_tokens / EVALUATION_TOKENS_PER_MTOK * output_price_per_mtok
    )


def _config_cost_estimate(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Select the Phase 9 pricing table for a model ID.

    Sonnet and Opus are the only comparison configs in STEPS Phase 9, so any
    unknown value is treated as Opus-priced only when it matches that constant.
    """
    if model_id == DEFAULT_CLAUDE_MODEL_ID:
        return _cost_estimate(
            input_tokens,
            output_tokens,
            EVALUATION_SONNET_INPUT_PRICE_PER_MTOK,
            EVALUATION_SONNET_OUTPUT_PRICE_PER_MTOK,
        )
    return _cost_estimate(
        input_tokens,
        output_tokens,
        EVALUATION_OPUS_INPUT_PRICE_PER_MTOK,
        EVALUATION_OPUS_OUTPUT_PRICE_PER_MTOK,
    )


def _evaluate_config(
    config: EvaluationConfig,
    sample_rows: List[Mapping[str, str]],
    history: Mapping[str, Mapping[str, str]],
    requirements: Mapping[object, Mapping[str, str]],
) -> EvaluationResult:
    """Run the pipeline and metrics for one evaluation config.

    A temporary cache directory is used per config because the Phase 6 cache key
    intentionally depends on input content and prompt version, not model ID.
    Separate caches keep model comparisons honest without changing cache design.
    """
    input_rows = [_sample_input_row(row) for row in sample_rows]
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        predicted_rows = [
            process_claim(
                row,
                history,
                requirements,
                config[EVALUATION_CONFIG_KEY_CLIENT],
                cache_dir,
            )
            for row in input_rows
        ]
    duration_seconds = time.perf_counter() - started_at
    metrics = evaluate_predictions(predicted_rows, sample_rows)
    model_calls = len(sample_rows) * EVALUATION_MODEL_CALLS_PER_ROW
    return {
        EVALUATION_CONFIG_KEY_LABEL: config[EVALUATION_CONFIG_KEY_LABEL],
        EVALUATION_CONFIG_KEY_MODEL_ID: config[EVALUATION_CONFIG_KEY_MODEL_ID],
        EVALUATION_CONFIG_KEY_USES_REAL_API: config[EVALUATION_CONFIG_KEY_USES_REAL_API],
        EVALUATION_RESULT_KEY_METRICS: metrics,
        EVALUATION_RESULT_KEY_RUNTIME_SECONDS: duration_seconds,
        EVALUATION_RESULT_KEY_MODEL_CALLS: model_calls,
        EVALUATION_RESULT_KEY_PAID_MODEL_CALLS: (
            model_calls
            if config[EVALUATION_CONFIG_KEY_USES_REAL_API]
            else EVALUATION_MOCK_PAID_MODEL_CALLS
        ),
        EVALUATION_RESULT_KEY_PREDICTED_ROWS: predicted_rows,
    }


def _format_score(value: float) -> str:
    """Format metric values consistently for stdout and Markdown.

    Keeping display formatting in one helper avoids tiny report inconsistencies
    when the same metric appears in headline and detailed sections.
    """
    return f"{value:.3f}"


def _print_metrics(results: List[EvaluationResult]) -> None:
    """Print concise headline metrics for command-line evaluation use.

    The full operational details are written to Markdown; stdout stays compact
    so a reviewer can see whether the run completed and compare configs quickly.
    """
    for result in results:
        metrics = result[EVALUATION_RESULT_KEY_METRICS]
        print(
            f"{result[EVALUATION_CONFIG_KEY_LABEL]}: "
            f"claim_status_macro_f1={_format_score(metrics[EVALUATION_METRIC_CLAIM_STATUS_MACRO_F1])}, "
            f"risk_flags_jaccard={_format_score(metrics[EVALUATION_METRIC_RISK_FLAGS_JACCARD])}, "
            f"supporting_image_ids_jaccard={_format_score(metrics[EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD])}"
        )


def _headline_table(results: List[EvaluationResult]) -> List[str]:
    """Build the Markdown headline comparison table.

    The table includes quality metrics plus operational call/runtime fields so
    Phase 9's model comparison is both accuracy- and cost-aware.
    """
    lines = [
        EVALUATION_HEADLINE_TABLE_HEADER,
        EVALUATION_TABLE_SEPARATOR,
    ]
    for result in results:
        metrics = result[EVALUATION_RESULT_KEY_METRICS]
        lines.append(
            "| {label} | {macro_f1} | {risk} | {supporting} | {runtime} | {model_calls} | {paid_model_calls} |".format(
                label=result[EVALUATION_CONFIG_KEY_LABEL],
                macro_f1=_format_score(metrics[EVALUATION_METRIC_CLAIM_STATUS_MACRO_F1]),
                risk=_format_score(metrics[EVALUATION_METRIC_RISK_FLAGS_JACCARD]),
                supporting=_format_score(metrics[EVALUATION_METRIC_SUPPORTING_IMAGE_IDS_JACCARD]),
                runtime=_format_score(result[EVALUATION_RESULT_KEY_RUNTIME_SECONDS]),
                model_calls=result[EVALUATION_RESULT_KEY_MODEL_CALLS],
                paid_model_calls=result[EVALUATION_RESULT_KEY_PAID_MODEL_CALLS],
            )
        )
    return lines


def _confusion_matrix_lines(result: EvaluationResult) -> List[str]:
    """Render one claim_status confusion matrix as Markdown.

    Rows are expected labels and columns are predicted labels, matching the
    metrics module's nested dictionary orientation.
    """
    matrix = result[EVALUATION_RESULT_KEY_METRICS][EVALUATION_METRIC_CLAIM_STATUS_CONFUSION_MATRIX]
    lines = [
        f"### {result[EVALUATION_CONFIG_KEY_LABEL]}",
        EVALUATION_CONFUSION_TABLE_HEADER,
        EVALUATION_CONFUSION_TABLE_SEPARATOR,
    ]
    for expected_label in EVALUATION_CLAIM_STATUS_LABELS:
        cells = [str(matrix[expected_label][predicted_label]) for predicted_label in EVALUATION_CLAIM_STATUS_LABELS]
        lines.append(f"| {expected_label} | {' | '.join(cells)} |")
    return lines


def _field_accuracy_lines(result: EvaluationResult) -> List[str]:
    """Render exact per-field accuracy for one config.

    Exact string fields are intentionally separate from Jaccard-scored set
    fields because reasons/justifications behave differently from risk lists.
    """
    field_scores = result[EVALUATION_RESULT_KEY_METRICS][EVALUATION_METRIC_FIELD_ACCURACY]
    lines = [
        f"### {result[EVALUATION_CONFIG_KEY_LABEL]}",
        EVALUATION_FIELD_TABLE_HEADER,
        EVALUATION_FIELD_TABLE_SEPARATOR,
    ]
    for field, score in field_scores.items():
        lines.append(f"| {field} | {_format_score(score)} |")
    return lines


def _operational_lines(
    sample_rows: List[Mapping[str, str]],
    test_rows: List[Mapping[str, str]],
    sample_image_count: int,
    test_image_count: int,
    results: List[EvaluationResult],
) -> List[str]:
    """Build the operational analysis section required by Phase 9.

    It covers model calls, token/cost assumptions, image volume, runtime,
    request/token rates, batching, caching, and retry behavior.
    """
    sample_tokens = _approx_tokens(len(sample_rows), sample_image_count)
    test_tokens = _approx_tokens(len(test_rows), test_image_count)
    lines = [
        f"- Sample evaluation rows: {len(sample_rows)} labeled claims, {sample_image_count} images.",
        f"- Full test set scale: {len(test_rows)} input claims, {test_image_count} images.",
        f"- Token assumptions per claim: {EVALUATION_APPROX_TEXT_INPUT_TOKENS_PER_CLAIM} text input, {EVALUATION_APPROX_IMAGE_INPUT_TOKENS_PER_IMAGE} input per image, {EVALUATION_APPROX_OUTPUT_TOKENS_PER_CLAIM} output.",
        f"- {EVALUATION_OPERATIONAL_COST_NOTE}",
        f"- Sample token estimate: {sample_tokens[EVALUATION_TOKEN_KEY_INPUT]} input, {sample_tokens[EVALUATION_TOKEN_KEY_OUTPUT]} output.",
        f"- Full test token estimate: {test_tokens[EVALUATION_TOKEN_KEY_INPUT]} input, {test_tokens[EVALUATION_TOKEN_KEY_OUTPUT]} output.",
        f"- Full test Sonnet estimate: ${_config_cost_estimate(DEFAULT_CLAUDE_MODEL_ID, test_tokens[EVALUATION_TOKEN_KEY_INPUT], test_tokens[EVALUATION_TOKEN_KEY_OUTPUT]):.4f}.",
        f"- Full test Opus estimate: ${_config_cost_estimate(COMPARISON_CLAUDE_MODEL_ID, test_tokens[EVALUATION_TOKEN_KEY_INPUT], test_tokens[EVALUATION_TOKEN_KEY_OUTPUT]):.4f}.",
        f"- Batch API cost multiplier assumption: {EVALUATION_BATCH_DISCOUNT_FACTOR}; prompt cache write/read multipliers: {EVALUATION_CACHE_WRITE_MULTIPLIER}/{EVALUATION_CACHE_READ_MULTIPLIER}.",
        f"- {EVALUATION_OPERATIONAL_BATCHING_NOTE}",
        f"- {EVALUATION_CACHE_NOTE}",
        f"- {EVALUATION_OPERATIONAL_RETRY_NOTE}",
    ]
    for result in results:
        minutes = max(
            result[EVALUATION_RESULT_KEY_RUNTIME_SECONDS] / 60,
            1 / EVALUATION_TOKENS_PER_MTOK,
        )
        tokens = sample_tokens[EVALUATION_TOKEN_KEY_TOTAL]
        rpm = result[EVALUATION_RESULT_KEY_MODEL_CALLS] / minutes
        tpm = tokens / minutes
        lines.append(
            f"- {result[EVALUATION_CONFIG_KEY_LABEL]} runtime: {_format_score(result[EVALUATION_RESULT_KEY_RUNTIME_SECONDS])}s; "
            f"approx throughput {rpm:.1f} {EVALUATION_RPM_UNIT}, {tpm:.1f} {EVALUATION_TPM_UNIT}."
        )
    return lines


def _write_report(
    results: List[EvaluationResult],
    sample_rows: List[Mapping[str, str]],
    test_rows: List[Mapping[str, str]],
    sample_image_count: int,
    test_image_count: int,
) -> None:
    """Write the generated Phase 9 Markdown report.

    The report is committed because the challenge layout expects an
    `evaluation_report.md` artifact under code/evaluation.
    """
    run_mode_note = EVALUATION_API_KEY_PRESENT_NOTE if _has_api_key() else EVALUATION_API_KEY_MISSING_NOTE
    lines = [
        EVALUATION_REPORT_TITLE,
        "",
        EVALUATION_SECTION_RUN_MODE,
        "",
        run_mode_note,
        "",
        EVALUATION_CACHE_NOTE,
        "",
        EVALUATION_SECTION_HEADLINE,
        "",
        *_headline_table(results),
        "",
        EVALUATION_SECTION_CONFUSION,
        "",
    ]
    for result in results:
        lines.extend(_confusion_matrix_lines(result))
        lines.append("")
    lines.extend([EVALUATION_SECTION_FIELD_ACCURACY, ""])
    for result in results:
        lines.extend(_field_accuracy_lines(result))
        lines.append("")
    lines.extend([EVALUATION_SECTION_OPERATIONAL, ""])
    lines.extend(
        _operational_lines(
            sample_rows,
            test_rows,
            sample_image_count,
            test_image_count,
            results,
        )
    )
    EVALUATION_REPORT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    """Run the full Phase 9 evaluation workflow.

    Raises:
        AssertionError: If the locked sample/test row counts are not present,
            because the DoD depends on scoring all 20 labeled rows.
    """
    sample_rows = load_sample_claims(SAMPLE_CSV)
    test_rows = load_claims(CLAIMS_CSV)
    assert len(sample_rows) == EXPECTED_SAMPLE_CLAIMS_ROW_COUNT
    assert len(test_rows) == EXPECTED_TEST_CLAIMS_ROW_COUNT
    history = load_history()
    requirements = load_evidence_requirements()
    configs = _evaluation_configs()
    results = [
        _evaluate_config(config, sample_rows, history, requirements)
        for config in configs
    ]
    _print_metrics(results)
    _write_report(
        results,
        sample_rows,
        test_rows,
        _count_images(sample_rows),
        _count_images(test_rows),
    )
    print(f"{EVALUATION_STDOUT_WROTE_PREFIX} {EVALUATION_REPORT}")


if __name__ == "__main__":
    main()
