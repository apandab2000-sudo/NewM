from .base import LLMBase, LLMResult, TokenUsage
from openai import AsyncOpenAI
from typing import List, Optional, Dict
from app.appConfig import settings
from app.logger import get_logger
from pydantic import BaseModel, Field


logger = get_logger(__name__)


class OpenAILLMBASE(LLMBase):
    """OpenAI LLM provider."""
    _client: Optional[AsyncOpenAI] = None

    @classmethod
    def get_client(cls) -> AsyncOpenAI:
        """Get or create async OpenAI client."""
        if cls._client is None:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            cls._client = AsyncOpenAI(api_key=api_key, timeout=30, max_retries=0)
            logger.debug("OpenAI async client created")
        return cls._client
    

class OpenAILLM(OpenAILLMBASE):
    async def _generate(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[BaseModel] = None,
        tools: Optional[list] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """Generate response using OpenAI API."""
        try:
            client: AsyncOpenAI = self.get_client()
            
            # Build request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                request_params["max_completion_tokens"] = max_tokens
                
            if json_schema:
                request_params["response_format"] = json_schema
                logger.debug("JSON mode enabled for OpenAI")
                
            if tools:
                request_params["tools"] = tools
                logger.debug(f"Added {len(tools)} tools to OpenAI request")

            call_usage = TokenUsage()

            response = await client.chat.completions.parse(**request_params)
            
            if json_schema:
                output = response.choices[0].message.parsed
            else:
                output = response.choices[0].message.content
            
            # Track token usage
            if response.usage:
                call_usage.update(
                    input_tokens=response.usage.prompt_tokens or 0,
                    output_tokens=response.usage.completion_tokens or 0,
                    cached_tokens=(
                        response.usage.prompt_tokens_details.cached_tokens or 0
                        if response.usage.prompt_tokens_details else 0
                    )
                )
           
            result = LLMResult(
                parsed_json=output,
                raw_response=response,
                token_usage=call_usage,
                model=self.model,
                provider=self.provider
            )
            
            logger.debug(f"OpenAI response generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {str(e)}", exc_info=True)
            raise


class OpenAILLMN_New(OpenAILLMBASE):
    async def _generate(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[BaseModel] = None,
        tools: Optional[list] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResult:
        """Generate response using OpenAI API."""
        try:
            client = self.get_client()
            
            # Build request parameters
            request_params = {
                "model": self.model,
                "input": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                request_params["max_output_tokens"] = max_tokens
                
            if json_schema:
                request_params["text_format"] = json_schema
                logger.debug("JSON mode enabled for OpenAI")
                
            if tools:
                request_params["tools"] = tools
                logger.debug(f"Added {len(tools)} tools to OpenAI request")

            
            call_usage = TokenUsage()
            
            response = await client.responses.parse(**request_params)

            # Track token usage
            if response.usage:
                call_usage.update(
                    input_tokens=response.usage.input_tokens or 0,
                    output_tokens=response.usage.output_tokens or 0,
                    cached_tokens=(
                        response.usage.input_tokens_details.cached_tokens or 0
                        if response.usage.input_tokens_details else 0
                    )
                )

            # output_text = response.output_parsed if hasattr(response, 'output_parsed') else str(response)
            if json_schema and hasattr(response, 'output_parsed') and response.output_parsed is not None:
                parsed_json = response.output_parsed          # Pydantic model instance
            else:
                # For plain text responses, extract from output items
                output_text = next(
                    (item.text for item in response.output 
                    if hasattr(item, 'text')),
                    ""
                )
                parsed_json = None
           
           
            result = LLMResult(
                parsed_json=parsed_json,
                raw_response=response,
                token_usage=call_usage,
                model=self.model,
                provider=self.provider
            )
            
            logger.debug(f"OpenAI response generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {str(e)}", exc_info=True)
            raise