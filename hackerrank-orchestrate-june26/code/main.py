"""
main.py - Terminal entry point for generating final claim predictions.

WHAT:  This file runs the claim-verification pipeline over the provided test
       claims and writes output.csv in the required 14-column schema.
WHY:   The project contract expects a stable, documented entry point that the
       evaluator and reviewer can run without discovering internal modules.
STEPS: Implements STEPS.md Phase 7 item 2 and Phase 8 item 2.
IN:    dataset/claims.csv plus supporting CSVs, local images, and selected
       model-client configuration.
OUT:   output.csv at the repository root.
"""

import argparse
import csv
import os
from pathlib import Path
from typing import Iterable, List

from constants import (
    CACHE_DIR,
    CLAIMS_CSV,
    DEFAULT_CLAUDE_MODEL_ID,
    EXPECTED_TEST_CLAIMS_ROW_COUNT,
    MAIN_ARG_CACHE_DIR,
    MAIN_ARG_CLAIMS,
    MAIN_ARG_CLIENT,
    MAIN_ARG_OUTPUT,
    MAIN_DESCRIPTION,
    MODEL_ID_ENV_VAR,
    OUTPUT_COLUMNS,
    OUTPUT_CSV,
    PIPELINE_CLIENT_CLAUDE,
    PIPELINE_CLIENT_ENV_VAR,
    PIPELINE_CLIENT_MOCK,
)
from io_loaders import Row, load_claims, load_evidence_requirements, load_history
from mock_model import MockModelClient
from model_client import ClaudeModelClient, ModelClient
from pipeline import process_claim


def _build_parser() -> argparse.ArgumentParser:
    """Build the Phase 7 command-line parser.

    Phase 8 supports the deterministic mock, the default/env Claude model, or a
    model ID provided directly as the client value.
    """
    parser = argparse.ArgumentParser(description=MAIN_DESCRIPTION)
    parser.add_argument(
        MAIN_ARG_CLIENT,
        default=os.environ.get(PIPELINE_CLIENT_ENV_VAR, PIPELINE_CLIENT_MOCK),
    )
    parser.add_argument(
        MAIN_ARG_CLAIMS,
        type=Path,
        default=CLAIMS_CSV,
    )
    parser.add_argument(
        MAIN_ARG_OUTPUT,
        type=Path,
        default=OUTPUT_CSV,
    )
    parser.add_argument(
        MAIN_ARG_CACHE_DIR,
        type=Path,
        default=CACHE_DIR,
    )
    return parser


def _model_client(client_name: str) -> ModelClient:
    """Instantiate the selected model client.

    `mock` keeps the zero-cost deterministic path. `claude` uses
    ANTHROPIC_MODEL_ID or the default Claude model. Any other value is treated
    as an explicit Claude model ID.
    """
    if client_name == PIPELINE_CLIENT_MOCK:
        return MockModelClient()
    if client_name == PIPELINE_CLIENT_CLAUDE:
        return ClaudeModelClient(
            model_id=os.environ.get(MODEL_ID_ENV_VAR, DEFAULT_CLAUDE_MODEL_ID)
        )
    return ClaudeModelClient(model_id=client_name)


def _write_output(rows: Iterable[Row], output_path: Path) -> None:
    """Write output rows in the exact required CSV column order.

    Args:
        rows: Validated output row dictionaries.
        output_path: Destination output.csv path.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in OUTPUT_COLUMNS})


def run(args: argparse.Namespace) -> List[Row]:
    """Run the configured mock pipeline and write output.csv.

    Args:
        args: Parsed command-line arguments from _build_parser().

    Returns:
        Validated output rows in the same order as the input claims.
    """
    claims = load_claims(Path(args.claims))
    history = load_history()
    requirements = load_evidence_requirements()
    client = _model_client(args.client)
    output_rows = [
        process_claim(row, history, requirements, client, Path(args.cache_dir))
        for row in claims
    ]
    assert len(output_rows) == len(claims)
    if Path(args.claims).resolve() == CLAIMS_CSV.resolve():
        assert len(output_rows) == EXPECTED_TEST_CLAIMS_ROW_COUNT
    _write_output(output_rows, Path(args.output))
    return output_rows


def main() -> None:
    """Parse CLI arguments and run the Phase 7 mock pipeline."""
    run(_build_parser().parse_args())


if __name__ == "__main__":
    main()
