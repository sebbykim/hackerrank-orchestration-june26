"""
constants.py - Shared contracts, paths, enums, and thresholds.

WHAT:  This file centralizes every meaningful string, enum value, output column,
       dataset path, model ID, and pre-filter threshold used by the claim-review
       pipeline. It is intentionally the only source of truth for the schema.
WHY:   STEPS Phase 0 locks contracts before any logic is written so later phases
       cannot drift into invented columns, values, paths, or thresholds.
STEPS: Implements STEPS.md Phase 0 items 2 and DoD contract checks.
IN:    Static project requirements from problem_statement.md, STEPS.md, and the
       verified CSV headers.
OUT:   Importable constants for loaders, validators, writers, prompts, and eval.
"""

from pathlib import Path
from types import MappingProxyType


REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
CLAIMS_CSV = DATASET_DIR / "claims.csv"
SAMPLE_CSV = DATASET_DIR / "sample_claims.csv"
HISTORY_CSV = DATASET_DIR / "user_history.csv"
EVIDENCE_CSV = DATASET_DIR / "evidence_requirements.csv"
OUTPUT_CSV = REPO_ROOT / "output.csv"

IMAGE_PATH_SEPARATOR = ";"
PROMPT_VERSION = "damage-claim-v1"

DEFAULT_CLAUDE_MODEL_ID = "claude-sonnet-4-6"
COMPARISON_CLAUDE_MODEL_ID = "claude-opus-4-8"
MODEL_ID_ENV_VAR = "ANTHROPIC_MODEL_ID"
ANTHROPIC_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

COL_USER_ID = "user_id"
COL_IMAGE_PATHS = "image_paths"
COL_USER_CLAIM = "user_claim"
COL_CLAIM_OBJECT = "claim_object"
COL_EVIDENCE_STANDARD_MET = "evidence_standard_met"
COL_EVIDENCE_STANDARD_MET_REASON = "evidence_standard_met_reason"
COL_RISK_FLAGS = "risk_flags"
COL_ISSUE_TYPE = "issue_type"
COL_OBJECT_PART = "object_part"
COL_CLAIM_STATUS = "claim_status"
COL_CLAIM_STATUS_JUSTIFICATION = "claim_status_justification"
COL_SUPPORTING_IMAGE_IDS = "supporting_image_ids"
COL_VALID_IMAGE = "valid_image"
COL_SEVERITY = "severity"

INPUT_COLUMNS = (
    COL_USER_ID,
    COL_IMAGE_PATHS,
    COL_USER_CLAIM,
    COL_CLAIM_OBJECT,
)

OUTPUT_COLUMNS = (
    COL_USER_ID,
    COL_IMAGE_PATHS,
    COL_USER_CLAIM,
    COL_CLAIM_OBJECT,
    COL_EVIDENCE_STANDARD_MET,
    COL_EVIDENCE_STANDARD_MET_REASON,
    COL_RISK_FLAGS,
    COL_ISSUE_TYPE,
    COL_OBJECT_PART,
    COL_CLAIM_STATUS,
    COL_CLAIM_STATUS_JUSTIFICATION,
    COL_SUPPORTING_IMAGE_IDS,
    COL_VALID_IMAGE,
    COL_SEVERITY,
)

COL_PAST_CLAIM_COUNT = "past_claim_count"
COL_ACCEPT_CLAIM = "accept_claim"
COL_MANUAL_REVIEW_CLAIM = "manual_review_claim"
COL_REJECTED_CLAIM = "rejected_claim"
COL_LAST_90_DAYS_CLAIM_COUNT = "last_90_days_claim_count"
COL_HISTORY_FLAGS = "history_flags"
COL_HISTORY_SUMMARY = "history_summary"

HISTORY_COLUMNS = (
    COL_USER_ID,
    COL_PAST_CLAIM_COUNT,
    COL_ACCEPT_CLAIM,
    COL_MANUAL_REVIEW_CLAIM,
    COL_REJECTED_CLAIM,
    COL_LAST_90_DAYS_CLAIM_COUNT,
    COL_HISTORY_FLAGS,
    COL_HISTORY_SUMMARY,
)

COL_REQUIREMENT_ID = "requirement_id"
COL_APPLIES_TO = "applies_to"
COL_MINIMUM_IMAGE_EVIDENCE = "minimum_image_evidence"

EVIDENCE_COLUMNS = (
    COL_REQUIREMENT_ID,
    COL_CLAIM_OBJECT,
    COL_APPLIES_TO,
    COL_MINIMUM_IMAGE_EVIDENCE,
)

CLAIM_OBJECT_CAR = "car"
CLAIM_OBJECT_LAPTOP = "laptop"
CLAIM_OBJECT_PACKAGE = "package"
CLAIM_OBJECT_ALL = "all"

ALLOWED_CLAIM_OBJECTS = frozenset(
    (
        CLAIM_OBJECT_CAR,
        CLAIM_OBJECT_LAPTOP,
        CLAIM_OBJECT_PACKAGE,
    )
)

CLAIM_STATUS_SUPPORTED = "supported"
CLAIM_STATUS_CONTRADICTED = "contradicted"
CLAIM_STATUS_NOT_ENOUGH_INFORMATION = "not_enough_information"

ALLOWED_CLAIM_STATUS = frozenset(
    (
        CLAIM_STATUS_SUPPORTED,
        CLAIM_STATUS_CONTRADICTED,
        CLAIM_STATUS_NOT_ENOUGH_INFORMATION,
    )
)

ISSUE_TYPE_DENT = "dent"
ISSUE_TYPE_SCRATCH = "scratch"
ISSUE_TYPE_CRACK = "crack"
ISSUE_TYPE_GLASS_SHATTER = "glass_shatter"
ISSUE_TYPE_BROKEN_PART = "broken_part"
ISSUE_TYPE_MISSING_PART = "missing_part"
ISSUE_TYPE_TORN_PACKAGING = "torn_packaging"
ISSUE_TYPE_CRUSHED_PACKAGING = "crushed_packaging"
ISSUE_TYPE_WATER_DAMAGE = "water_damage"
ISSUE_TYPE_STAIN = "stain"
ISSUE_TYPE_NONE = "none"
ISSUE_TYPE_UNKNOWN = "unknown"

ALLOWED_ISSUE_TYPES = frozenset(
    (
        ISSUE_TYPE_DENT,
        ISSUE_TYPE_SCRATCH,
        ISSUE_TYPE_CRACK,
        ISSUE_TYPE_GLASS_SHATTER,
        ISSUE_TYPE_BROKEN_PART,
        ISSUE_TYPE_MISSING_PART,
        ISSUE_TYPE_TORN_PACKAGING,
        ISSUE_TYPE_CRUSHED_PACKAGING,
        ISSUE_TYPE_WATER_DAMAGE,
        ISSUE_TYPE_STAIN,
        ISSUE_TYPE_NONE,
        ISSUE_TYPE_UNKNOWN,
    )
)

OBJECT_PART_FRONT_BUMPER = "front_bumper"
OBJECT_PART_REAR_BUMPER = "rear_bumper"
OBJECT_PART_DOOR = "door"
OBJECT_PART_HOOD = "hood"
OBJECT_PART_WINDSHIELD = "windshield"
OBJECT_PART_SIDE_MIRROR = "side_mirror"
OBJECT_PART_HEADLIGHT = "headlight"
OBJECT_PART_TAILLIGHT = "taillight"
OBJECT_PART_FENDER = "fender"
OBJECT_PART_QUARTER_PANEL = "quarter_panel"
OBJECT_PART_BODY = "body"
OBJECT_PART_UNKNOWN = "unknown"

ALLOWED_CAR_OBJECT_PARTS = frozenset(
    (
        OBJECT_PART_FRONT_BUMPER,
        OBJECT_PART_REAR_BUMPER,
        OBJECT_PART_DOOR,
        OBJECT_PART_HOOD,
        OBJECT_PART_WINDSHIELD,
        OBJECT_PART_SIDE_MIRROR,
        OBJECT_PART_HEADLIGHT,
        OBJECT_PART_TAILLIGHT,
        OBJECT_PART_FENDER,
        OBJECT_PART_QUARTER_PANEL,
        OBJECT_PART_BODY,
        OBJECT_PART_UNKNOWN,
    )
)

OBJECT_PART_SCREEN = "screen"
OBJECT_PART_KEYBOARD = "keyboard"
OBJECT_PART_TRACKPAD = "trackpad"
OBJECT_PART_HINGE = "hinge"
OBJECT_PART_LID = "lid"
OBJECT_PART_CORNER = "corner"
OBJECT_PART_PORT = "port"
OBJECT_PART_BASE = "base"

ALLOWED_LAPTOP_OBJECT_PARTS = frozenset(
    (
        OBJECT_PART_SCREEN,
        OBJECT_PART_KEYBOARD,
        OBJECT_PART_TRACKPAD,
        OBJECT_PART_HINGE,
        OBJECT_PART_LID,
        OBJECT_PART_CORNER,
        OBJECT_PART_PORT,
        OBJECT_PART_BASE,
        OBJECT_PART_BODY,
        OBJECT_PART_UNKNOWN,
    )
)

OBJECT_PART_BOX = "box"
OBJECT_PART_PACKAGE_CORNER = "package_corner"
OBJECT_PART_PACKAGE_SIDE = "package_side"
OBJECT_PART_SEAL = "seal"
OBJECT_PART_LABEL = "label"
OBJECT_PART_CONTENTS = "contents"
OBJECT_PART_ITEM = "item"

ALLOWED_PACKAGE_OBJECT_PARTS = frozenset(
    (
        OBJECT_PART_BOX,
        OBJECT_PART_PACKAGE_CORNER,
        OBJECT_PART_PACKAGE_SIDE,
        OBJECT_PART_SEAL,
        OBJECT_PART_LABEL,
        OBJECT_PART_CONTENTS,
        OBJECT_PART_ITEM,
        OBJECT_PART_UNKNOWN,
    )
)

ALLOWED_OBJECT_PARTS_BY_OBJECT = MappingProxyType(
    {
        CLAIM_OBJECT_CAR: ALLOWED_CAR_OBJECT_PARTS,
        CLAIM_OBJECT_LAPTOP: ALLOWED_LAPTOP_OBJECT_PARTS,
        CLAIM_OBJECT_PACKAGE: ALLOWED_PACKAGE_OBJECT_PARTS,
    }
)

RISK_FLAG_NONE = "none"
RISK_FLAG_BLURRY_IMAGE = "blurry_image"
RISK_FLAG_CROPPED_OR_OBSTRUCTED = "cropped_or_obstructed"
RISK_FLAG_LOW_LIGHT_OR_GLARE = "low_light_or_glare"
RISK_FLAG_WRONG_ANGLE = "wrong_angle"
RISK_FLAG_WRONG_OBJECT = "wrong_object"
RISK_FLAG_WRONG_OBJECT_PART = "wrong_object_part"
RISK_FLAG_DAMAGE_NOT_VISIBLE = "damage_not_visible"
RISK_FLAG_CLAIM_MISMATCH = "claim_mismatch"
RISK_FLAG_POSSIBLE_MANIPULATION = "possible_manipulation"
RISK_FLAG_NON_ORIGINAL_IMAGE = "non_original_image"
RISK_FLAG_TEXT_INSTRUCTION_PRESENT = "text_instruction_present"
RISK_FLAG_USER_HISTORY_RISK = "user_history_risk"
RISK_FLAG_MANUAL_REVIEW_REQUIRED = "manual_review_required"

ALLOWED_RISK_FLAGS = frozenset(
    (
        RISK_FLAG_NONE,
        RISK_FLAG_BLURRY_IMAGE,
        RISK_FLAG_CROPPED_OR_OBSTRUCTED,
        RISK_FLAG_LOW_LIGHT_OR_GLARE,
        RISK_FLAG_WRONG_ANGLE,
        RISK_FLAG_WRONG_OBJECT,
        RISK_FLAG_WRONG_OBJECT_PART,
        RISK_FLAG_DAMAGE_NOT_VISIBLE,
        RISK_FLAG_CLAIM_MISMATCH,
        RISK_FLAG_POSSIBLE_MANIPULATION,
        RISK_FLAG_NON_ORIGINAL_IMAGE,
        RISK_FLAG_TEXT_INSTRUCTION_PRESENT,
        RISK_FLAG_USER_HISTORY_RISK,
        RISK_FLAG_MANUAL_REVIEW_REQUIRED,
    )
)

SEVERITY_NONE = "none"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_UNKNOWN = "unknown"

ALLOWED_SEVERITY = frozenset(
    (
        SEVERITY_NONE,
        SEVERITY_LOW,
        SEVERITY_MEDIUM,
        SEVERITY_HIGH,
        SEVERITY_UNKNOWN,
    )
)

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_BLUR_LAPLACIAN_VAR_THRESHOLD = 0.0

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_MEAN_BRIGHTNESS_LOW_THRESHOLD = 0.0

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_GLARE_FRACTION_THRESHOLD = 1.0

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_MIN_IMAGE_WIDTH = 0

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_MIN_IMAGE_HEIGHT = 0

# Placeholder values only. Phase 2 calibrates these on sample images before
# pre-filter logic relies on them (STEPS Phase 0; design §5.1).
PREFILTER_PHASH_DUPLICATE_DISTANCE_THRESHOLD = 0
