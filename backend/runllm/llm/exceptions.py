"""Custom exceptions for the LLM layer."""

from __future__ import annotations


class LLMError(Exception):
    """Base error for LLM operations."""


class LLMToolError(LLMError):
    """A Claude tool call failed."""


class LLMTokenBudgetError(LLMError):
    """The system prompt exceeded the configured token budget."""
