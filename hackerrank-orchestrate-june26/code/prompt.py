"""
prompt.py - Claude prompt construction and response schema definition.

WHAT:  This module builds the system/user message blocks and defines the strict
       JSON schema expected from the vision model. It does not call a model.
WHY:   Prompt and schema definitions need one home so allowed values, injection
       defenses, and response contracts stay synchronized with validation.
STEPS: Implements STEPS.md Phase 5 items 1-2.
IN:    Claim context, evidence requirements, history context, pre-filter
       measurements, and image blocks.
OUT:   Claude message payloads and a response JSON schema.
"""

import base64
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from claim_extraction import extract_claim
from constants import (
    ALLOWED_CAR_OBJECT_PARTS,
    ALLOWED_CLAIM_OBJECTS,
    ALLOWED_CLAIM_STATUS,
    ALLOWED_ISSUE_TYPES,
    ALLOWED_LAPTOP_OBJECT_PARTS,
    ALLOWED_MODEL_IMAGE_USEFULNESS,
    ALLOWED_PACKAGE_OBJECT_PARTS,
    ALLOWED_RISK_FLAGS,
    ALLOWED_SEVERITY,
    CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE,
    COL_CLAIM_OBJECT,
    COL_CLAIM_STATUS,
    COL_CLAIM_STATUS_JUSTIFICATION,
    COL_EVIDENCE_STANDARD_MET,
    COL_EVIDENCE_STANDARD_MET_REASON,
    COL_IMAGE_PATHS,
    COL_ISSUE_TYPE,
    COL_OBJECT_PART,
    COL_RISK_FLAGS,
    COL_SEVERITY,
    COL_SUPPORTING_IMAGE_IDS,
    COL_USER_CLAIM,
    COL_USER_ID,
    COL_VALID_IMAGE,
    INPUT_COLUMNS,
    MODEL_AUTHENTICITY_KEY_NON_ORIGINAL_IMAGE,
    MODEL_AUTHENTICITY_KEY_POSSIBLE_MANIPULATION,
    MODEL_AUTHENTICITY_KEY_TEXT_INSTRUCTION_PRESENT,
    MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT,
    MODEL_CONTEXT_KEY_EXTRACTED_CLAIM,
    MODEL_CONTEXT_KEY_HISTORY,
    MODEL_CONTEXT_KEY_INPUT_ROW,
    MODEL_CONTEXT_KEY_PREFILTER,
    MODEL_DAMAGE_KEY_VISIBLE,
    MODEL_IMAGE_KEY_AUTHENTICITY,
    MODEL_IMAGE_KEY_CONFIDENCE,
    MODEL_IMAGE_KEY_DAMAGE,
    MODEL_IMAGE_KEY_IMAGE_ID,
    MODEL_IMAGE_KEY_OBJECT_CHECK,
    MODEL_IMAGE_KEY_PART_CHECK,
    MODEL_IMAGE_KEY_PREFILTER,
    MODEL_IMAGE_KEY_RISK_FLAGS,
    MODEL_IMAGE_KEY_USEFULNESS,
    MODEL_OBJECT_CHECK_KEY_EXPECTED_OBJECT,
    MODEL_OBJECT_CHECK_KEY_SHOWS_EXPECTED_OBJECT,
    MODEL_OBJECT_CHECK_KEY_WRONG_OBJECT,
    MODEL_PART_CHECK_KEY_CLAIMED_PART,
    MODEL_PART_CHECK_KEY_SHOWS_CLAIMED_PART,
    MODEL_PART_CHECK_KEY_WRONG_ANGLE,
    MODEL_PREFILTER_KEY_BLURRY,
    MODEL_PREFILTER_KEY_CROPPED,
    MODEL_PREFILTER_KEY_LOW_LIGHT_OR_GLARE,
    MODEL_PREFILTER_KEY_USABLE,
    MODEL_RESPONSE_KEY_CLAIM_LEVEL,
    MODEL_RESPONSE_KEY_PER_IMAGE,
    PREFILTER_KEY_PATH,
    PROMPT_ALLOWED_VALUES_TITLE,
    PROMPT_ANTI_INJECTION_RULE,
    PROMPT_CONTENT_KEY_SOURCE,
    PROMPT_CONTENT_KEY_TEXT,
    PROMPT_CONTENT_KEY_TYPE,
    PROMPT_CONTENT_TYPE_IMAGE,
    PROMPT_CONTENT_TYPE_TEXT,
    PROMPT_CONTEXT_KEY_PROMPT_VERSION,
    PROMPT_CONTEXT_KEY_IMAGE_IDS,
    PROMPT_CONTEXT_KEY_RESPONSE_SCHEMA_NAME,
    PROMPT_CONTEXT_RESPONSE_SCHEMA_NAME,
    PROMPT_CONTEXT_TITLE,
    PROMPT_ENGLISH_OUTPUT_INSTRUCTION,
    PROMPT_IMAGE_SOURCE_KEY_DATA,
    PROMPT_IMAGE_SOURCE_KEY_MEDIA_TYPE,
    PROMPT_IMAGE_SOURCE_KEY_TYPE,
    PROMPT_IMAGE_SOURCE_TYPE_BASE64,
    PROMPT_JPEG_SUFFIXES,
    PROMPT_JSON_INDENT,
    PROMPT_MEDIA_TYPE_JPEG,
    PROMPT_MEDIA_TYPE_OCTET_STREAM,
    PROMPT_MEDIA_TYPE_PNG,
    PROMPT_MEDIA_TYPE_WEBP,
    PROMPT_PNG_SUFFIX,
    PROMPT_MESSAGE_KEY_CONTENT,
    PROMPT_MESSAGE_KEY_MESSAGES,
    PROMPT_MESSAGE_KEY_ROLE,
    PROMPT_MESSAGE_KEY_SYSTEM,
    PROMPT_MESSAGE_ROLE_ASSISTANT,
    PROMPT_MESSAGE_ROLE_USER,
    PROMPT_OUTPUT_INSTRUCTION,
    PROMPT_SCHEMA_FORBIDDEN_LANGUAGE_KEY,
    PROMPT_SYSTEM_REVIEWER_ROLE,
    PROMPT_USER_TEXT_TEMPLATE,
    PROMPT_VERSION,
    PROMPT_WEBP_SUFFIX,
    SAMPLE_CSV,
)
from io_loaders import (
    load_history,
    load_sample_claims,
    match_evidence_requirement,
    resolve_image_paths,
)
from prefilter import prefilter_claim


JsonDict = Dict[str, Any]


def _enum_schema(allowed_values: Iterable[str]) -> JsonDict:
    """Build a string enum schema from constants.py values.

    Sorting makes the schema deterministic for reviewers and cache keys while
    keeping constants.py as the source of allowed categorical values.
    """
    return {"type": "string", "enum": sorted(allowed_values)}


def _string_array_schema(allowed_values: Iterable[str] | None = None) -> JsonDict:
    """Build an array-of-strings schema for structured model lists.

    Risk flags and supporting IDs are easier to validate as arrays in JSON and
    can be joined into the CSV representation in the later aggregation phase.
    """
    item_schema: JsonDict = {"type": "string"}
    if allowed_values is not None:
        item_schema["enum"] = sorted(allowed_values)
    return {"type": "array", "items": item_schema}


def _object_schema(properties: Mapping[str, JsonDict]) -> JsonDict:
    """Build a strict JSON-object schema with every declared property required.

    Phase 5 locks the response contract before the real client exists, so extra
    model keys are rejected by default instead of drifting into later phases.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _all_object_parts() -> List[str]:
    """Return the union of object-specific part enums for schema validation.

    The validator phase can enforce object-specific consistency; the VLM schema
    only needs to reject values outside the global problem contract.
    """
    return sorted(
        ALLOWED_CAR_OBJECT_PARTS
        | ALLOWED_LAPTOP_OBJECT_PARTS
        | ALLOWED_PACKAGE_OBJECT_PARTS
    )


def _per_image_schema() -> JsonDict:
    """Define the strict per-image breakdown requested by design §19.

    This structure separates quality, object, part, damage, and authenticity
    observations so aggregation can reason about each image selectively later.
    """
    return _object_schema(
        {
            MODEL_IMAGE_KEY_IMAGE_ID: {"type": "string"},
            MODEL_IMAGE_KEY_PREFILTER: _object_schema(
                {
                    MODEL_PREFILTER_KEY_USABLE: {"type": "boolean"},
                    MODEL_PREFILTER_KEY_BLURRY: {"type": "boolean"},
                    MODEL_PREFILTER_KEY_LOW_LIGHT_OR_GLARE: {"type": "boolean"},
                    MODEL_PREFILTER_KEY_CROPPED: {"type": "boolean"},
                }
            ),
            MODEL_IMAGE_KEY_OBJECT_CHECK: _object_schema(
                {
                    MODEL_OBJECT_CHECK_KEY_EXPECTED_OBJECT: _enum_schema(
                        ALLOWED_CLAIM_OBJECTS
                    ),
                    MODEL_OBJECT_CHECK_KEY_SHOWS_EXPECTED_OBJECT: {
                        "type": "boolean"
                    },
                    MODEL_OBJECT_CHECK_KEY_WRONG_OBJECT: {"type": "boolean"},
                }
            ),
            MODEL_IMAGE_KEY_PART_CHECK: _object_schema(
                {
                    MODEL_PART_CHECK_KEY_CLAIMED_PART: _enum_schema(
                        _all_object_parts()
                    ),
                    MODEL_PART_CHECK_KEY_SHOWS_CLAIMED_PART: {"type": "boolean"},
                    MODEL_PART_CHECK_KEY_WRONG_ANGLE: {"type": "boolean"},
                }
            ),
            MODEL_IMAGE_KEY_DAMAGE: _object_schema(
                {
                    MODEL_DAMAGE_KEY_VISIBLE: {"type": "boolean"},
                    COL_ISSUE_TYPE: _enum_schema(ALLOWED_ISSUE_TYPES),
                    COL_OBJECT_PART: _enum_schema(_all_object_parts()),
                    COL_SEVERITY: _enum_schema(ALLOWED_SEVERITY),
                }
            ),
            MODEL_IMAGE_KEY_AUTHENTICITY: _object_schema(
                {
                    MODEL_AUTHENTICITY_KEY_POSSIBLE_MANIPULATION: {
                        "type": "boolean"
                    },
                    MODEL_AUTHENTICITY_KEY_NON_ORIGINAL_IMAGE: {"type": "boolean"},
                    MODEL_AUTHENTICITY_KEY_TEXT_INSTRUCTION_PRESENT: {
                        "type": "boolean"
                    },
                }
            ),
            MODEL_IMAGE_KEY_USEFULNESS: _enum_schema(ALLOWED_MODEL_IMAGE_USEFULNESS),
            MODEL_IMAGE_KEY_CONFIDENCE: {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            MODEL_IMAGE_KEY_RISK_FLAGS: _string_array_schema(ALLOWED_RISK_FLAGS),
        }
    )


def _claim_level_schema() -> JsonDict:
    """Define the claim-level object mirroring the 14 output columns.

    JSON uses booleans and arrays where they are safer than CSV strings; Phase 6
    will serialize these fields into the exact output row format.
    """
    return _object_schema(
        {
            COL_USER_ID: {"type": "string"},
            COL_IMAGE_PATHS: {"type": "string"},
            COL_USER_CLAIM: {"type": "string"},
            COL_CLAIM_OBJECT: _enum_schema(ALLOWED_CLAIM_OBJECTS),
            COL_EVIDENCE_STANDARD_MET: {"type": "boolean"},
            COL_EVIDENCE_STANDARD_MET_REASON: {"type": "string"},
            COL_RISK_FLAGS: _string_array_schema(ALLOWED_RISK_FLAGS),
            COL_ISSUE_TYPE: _enum_schema(ALLOWED_ISSUE_TYPES),
            COL_OBJECT_PART: _enum_schema(_all_object_parts()),
            COL_CLAIM_STATUS: _enum_schema(ALLOWED_CLAIM_STATUS),
            COL_CLAIM_STATUS_JUSTIFICATION: {"type": "string"},
            COL_SUPPORTING_IMAGE_IDS: _string_array_schema(),
            COL_VALID_IMAGE: {"type": "boolean"},
            COL_SEVERITY: _enum_schema(ALLOWED_SEVERITY),
        }
    )


RESPONSE_JSON_SCHEMA = _object_schema(
    {
        MODEL_RESPONSE_KEY_PER_IMAGE: {
            "type": "array",
            "items": _per_image_schema(),
        },
        MODEL_RESPONSE_KEY_CLAIM_LEVEL: _claim_level_schema(),
    }
)


def _media_type(path: Path) -> str:
    """Map local image suffixes to Claude image-block media types.

    The dataset currently uses JPEGs, but keeping PNG/WebP support costs nothing
    and avoids hardcoding one extension into the prompt builder.
    """
    suffix = path.suffix.lower()
    if suffix in PROMPT_JPEG_SUFFIXES:
        return PROMPT_MEDIA_TYPE_JPEG
    if suffix == PROMPT_PNG_SUFFIX:
        return PROMPT_MEDIA_TYPE_PNG
    if suffix == PROMPT_WEBP_SUFFIX:
        return PROMPT_MEDIA_TYPE_WEBP
    return PROMPT_MEDIA_TYPE_OCTET_STREAM


def _image_path(image: Any) -> Path:
    """Extract a local path from supported image payload shapes.

    Existing phases pass `(image_id, path)` tuples, while prefilter-style
    dictionaries carry a path field. Accepting both avoids premature coupling to
    the final pipeline representation.
    """
    if isinstance(image, Mapping):
        return Path(str(image[PREFILTER_KEY_PATH]))
    if isinstance(image, tuple) and len(image) >= 2:
        return Path(image[1])
    if isinstance(image, Path):
        return image
    return Path(str(image))


def _image_id(image: Any) -> str:
    """Extract a stable image ID for prompt context.

    The model receives binary image blocks, so this ID is the bridge it uses to
    cite supporting or contradictory images in the JSON response.
    """
    if isinstance(image, Mapping):
        return str(image.get(MODEL_IMAGE_KEY_IMAGE_ID, _image_path(image).stem))
    if isinstance(image, tuple) and image:
        return str(image[0])
    return _image_path(image).stem


def _image_block(image: Any) -> JsonDict:
    """Build one base64 image block for the Claude user message.

    This only prepares the payload; it does not call the API. Encoding here lets
    Phase 5 verify that every sample row can produce complete image blocks.
    """
    path = _image_path(image)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        PROMPT_CONTENT_KEY_TYPE: PROMPT_CONTENT_TYPE_IMAGE,
        PROMPT_CONTENT_KEY_SOURCE: {
            PROMPT_IMAGE_SOURCE_KEY_TYPE: PROMPT_IMAGE_SOURCE_TYPE_BASE64,
            PROMPT_IMAGE_SOURCE_KEY_MEDIA_TYPE: _media_type(path),
            PROMPT_IMAGE_SOURCE_KEY_DATA: encoded,
        },
    }


def _to_json_safe(value: Any) -> Any:
    """Convert context values into deterministic JSON-serializable data.

    Prefilter output contains tuples and Path instances, which are useful in
    Python but need stable string/list forms before entering a prompt block.
    """
    if isinstance(value, Mapping):
        return {
            str(key): _to_json_safe(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_to_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Path):
        return str(value)
    return value


def _input_only_row(row: Mapping[str, Any]) -> JsonDict:
    """Filter a row down to model inputs so sample labels never leak.

    The sample CSV contains expected outputs, but prompt construction must
    behave exactly like the test-set path and expose only input columns.
    """
    return {column: row.get(column, "") for column in INPUT_COLUMNS}


def _allowed_values_text() -> str:
    """Render allowed values into the stable system prompt prefix.

    The prompt gives the VLM the same categorical contract that validators will
    enforce later, reducing avoidable out-of-vocabulary responses.
    """
    allowed_values = {
        COL_CLAIM_OBJECT: sorted(ALLOWED_CLAIM_OBJECTS),
        COL_CLAIM_STATUS: sorted(ALLOWED_CLAIM_STATUS),
        COL_ISSUE_TYPE: sorted(ALLOWED_ISSUE_TYPES),
        "car_object_part": sorted(ALLOWED_CAR_OBJECT_PARTS),
        "laptop_object_part": sorted(ALLOWED_LAPTOP_OBJECT_PARTS),
        "package_object_part": sorted(ALLOWED_PACKAGE_OBJECT_PARTS),
        COL_RISK_FLAGS: sorted(ALLOWED_RISK_FLAGS),
        COL_SEVERITY: sorted(ALLOWED_SEVERITY),
    }
    return json.dumps(allowed_values, indent=PROMPT_JSON_INDENT, sort_keys=True)


def _system_prompt() -> str:
    """Build the stable system prompt prefix used for every claim.

    It includes the English-output instruction and anti-injection rule required
    by the design, plus the prompt version for cache invalidation.
    """
    return "\n\n".join(
        (
            f"{PROMPT_SYSTEM_REVIEWER_ROLE} Prompt version: {PROMPT_VERSION}.",
            PROMPT_ENGLISH_OUTPUT_INSTRUCTION,
            PROMPT_ANTI_INJECTION_RULE,
            PROMPT_ALLOWED_VALUES_TITLE,
            _allowed_values_text(),
            PROMPT_OUTPUT_INSTRUCTION,
        )
    )


def _context_payload(claim_context: Mapping[str, Any], images: List[Any]) -> JsonDict:
    """Build the text payload that accompanies the image blocks.

    The payload contains raw claim text, extracted claim, evidence requirement,
    history, prefilter measurements, and image IDs. User-provided content stays
    inside JSON data so system instructions remain clearly separated.
    """
    input_row = _input_only_row(
        claim_context.get(MODEL_CONTEXT_KEY_INPUT_ROW, claim_context)
    )
    return {
        PROMPT_CONTEXT_KEY_PROMPT_VERSION: PROMPT_VERSION,
        MODEL_CONTEXT_KEY_INPUT_ROW: input_row,
        MODEL_CONTEXT_KEY_EXTRACTED_CLAIM: claim_context.get(
            MODEL_CONTEXT_KEY_EXTRACTED_CLAIM,
            {},
        ),
        MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT: claim_context.get(
            MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT,
            "",
        ),
        MODEL_CONTEXT_KEY_HISTORY: claim_context.get(MODEL_CONTEXT_KEY_HISTORY, {}),
        MODEL_CONTEXT_KEY_PREFILTER: claim_context.get(
            MODEL_CONTEXT_KEY_PREFILTER,
            {},
        ),
        PROMPT_CONTEXT_KEY_IMAGE_IDS: [_image_id(image) for image in images],
        PROMPT_CONTEXT_KEY_RESPONSE_SCHEMA_NAME: PROMPT_CONTEXT_RESPONSE_SCHEMA_NAME,
    }


def build_messages(claim_context: Dict[str, Any], images: List[Any]) -> Dict[str, Any]:
    """Build Claude system and user message blocks for one claim.

    Args:
        claim_context: Input row plus extracted claim, evidence requirement,
            history, and prefilter context.
        images: Resolved local image references to include as image blocks.

    Returns:
        A dictionary with top-level `system` text and one user message. It does
        not include an assistant prefill and does not call the model.
    """
    payload = json.dumps(
        _to_json_safe(_context_payload(claim_context, images)),
        indent=PROMPT_JSON_INDENT,
        sort_keys=True,
    )
    user_text = PROMPT_USER_TEXT_TEMPLATE.format(
        title=PROMPT_CONTEXT_TITLE,
        payload=payload,
    )
    user_content = [
        {
            PROMPT_CONTENT_KEY_TYPE: PROMPT_CONTENT_TYPE_TEXT,
            PROMPT_CONTENT_KEY_TEXT: user_text,
        }
    ]
    user_content.extend(_image_block(image) for image in images)
    return {
        PROMPT_MESSAGE_KEY_SYSTEM: _system_prompt(),
        PROMPT_MESSAGE_KEY_MESSAGES: [
            {
                PROMPT_MESSAGE_KEY_ROLE: PROMPT_MESSAGE_ROLE_USER,
                PROMPT_MESSAGE_KEY_CONTENT: user_content,
            }
        ],
    }


def _schema_contains_key(schema: Any, forbidden_key: str) -> bool:
    """Search a schema recursively for a forbidden property name.

    Phase 5 explicitly forbids a language field, so this helper keeps the smoke
    test focused on the structural contract rather than string matching docs.
    """
    if isinstance(schema, Mapping):
        return any(
            key == forbidden_key or _schema_contains_key(value, forbidden_key)
            for key, value in schema.items()
        )
    if isinstance(schema, list):
        return any(_schema_contains_key(item, forbidden_key) for item in schema)
    return False


def _sample_context(row: Mapping[str, str], history_by_user: Mapping[str, Any]) -> JsonDict:
    """Build representative Phase 5 context for one labeled sample row.

    The context uses only input fields from the sample row, then joins the
    deterministic Phase 1-3 context that prompt construction must include.
    """
    input_row = _input_only_row(row)
    extracted_claim = extract_claim(
        str(input_row[COL_USER_CLAIM]),
        str(input_row[COL_CLAIM_OBJECT]),
    )
    images = resolve_image_paths(str(input_row[COL_IMAGE_PATHS]))
    return {
        MODEL_CONTEXT_KEY_INPUT_ROW: input_row,
        MODEL_CONTEXT_KEY_EXTRACTED_CLAIM: extracted_claim,
        MODEL_CONTEXT_KEY_EVIDENCE_REQUIREMENT: match_evidence_requirement(
            str(input_row[COL_CLAIM_OBJECT]),
            extracted_claim[CLAIM_EXTRACTION_KEY_CLAIMED_ISSUE_TYPE],
        ),
        MODEL_CONTEXT_KEY_HISTORY: history_by_user.get(input_row[COL_USER_ID], {}),
        MODEL_CONTEXT_KEY_PREFILTER: prefilter_claim(images),
    }


def run_smoke_test() -> None:
    """Exercise prompt and schema construction across every sample row.

    Raises:
        AssertionError: If messages omit required sections, include assistant
            prefill, fail to build image blocks, omit PROMPT_VERSION, or if the
            response schema lacks required fields or contains a language key.
    """
    history_by_user = load_history()
    claim_level_properties = RESPONSE_JSON_SCHEMA["properties"][
        MODEL_RESPONSE_KEY_CLAIM_LEVEL
    ]["properties"]

    assert set(claim_level_properties) == set(
        (
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
    )
    assert MODEL_RESPONSE_KEY_PER_IMAGE in RESPONSE_JSON_SCHEMA["properties"]
    assert not _schema_contains_key(
        RESPONSE_JSON_SCHEMA,
        PROMPT_SCHEMA_FORBIDDEN_LANGUAGE_KEY,
    )

    for row in load_sample_claims(SAMPLE_CSV):
        images = resolve_image_paths(row[COL_IMAGE_PATHS])
        messages = build_messages(_sample_context(row, history_by_user), images)

        assert set(messages) == {
            PROMPT_MESSAGE_KEY_SYSTEM,
            PROMPT_MESSAGE_KEY_MESSAGES,
        }
        assert PROMPT_ENGLISH_OUTPUT_INSTRUCTION in messages[PROMPT_MESSAGE_KEY_SYSTEM]
        assert PROMPT_VERSION in messages[PROMPT_MESSAGE_KEY_SYSTEM]
        assert len(messages[PROMPT_MESSAGE_KEY_MESSAGES]) == 1
        assert all(
            message[PROMPT_MESSAGE_KEY_ROLE] != PROMPT_MESSAGE_ROLE_ASSISTANT
            for message in messages[PROMPT_MESSAGE_KEY_MESSAGES]
        )

        user_message = messages[PROMPT_MESSAGE_KEY_MESSAGES][0]
        assert user_message[PROMPT_MESSAGE_KEY_ROLE] == PROMPT_MESSAGE_ROLE_USER
        content_blocks = user_message[PROMPT_MESSAGE_KEY_CONTENT]
        assert content_blocks[0][PROMPT_CONTENT_KEY_TYPE] == PROMPT_CONTENT_TYPE_TEXT
        image_blocks = [
            block
            for block in content_blocks
            if block[PROMPT_CONTENT_KEY_TYPE] == PROMPT_CONTENT_TYPE_IMAGE
        ]
        assert len(image_blocks) == len(images)


if __name__ == "__main__":
    run_smoke_test()
