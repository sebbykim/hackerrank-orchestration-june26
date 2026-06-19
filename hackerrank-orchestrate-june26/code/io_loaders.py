"""
io_loaders.py - Deterministic CSV and image-path loading helpers.

WHAT:  This module will read the claim, sample, history, and evidence CSV files;
       preserve input row order; join supporting context; and resolve image
       paths relative to the dataset directory.
WHY:   Keeping IO separate from model and validation logic makes the pipeline
       reproducible and lets later phases verify dataset contracts before any
       reasoning runs.
STEPS: Stub for STEPS.md Phase 1; created in Phase 0 item 3.
IN:    CSV files under dataset/ and semicolon-separated image path fields.
OUT:   In-memory row dictionaries, indexed supporting data, and resolved image
       identifiers/paths in later phases.
"""
