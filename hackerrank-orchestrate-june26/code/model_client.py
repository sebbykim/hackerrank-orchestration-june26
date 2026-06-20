"""
model_client.py - Model client interface boundary.

WHAT:  This module defines the shared model-client interface for claim-review
       model implementations. It also implements the real Claude vision client
       behind that same boundary.
WHY:   A single interface lets the mock and real model clients be swapped
       without changing pipeline, aggregation, or evaluation logic.
STEPS: Implements STEPS.md Phase 4 item 1 and Phase 8 item 1.
IN:    Claim context dictionaries and resolved usable image payloads.
OUT:   Per-image plus claim-level response dictionaries.
"""

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping

import anthropic

from constants import (
    ANTHROPIC_API_KEY_ENV_VAR,
    ANTHROPIC_REQUEST_TIMEOUT_SECONDS,
    CLAUDE_CACHE_CONTROL_TYPE,
    CLAUDE_CACHE_CONTROL_KEY,
    CLAUDE_CONTENT_TYPE_TEXT,
    CLAUDE_CONTENT_TYPE_TOOL_USE,
    CLAUDE_DISABLE_PARALLEL_TOOL_USE,
    CLAUDE_ERROR_MISSING_API_KEY,
    CLAUDE_ERROR_NO_STRUCTURED_OUTPUT,
    CLAUDE_ERROR_RETRIES_EXHAUSTED_TEMPLATE,
    CLAUDE_JSON_OBJECT_END,
    CLAUDE_JSON_OBJECT_START,
    CLAUDE_MAX_RETRIES,
    CLAUDE_MAX_TOKENS,
    CLAUDE_REQUEST_KEY_MAX_TOKENS,
    CLAUDE_REQUEST_KEY_MESSAGES,
    CLAUDE_REQUEST_KEY_MODEL,
    CLAUDE_REQUEST_KEY_SYSTEM,
    CLAUDE_REQUEST_KEY_TEMPERATURE,
    CLAUDE_REQUEST_KEY_THINKING,
    CLAUDE_REQUEST_KEY_TOOL_CHOICE,
    CLAUDE_REQUEST_KEY_TOOLS,
    CLAUDE_RESPONSE_CONTENT_ATTR,
    CLAUDE_RESPONSE_TEXT_ATTR,
    CLAUDE_RETRY_BACKOFF_SECONDS,
    CLAUDE_SMOKE_RESPONSE_KEY_OK,
    CLAUDE_TEMPERATURE,
    CLAUDE_THINKING_KEY_BUDGET_TOKENS,
    CLAUDE_THINKING_BUDGET_TOKENS,
    CLAUDE_THINKING_TYPE_ENABLED,
    CLAUDE_TOOL_CHOICE_KEY_DISABLE_PARALLEL,
    CLAUDE_TOOL_CHOICE_TYPE,
    CLAUDE_TOOL_DESCRIPTION,
    CLAUDE_TOOL_KEY_DESCRIPTION,
    CLAUDE_TOOL_KEY_INPUT_SCHEMA,
    CLAUDE_TOOL_KEY_NAME,
    CLAUDE_TOOL_KEY_TYPE,
    CLAUDE_TOOL_NAME,
    CLAUDE_TOOL_RESPONSE_INPUT_ATTR,
    CLAUDE_TOOL_TYPE,
    DEFAULT_CLAUDE_MODEL_ID,
    MODEL_ID_ENV_VAR,
    PROMPT_CONTENT_KEY_TEXT,
    PROMPT_CONTENT_KEY_TYPE,
    PROMPT_CONTENT_TYPE_TEXT,
    PROMPT_MESSAGE_KEY_MESSAGES,
    PROMPT_MESSAGE_KEY_SYSTEM,
)
from prompt import RESPONSE_JSON_SCHEMA, build_messages


class ModelClient(ABC):
    """Define the one model boundary used by mock and real VLM clients.

    The interface stays deliberately small because the pipeline should not know
    whether responses come from a deterministic mock or a paid API call. Phase 4
    only establishes the contract; concrete clients decide how to interpret the
    context and image payloads.
    """

    @abstractmethod
    def predict(
        self,
        claim_context: Dict[str, Any],
        images: List[Any],
    ) -> Dict[str, Any]:
        """Return per-image and claim-level JSON-like model output.

        Args:
            claim_context: Structured row, extraction, history, prefilter, and
                requirement context assembled by later pipeline phases.
            images: Resolved image references or metadata records in input order.

        Returns:
            A dictionary with per-image and claim-level response sections.
        """


class ModelClientError(RuntimeError):
    """Represent a model-client failure that the pipeline can degrade from.

    The pipeline catches broad exceptions to emit fallback rows, but a typed
    model error makes real-client failures explicit for callers and tests.
    """


class ClaudeModelClient(ModelClient):
    """Call Claude through the shared ModelClient boundary.

    The client uses the pinned Anthropic SDK, the Phase 5 prompt builder, a
    forced structured tool call backed by RESPONSE_JSON_SCHEMA, prompt caching
    on the stable system prefix, and bounded retries. It raises ModelClientError
    on failure so the Phase 7 pipeline can emit a valid fallback row.
    """

    def __init__(
        self,
        model_id: str | None = None,
        api_key: str | None = None,
        max_retries: int = CLAUDE_MAX_RETRIES,
        timeout_seconds: float = ANTHROPIC_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the Claude client from explicit args or environment.

        Args:
            model_id: Optional Anthropic model ID. Defaults to ANTHROPIC_MODEL_ID
                or DEFAULT_CLAUDE_MODEL_ID.
            api_key: Optional API key. Defaults to ANTHROPIC_API_KEY.
            max_retries: Number of retry attempts after the initial request.
            timeout_seconds: SDK request timeout.

        Raises:
            ModelClientError: If no API key is available.
        """
        resolved_api_key = api_key or os.environ.get(ANTHROPIC_API_KEY_ENV_VAR)
        if not resolved_api_key:
            raise ModelClientError(CLAUDE_ERROR_MISSING_API_KEY)
        self.model_id = model_id or os.environ.get(MODEL_ID_ENV_VAR, DEFAULT_CLAUDE_MODEL_ID)
        self.max_retries = max_retries
        self._client = anthropic.Anthropic(
            api_key=resolved_api_key,
            timeout=timeout_seconds,
        )

    def predict(
        self,
        claim_context: Dict[str, Any],
        images: List[Any],
    ) -> Dict[str, Any]:
        """Return structured Claude output for one claim.

        Args:
            claim_context: Structured context built by pipeline.py.
            images: Resolved local image references for the claim.

        Returns:
            A dictionary matching RESPONSE_JSON_SCHEMA.

        Raises:
            ModelClientError: If Claude fails repeatedly or returns no
                structured response.
        """
        request_payload = _claude_request_payload(claim_context, images, self.model_id)
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt_index in range(attempts):
            try:
                response = self._client.messages.create(**request_payload)
                return _extract_structured_response(response)
            except Exception as error:
                last_error = error
                if attempt_index + 1 < attempts:
                    time.sleep(CLAUDE_RETRY_BACKOFF_SECONDS * (attempt_index + 1))
        raise ModelClientError(
            CLAUDE_ERROR_RETRIES_EXHAUSTED_TEMPLATE.format(
                attempts=attempts,
                error=last_error,
            )
        )


def _claude_system_blocks(system_text: str) -> List[Dict[str, Any]]:
    """Build cached system text blocks for Claude prompt caching.

    Prompt caching applies to content blocks, so the stable Phase 5 system
    prefix is wrapped as a text block with an ephemeral cache-control breakpoint.
    """
    return [
        {
            PROMPT_CONTENT_KEY_TYPE: PROMPT_CONTENT_TYPE_TEXT,
            PROMPT_CONTENT_KEY_TEXT: system_text,
            CLAUDE_CACHE_CONTROL_KEY: {CLAUDE_TOOL_KEY_TYPE: CLAUDE_CACHE_CONTROL_TYPE},
        }
    ]


def _claude_tool_definition() -> Dict[str, Any]:
    """Build the forced structured-output tool definition.

    The installed SDK version does not expose `output_config`, so a single
    forced client tool with RESPONSE_JSON_SCHEMA provides the same strict JSON
    shape without assistant prefill.
    """
    return {
        CLAUDE_TOOL_KEY_NAME: CLAUDE_TOOL_NAME,
        CLAUDE_TOOL_KEY_DESCRIPTION: CLAUDE_TOOL_DESCRIPTION,
        CLAUDE_TOOL_KEY_INPUT_SCHEMA: RESPONSE_JSON_SCHEMA,
        CLAUDE_TOOL_KEY_TYPE: CLAUDE_TOOL_TYPE,
        CLAUDE_CACHE_CONTROL_KEY: {CLAUDE_TOOL_KEY_TYPE: CLAUDE_CACHE_CONTROL_TYPE},
    }


def _claude_request_payload(
    claim_context: Dict[str, Any],
    images: List[Any],
    model_id: str,
) -> Dict[str, Any]:
    """Build the SDK request payload without making a network call.

    Args:
        claim_context: Structured claim context from the pipeline.
        images: Resolved image references.
        model_id: Anthropic model ID.

    Returns:
        Keyword arguments suitable for `client.messages.create`.
    """
    messages_payload = build_messages(claim_context, images)
    return {
        CLAUDE_REQUEST_KEY_MODEL: model_id,
        CLAUDE_REQUEST_KEY_MAX_TOKENS: CLAUDE_MAX_TOKENS,
        CLAUDE_REQUEST_KEY_TEMPERATURE: CLAUDE_TEMPERATURE,
        CLAUDE_REQUEST_KEY_THINKING: {
            CLAUDE_TOOL_KEY_TYPE: CLAUDE_THINKING_TYPE_ENABLED,
            CLAUDE_THINKING_KEY_BUDGET_TOKENS: CLAUDE_THINKING_BUDGET_TOKENS,
        },
        CLAUDE_REQUEST_KEY_SYSTEM: _claude_system_blocks(
            messages_payload[PROMPT_MESSAGE_KEY_SYSTEM]
        ),
        CLAUDE_REQUEST_KEY_MESSAGES: messages_payload[PROMPT_MESSAGE_KEY_MESSAGES],
        CLAUDE_REQUEST_KEY_TOOLS: [_claude_tool_definition()],
        CLAUDE_REQUEST_KEY_TOOL_CHOICE: {
            CLAUDE_TOOL_KEY_TYPE: CLAUDE_TOOL_CHOICE_TYPE,
            CLAUDE_TOOL_KEY_NAME: CLAUDE_TOOL_NAME,
            CLAUDE_TOOL_CHOICE_KEY_DISABLE_PARALLEL: CLAUDE_DISABLE_PARALLEL_TOOL_USE,
        },
    }


def _content_block_type(block: Any) -> str:
    """Return a content block type from SDK objects or plain dicts.

    Tests and SDK responses may use different representations, so parsing stays
    representation-agnostic.
    """
    if isinstance(block, Mapping):
        return str(block.get(CLAUDE_TOOL_KEY_TYPE, ""))
    return str(getattr(block, CLAUDE_TOOL_KEY_TYPE, ""))


def _extract_structured_response(response: Any) -> Dict[str, Any]:
    """Extract structured JSON from a Claude response.

    The preferred path is a forced `tool_use` block. A text JSON fallback is
    accepted for defensive compatibility with test doubles or SDK changes.
    """
    for block in getattr(response, CLAUDE_RESPONSE_CONTENT_ATTR, []):
        if _content_block_type(block) == CLAUDE_CONTENT_TYPE_TOOL_USE:
            tool_input = (
                block.get(CLAUDE_TOOL_RESPONSE_INPUT_ATTR)
                if isinstance(block, Mapping)
                else getattr(block, CLAUDE_TOOL_RESPONSE_INPUT_ATTR)
            )
            if isinstance(tool_input, dict):
                return tool_input

    for block in getattr(response, CLAUDE_RESPONSE_CONTENT_ATTR, []):
        if _content_block_type(block) == CLAUDE_CONTENT_TYPE_TEXT:
            text = (
                block.get(CLAUDE_RESPONSE_TEXT_ATTR)
                if isinstance(block, Mapping)
                else getattr(block, CLAUDE_RESPONSE_TEXT_ATTR)
            )
            parsed = _parse_json_object(str(text))
            if isinstance(parsed, dict):
                return parsed
    raise ModelClientError(CLAUDE_ERROR_NO_STRUCTURED_OUTPUT)


def _parse_json_object(text: str) -> Dict[str, Any] | None:
    """Parse the first JSON object from a text block when present.

    Tool use is the normal structured path. This fallback only exists so tests
    and transient model behavior can still be interpreted without assistant
    prefill.
    """
    start = text.find(CLAUDE_JSON_OBJECT_START)
    end = text.rfind(CLAUDE_JSON_OBJECT_END)
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def run_smoke_test() -> None:
    """Exercise Phase 8 request construction and response parsing without API calls.

    Raises:
        AssertionError: If the request omits tool schema, thinking, prompt cache
            blocks, or if structured response extraction fails.
    """
    payload = _claude_request_payload({}, [], DEFAULT_CLAUDE_MODEL_ID)
    assert payload[CLAUDE_REQUEST_KEY_MODEL] == DEFAULT_CLAUDE_MODEL_ID
    assert payload[CLAUDE_REQUEST_KEY_TOOLS][0][CLAUDE_TOOL_KEY_INPUT_SCHEMA] == RESPONSE_JSON_SCHEMA
    assert payload[CLAUDE_REQUEST_KEY_TOOL_CHOICE][CLAUDE_TOOL_KEY_NAME] == CLAUDE_TOOL_NAME
    assert (
        payload[CLAUDE_REQUEST_KEY_THINKING][CLAUDE_THINKING_KEY_BUDGET_TOKENS]
        == CLAUDE_THINKING_BUDGET_TOKENS
    )
    assert (
        payload[CLAUDE_REQUEST_KEY_SYSTEM][0][CLAUDE_CACHE_CONTROL_KEY][CLAUDE_TOOL_KEY_TYPE]
        == CLAUDE_CACHE_CONTROL_TYPE
    )

    class FakeResponse:
        """Minimal SDK-like response for parser smoke coverage."""

        content = [
            {
                CLAUDE_TOOL_KEY_TYPE: CLAUDE_CONTENT_TYPE_TOOL_USE,
                CLAUDE_TOOL_RESPONSE_INPUT_ATTR: {CLAUDE_SMOKE_RESPONSE_KEY_OK: True},
            }
        ]

    assert _extract_structured_response(FakeResponse()) == {
        CLAUDE_SMOKE_RESPONSE_KEY_OK: True
    }


if __name__ == "__main__":
    run_smoke_test()
