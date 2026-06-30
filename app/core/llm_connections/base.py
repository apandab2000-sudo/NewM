from abc import ABC, abstractmethod
from app.logger import get_logger
import os
from typing import List, Optional, Dict
from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_exponential
import json
import asyncio
from .models import TokenUsage, LLMResult
from pydantic import BaseModel, ValidationError


logger = get_logger(__name__)


class LLMBase(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, model: str, provider: str, timeout: int = 30, max_retries: int = 2):
        """Initialize LLM base.
        
        Args:
            model: Model name
            provider: Provider name ('openai', 'anthropic', 'gemini')
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.model = model
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.token_usage = TokenUsage()
        self._async_client = None
        logger.info(f"Initialized {provider} LLM with model: {model}")

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((
            json.JSONDecodeError, 
            asyncio.TimeoutError,
            ValidationError)),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _execute_with_retry(self, coro_factory, *args, **kwargs):
        """Execute a coroutine factory with retry logic.
        
        Args:
            coro_factory: A callable that returns a coroutine (not the coroutine itself)
        """
        try:
            async with asyncio.timeout(self.timeout):   # fold timeout in here
                return await coro_factory(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Attempt failed ({type(e).__name__}): {e}")
            raise

    # async def _execute_with_retry(self, coro):
    #     """Execute coroutine with retry logic."""
    #     try:
    #         return await coro(*args, **kwargs)
    #     except Exception as e:
    #         logger.error(f"Error during execution: {str(e)}", exc_info=True)
    #         raise
    
    # async def _execute_with_timeout(self, coro):
    #     """Execute coroutine with timeout."""
    #     try:
    #         async with asyncio.timeout(self.timeout):
    #             return await coro
    #     except asyncio.TimeoutError:
    #         logger.error(f"Request timeout after {self.timeout} seconds")
    #         raise
        
    async def generate(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[dict] = None,
        tools: Optional[list] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResult:
        """Generate LLM response.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            json_schema: Optional JSON schema for response validation
            tools: Optional list of tools/functions
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResult with content and token usage
        """
        logger.debug(
            f"Generating response from {self.provider}/{self.model} "
            f"with {len(messages)} messages, json_schema={json_schema}"
        )
        
        try:
            # response = await self._execute_with_retry(
            #     self._execute_with_timeout(
            #         self._generate(
            #             messages=messages,
            #             json_schema=json_schema,
            #             tools=tools,
            #             temperature=temperature,
            #             max_tokens=max_tokens,
            #         )
            #     )
            # )

            response = await self._execute_with_retry(
                lambda: self._generate(
                    messages=messages,
                    json_schema=json_schema,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

            logger.info(
                f"Successfully generated response from {self.provider} "
                f"- Tokens used: {self.token_usage.model_dump()}"
            )
            return response
        except Exception as e:
            logger.error(f"Failed to generate response: {str(e)}", exc_info=True)
            raise
    
    @abstractmethod
    async def _generate(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[dict] = None,
        tools: Optional[list] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """Provider-specific generation implementation."""
        ...

    @staticmethod
    def get_json_from_str(text: str) -> dict:
        """Extract and parse JSON from text."""
        try:
            # Remove markdown code blocks and json markers
            json_response = text.strip()
            if json_response.startswith("```"):
                json_response = json_response.split("```")[1]
            if json_response.lower().startswith("json"):
                json_response = json_response[4:]
            json_response = json_response.strip()
            parsed = json.loads(json_response)
            logger.debug("Successfully parsed JSON from response")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {str(e)}")
            raise

