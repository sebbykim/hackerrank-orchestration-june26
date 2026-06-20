"""
main.py - Terminal entry point for generating final claim predictions.

WHAT:  This file runs the claim-verification pipeline over the provided test
       claims and writes output.csv in the required 14-column schema.
WHY:   The project contract expects a stable, documented entry point that the
       evaluator and reviewer can run without discovering internal modules.
STEPS: Implements STEPS.md Phase 7 item 2.
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
    EXPECTED_TEST_CLAIMS_ROW_COUNT,
    MAIN_ARG_CACHE_DIR,
    MAIN_ARG_CLAIMS,
    MAIN_ARG_CLIENT,
    MAIN_ARG_CLIENT_CHOICES,
    MAIN_ARG_OUTPUT,
    MAIN_DESCRIPTION,
    MAIN_UNSUPPORTED_CLIENT_TEMPLATE,
    OUTPUT_COLUMNS,
    OUTPUT_CSV,
    PIPELINE_CLIENT_ENV_VAR,
    PIPELINE_CLIENT_MOCK,
)
from io_loaders import Row, load_claims, load_evidence_requirements, load_history
from mock_model import MockModelClient
from model_client import ModelClient
from pipeline import process_claim


def _build_parser() -> argparse.ArgumentParser:
    """Build the Phase 7 command-line parser.

    The only available client in Phase 7 is the deterministic mock; the flag is
    still present because STEPS requires client selection by flag/env before the
    real client is added in Phase 8.
    """
    parser = argparse.ArgumentParser(description=MAIN_DESCRIPTION)
    parser.add_argument(
        MAIN_ARG_CLIENT,
        choices=MAIN_ARG_CLIENT_CHOICES,
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

    Phase 7 only supports the mock client so the pipeline runs with zero API
    calls. The explicit factory keeps Phase 8's real-client addition isolated.
    """
    if client_name == PIPELINE_CLIENT_MOCK:
        return MockModelClient()
    raise ValueError(MAIN_UNSUPPORTED_CLIENT_TEMPLATE.format(client_name=client_name))


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
