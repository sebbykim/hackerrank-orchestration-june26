"""
metrics.py - Evaluation metrics for labeled sample claims.

WHAT:  This module will compute per-field accuracy, claim_status macro-F1,
       confusion matrices, and set-overlap metrics for multi-value fields.
WHY:   Evaluation is required as a deliverable, and keeping metrics isolated
       makes model-configuration comparisons reproducible and inspectable.
STEPS: Stub for STEPS.md Phase 9; created in Phase 0 item 3.
IN:    Predicted output rows and labeled sample_claims.csv rows.
OUT:   Metric summaries used by the evaluation report in later phases.
"""
