
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TokenUsage(BaseModel):
    """Track token usage across LLM calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def update(self, input_tokens: int = 0, output_tokens: int = 0, cached_tokens: int = 0):
        """Update token counts."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens

    def reset(self):
        """Reset token counts."""
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0

    def __add__(self, other):
        if not isinstance(other, TokenUsage):
            return NotImplemented
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


class LLMResult(BaseModel):
    """Result from LLM generation."""
    parsed_json: Optional[Any] = None
    raw_response: Optional[Any] = None
    token_usage: Optional[TokenUsage] = None
    model: Optional[str] = None
    provider: Optional[str] = None
