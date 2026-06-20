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
EVIDENCE_REQUIREMENT_TEXT_SEPARATOR = " "
PROMPT_VERSION = "damage-claim-v1"

DEFAULT_CLAUDE_MODEL_ID = "claude-sonnet-4-6"
COMPARISON_CLAUDE_MODEL_ID = "claude-opus-4-8"
MODEL_ID_ENV_VAR = "ANTHROPIC_MODEL_ID"
ANTHROPIC_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

EXPECTED_SAMPLE_CLAIMS_ROW_COUNT = 20
EXPECTED_TEST_CLAIMS_ROW_COUNT = 44
EXPECTED_HISTORY_ROW_COUNT = 47
EXPECTED_EVIDENCE_REQUIREMENTS_ROW_COUNT = 11

PREFILTER_KEY_IMAGE_ID = "image_id"
PREFILTER_KEY_PATH = "path"
PREFILTER_KEY_DECODE_OK = "decode_ok"
PREFILTER_KEY_BLUR_LAPLACIAN_VAR = "blur_laplacian_var"
PREFILTER_KEY_MEAN_BRIGHTNESS = "mean_brightness"
PREFILTER_KEY_GLARE_FRACTION = "glare_fraction"
PREFILTER_KEY_WIDTH = "width"
PREFILTER_KEY_HEIGHT = "height"
PREFILTER_KEY_FLAGS = "flags"
PREFILTER_KEY_EXIF = "exif"
PREFILTER_KEY_NON_ORIGINAL_SIGNAL = "non_original_signal"
PREFILTER_KEY_SIGNAL_SCORE = "signal_score"
PREFILTER_KEY_SIGNAL_REASONS = "signal_reasons"
PREFILTER_KEY_MISSING_CAMERA_EXIF = "missing_camera_exif"
PREFILTER_KEY_EDITOR_SOFTWARE = "editor_software"
PREFILTER_KEY_SCREENSHOT_DIMENSIONS = "screenshot_dimensions"
PREFILTER_KEY_PER_IMAGE = "per_image"
PREFILTER_KEY_KEPT_IMAGE_IDS = "kept_image_ids"
PREFILTER_KEY_KEPT_IMAGES = "kept_images"
PREFILTER_KEY_DROPPED_DUPLICATES = "dropped_duplicates"
PREFILTER_KEY_DEDUP = "dedup"
PREFILTER_KEY_ALL_IMAGES_DEAD = "all_images_dead"
PREFILTER_DUPLICATE_TEST_SUFFIX = "_duplicate"

EXIF_REASON_MISSING_CAMERA = "missing_camera_exif"
EXIF_REASON_EDITOR_SOFTWARE = "editor_software"
EXIF_REASON_SCREENSHOT_DIMENSIONS = "screenshot_dimensions"
# EXIF tag IDs cover common camera provenance fields: make, model, software,
# original timestamp, and lens model. Missing tags are weak evidence only.
EXIF_CAMERA_TAG_IDS = frozenset((271, 272, 306, 36867, 42036))
EXIF_SOFTWARE_TAG_ID = 305
EXIF_EDITOR_SOFTWARE_MARKERS = frozenset(
    (
        "adobe",
        "photoshop",
        "gimp",
        "lightroom",
        "snapseed",
        "pixelmator",
    )
)
# Screenshot-dimension heuristic: only long, phone/screen-shaped images trigger
# this weak signal; ordinary landscape photos are left to the VLM.
EXIF_SCREENSHOT_LONG_EDGE_MIN = 1000
EXIF_SCREENSHOT_WIDE_ASPECT_RATIO = 1.75
EXIF_SCREENSHOT_TALL_ASPECT_RATIO = 0.57
EXIF_MISSING_CAMERA_SIGNAL_SCORE = 1
EXIF_EDITOR_SOFTWARE_SIGNAL_SCORE = 2
EXIF_SCREENSHOT_DIMENSION_SIGNAL_SCORE = 1
# Phase 2 calibration: missing camera EXIF appears across all sample images, so
# it is kept as a weak score but does not set the boolean signal alone.
EXIF_NON_ORIGINAL_SIGNAL_SCORE_THRESHOLD = 2

PREFILTER_DEFAULT_IMAGE_DIMENSION = 0
PREFILTER_DEFAULT_MEASUREMENT_VALUE = 0.0
PREFILTER_DEFAULT_SIGNAL_SCORE = 0
# Near-white saturation cutoff used to compute glare_fraction.
PREFILTER_GLARE_PIXEL_VALUE_THRESHOLD = 245

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

# Calibrated in Phase 2 on the 29 images referenced by the 20 labeled sample
# rows: blur min=7.75, next=19.77, p10=38.42. A 30.0 cutoff flags only the
# extreme bottom tail and leaves borderline images for the VLM (design §5.1).
PREFILTER_BLUR_LAPLACIAN_VAR_THRESHOLD = 30.0

# Calibrated in Phase 2: sample brightness min=38.03, next=49.35, p10=79.29.
# A 45.0 cutoff marks only the darkest outlier as low-light signal.
PREFILTER_MEAN_BRIGHTNESS_LOW_THRESHOLD = 45.0

# Calibrated in Phase 2: sample glare p90=0.0438, top values=0.0563/0.0584.
# A 0.057 cutoff catches the saturated outlier without flagging normal highlights.
PREFILTER_GLARE_FRACTION_THRESHOLD = 0.057

# Calibrated in Phase 2: sample width min=275 and p10=356. A 320px floor flags
# only very narrow uploads as a cropped/obstructed signal.
PREFILTER_MIN_IMAGE_WIDTH = 320

# Calibrated in Phase 2: sample height min=134 and p10=183. A 160px floor flags
# strip-like uploads while preserving the next observed sample band.
PREFILTER_MIN_IMAGE_HEIGHT = 160

# Calibrated in Phase 2: same-claim sample phash distances have minimum 24. A
# distance <=8 is therefore conservative and intended only for exact/near duplicates.
PREFILTER_PHASH_DUPLICATE_DISTANCE_THRESHOLD = 8

# Calibrated in Phase 2: sample brightness min=38.03. A 5.0 dead-image cutoff
# catches fully black/unreadable decodes without short-circuiting dark but usable photos.
PREFILTER_DEAD_MEAN_BRIGHTNESS_THRESHOLD = 5.0

CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE = "claimed_issue_type"
CLAIM_EXTRACTION_KEY_CLAIMED_OBJECT_PART = "claimed_object_part"
CLAIM_EXTRACTION_KEY_SEVERITY_HINT = "severity_hint"
CLAIM_EXTRACTION_KEY_UNCERTAINTY = "uncertainty"
CLAIM_EXTRACTION_KEY_EVIDENCE_NEEDED = "evidence_needed"
CLAIM_TEXT_NORMALIZED_SEPARATOR = " "
CLAIM_CONVERSATION_TURN_SEPARATOR = "|"
CLAIM_CUSTOMER_SPEAKER_PREFIX = "customer:"
CLAIM_EVIDENCE_NEEDED_TEMPLATE = "{base}; focus on {object_part} and {issue_type}"
CLAIM_EVIDENCE_NEEDED_UNKNOWN_TEMPLATE = "{base}; focus on the claimed damage and part"
CLAIM_EVIDENCE_NEEDED_GENERIC = "clear image of the claimed object, part, and condition"

CLAIM_UNCERTAINTY_LOW = "low"
CLAIM_UNCERTAINTY_MEDIUM = "medium"
CLAIM_UNCERTAINTY_HIGH = "high"

CLAIM_UNCERTAINTY_HIGH_KEYWORDS = frozenset(
    (
        "not fully sure",
        "not sure",
        "confused",
        "could not decide",
        "overthinking",
        "do not want to claim the wrong thing",
        "not sure if",
    )
)
CLAIM_UNCERTAINTY_MEDIUM_KEYWORDS = frozenset(
    (
        "i think",
        "maybe",
        "may be",
        "might",
        "seems",
        "seem",
        "looks like",
        "appears",
        "worried",
        "possible",
        "lag raha",
        "lagta",
    )
)

CLAIM_SEVERITY_HIGH_KEYWORDS = frozenset(
    (
        "shattered",
        "shatter",
        "badly",
        "severe",
        "missing",
        "not inside",
        "broken",
        "broke",
        "torn open",
        "unreadable",
    )
)
CLAIM_SEVERITY_LOW_KEYWORDS = frozenset(
    (
        "small",
        "minor",
        "nothing major",
        "slightly",
        "scratch",
        "mark",
        "scuff",
    )
)
CLAIM_SEVERITY_MEDIUM_KEYWORDS = frozenset(
    (
        "dent",
        "crack",
        "cracked",
        "crushed",
        "water damaged",
        "water damage",
        "stain",
        "torn",
        "damaged",
        "damage",
    )
)

CLAIM_ISSUE_KEYWORDS = (
    (ISSUE_TYPE_GLASS_SHATTER, ("shattered", "shatter")),
    (ISSUE_TYPE_MISSING_PART, ("missing", "not inside", "faltan", "came off")),
    (ISSUE_TYPE_BROKEN_PART, ("broken", "broke", "breakage", "wobbles", "toot gaya")),
    (ISSUE_TYPE_CRACK, ("crack", "cracked", "cracking", "crack lines")),
    (ISSUE_TYPE_DENT, ("dent", "dented", "hail dents", "ding")),
    (ISSUE_TYPE_SCRATCH, ("scratch", "scratched", "scrape", "mark", "scuff")),
    (ISSUE_TYPE_TORN_PACKAGING, ("torn", "opened", "open jaisa", "phati", "seal affected")),
    (ISSUE_TYPE_CRUSHED_PACKAGING, ("crushed", "crush", "dab gaya", "bad condition")),
    (ISSUE_TYPE_WATER_DAMAGE, ("water damage", "water damaged", "wet", "liquid damage")),
    (ISSUE_TYPE_STAIN, ("stain", "stained", "oily mark", "oil stain", "sticky")),
)

CLAIM_OBJECT_PART_KEYWORDS_BY_OBJECT = MappingProxyType(
    {
        CLAIM_OBJECT_CAR: (
            (OBJECT_PART_FRONT_BUMPER, ("front bumper",)),
            (OBJECT_PART_REAR_BUMPER, ("rear bumper", "back bumper", "rear side", "back of the car")),
            (OBJECT_PART_SIDE_MIRROR, ("side mirror", "left mirror", "mirror")),
            (OBJECT_PART_HEADLIGHT, ("headlight", "front light")),
            (OBJECT_PART_TAILLIGHT, ("taillight", "back light", "tail light")),
            (OBJECT_PART_WINDSHIELD, ("windshield", "front glass")),
            (OBJECT_PART_DOOR, ("door", "door panel")),
            (OBJECT_PART_HOOD, ("hood", "top panel")),
            (OBJECT_PART_FENDER, ("fender",)),
            (OBJECT_PART_QUARTER_PANEL, ("quarter panel",)),
            (OBJECT_PART_BODY, ("body panel", "body")),
        ),
        CLAIM_OBJECT_LAPTOP: (
            (OBJECT_PART_SCREEN, ("screen", "display", "pantalla")),
            (OBJECT_PART_KEYBOARD, ("keyboard", "keys", "keycaps", "teclas")),
            (OBJECT_PART_TRACKPAD, ("trackpad", "palm-rest", "palm rest")),
            (OBJECT_PART_HINGE, ("hinge",)),
            (OBJECT_PART_LID, ("lid",)),
            (OBJECT_PART_CORNER, ("corner",)),
            (OBJECT_PART_PORT, ("port",)),
            (OBJECT_PART_BASE, ("base",)),
            (OBJECT_PART_BODY, ("outer body", "body", "side edge")),
        ),
        CLAIM_OBJECT_PACKAGE: (
            (OBJECT_PART_PACKAGE_CORNER, ("package corner", "box corner", "corner")),
            (OBJECT_PART_SEAL, ("seal", "tape", "flap")),
            (OBJECT_PART_LABEL, ("label",)),
            (OBJECT_PART_CONTENTS, ("contents", "product inside", "item inside")),
            (OBJECT_PART_ITEM, ("item", "product")),
            (OBJECT_PART_PACKAGE_SIDE, ("package side", "surface", "outside")),
            (OBJECT_PART_BOX, ("box", "delivery box", "shipping box", "cardboard box", "package")),
        ),
    }
)

CLAIM_EVIDENCE_NEEDED_BY_OBJECT = MappingProxyType(
    {
        CLAIM_OBJECT_CAR: "clear image of the claimed car part and visible surface damage",
        CLAIM_OBJECT_LAPTOP: "clear image of the claimed laptop part and visible physical damage",
        CLAIM_OBJECT_PACKAGE: "clear image of the package area or contents relevant to the claim",
    }
)
