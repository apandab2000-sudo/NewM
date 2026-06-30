# from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI, omit
import os
from dotenv import load_dotenv
from app.logger import get_logger
import time
import json
from pydantic import BaseModel
from typing import List, Dict, Optional

load_dotenv()


# class TokenUsage(BaseModel):
#     input_tokens: int = 0
#     output_tokens: int = 0
#     cached_tokens: int = 0


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
            cached_tokens=self.cached_tokens + other.cached_tokens
        )


logger = get_logger()


async def get_llm(base: str = "gpt"):
    if base=="gpt":
        return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    else:
        return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # TO BE CHNAGED FOR OTHER MODELS


def get_json_from_str(text: str):
    json_response = text.strip().replace("`","").replace("json","")
    return json.loads(json_response)


async def get_llm_response(client: AsyncOpenAI, model: str="gpt-4.1", messages: List[Optional[Dict[str, str]]] = []):
    start_time = time.perf_counter()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"}
    )

    print("#############################")
    print(response.choices[0].message.content)
    print("##############################")

    token_usage = TokenUsage()
    token_usage.input_tokens += response.usage.prompt_tokens
    token_usage.output_tokens += response.usage.completion_tokens
    token_usage.cached_tokens += response.usage.prompt_tokens_details.cached_tokens if response.usage.prompt_tokens_details.cached_tokens else 0 


    try:
        json_response = get_json_from_str(str(response.choices[0].message.content))
        return json_response, token_usage
    except json.JSONDecodeError as e:
        logger.error(f"LLM response resulted in JSON Decode error - {repr(e)}") 
        messages = [
            {"role": "system", "content": "Your task is to take user request and convert and return the response in proper JSON format. Only JSON output and nothing else"},
            {"role": "user", "content":messages[-1]["content"]},
            {"role": "assistant", "content":f"JSON decode error {repr(e)}"},
            {"role": "user", "content": str(response.choices[0].message.content)}
        ]
        print(messages)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"}
        )

        token_usage.input_tokens += response.usage.completion_tokens
        token_usage.output_tokens += response.usage.prompt_tokens
        token_usage.cached_tokens += response.usage.prompt_tokens_details.cached_tokens if response.usage.prompt_tokens_details.cached_tokens else 0 
        
        try:
            json_response = get_json_from_str(str(response.choices[0].message.content))
            return json_response, token_usage
        except Exception as e:
            return None, token_usage
    except Exception as e:
        logger.error(f"LLM response not generated properly - {repr(e)}") 
        return None, token_usage
    finally: 
        process_time = time.perf_counter()-start_time               
        logger.info(f"Model Used: {model} | LLM response time: {process_time:.2f} | token usage: {token_usage.model_dump()}")
        



async def get_llm_response_with_tool(client: AsyncOpenAI, model: str="gpt-4.1", messages: List[Optional[Dict[str, str]]] = [], tools: list = []):
    
    start_time = time.perf_counter()
    token_usage = TokenUsage()

    try:
        response = await client.responses.create(
            model=model,
            tools=tools if tools else omit,
            input=messages,
        )

        print("#############################")
        print(response.output)
        print("##############################")

        # ---- Token usage tracking ----
        if response.usage:
            token_usage.input_tokens += response.usage.input_tokens or 0
            token_usage.output_tokens += response.usage.output_tokens or 0
            token_usage.cached_tokens += (
                response.usage.input_tokens_details.cached_tokens or 0
                if response.usage.input_tokens_details else 0
            )

        return response, token_usage

    except Exception as e:
        print(repr(e))
        logger.error(f"LLM response not generated properly - {repr(e)}")
        return None, token_usage

    finally:
        process_time = time.perf_counter() - start_time
        logger.info(
          f"Model Used: {model} | "
          f"LLM response time: {process_time:.2f} | "
          f"token usage: {token_usage.model_dump()}"
        )


async def get_llm_response_with_tool_basic(client: AsyncOpenAI, model: str="gpt-4.1", messages: List[Optional[Dict[str, str]]] = [], tools: list = []):
    
    start_time = time.perf_counter()

    try:
        response = await client.chat.completions.create(
            model=model,
            tools=tools if tools else omit,
            messages=messages,
        )

        print("#############################")
        print(response.choices[0].message.content)
        print("##############################")

        # ---- Token usage tracking ----``
        token_usage = TokenUsage()
        token_usage.input_tokens += response.usage.prompt_tokens
        token_usage.output_tokens += response.usage.completion_tokens
        token_usage.cached_tokens += response.usage.prompt_tokens_details.cached_tokens if response.usage.prompt_tokens_details.cached_tokens else 0 
        return response, token_usage

    except Exception as e:
        print(repr(e))
        logger.error(f"LLM response not generated properly - {repr(e)}")
        return None, token_usage

    finally:
        process_time = time.perf_counter() - start_time
        logger.info(
          f"Model Used: {model} | "
          f"LLM response time: {process_time:.2f} | "
          f"token usage: {token_usage.model_dump()}"
        )


    # try:
    #     return response, token_usage
    # except json.JSONDecodeError as e:
    #     logger.error(f"LLM response resulted in JSON Decode error - {repr(e)}") 
    #     messages = [
    #         {"role": "system", "content": "Your task is to take user request and convert and return the response in proper JSON format. Only JSON output and nothing else"},
    #         {"role": "user", "content":messages[-1]["content"]},
    #         {"role": "assistant", "content":f"JSON decode error {repr(e)}"},
    #         {"role": "user", "content": str(response.choices[0].message.content)}
    #     ]
    #     print(messages)
    #     response = await client.chat.completions.create(
    #         model=model,
    #         messages=messages,
    #         response_format={"type": "json_object"}
    #     )

    #     token_usage.input_tokens += response.usage.completion_tokens
    #     token_usage.output_tokens += response.usage.prompt_tokens
    #     token_usage.cached_tokens += response.usage.prompt_tokens_details.cached_tokens if response.usage.prompt_tokens_details.cached_tokens else 0 
        
    #     try:
    #         json_response = get_json_from_str(str(response.choices[0].message.content))
    #         return json_response, token_usage
    #     except Exception as e:
    #         return None, token_usage
    # except Exception as e:
    #     logger.error(f"LLM response not generated properly - {repr(e)}") 
    #     return None, token_usage
    # finally: 
    #     process_time = time.perf_counter()-start_time               
    #     logger.info(f"Model Used: {model} | LLM response time: {process_time:.2f} | token usage: {token_usage.model_dump()}")
        




# async def get_resp(messages: list):
#     client = await get_llm()
#     response, token_usage =  await get_llm_response(client, messages=messages) 
#     print(response)
#     print(token_usage)

# if __name__ == "__main__":
#     messages = [
#         {"role": "system", "content": """Reply to user question in 1 reply to user in json format {"resp": "reply for the user question"}"""},
#         {"role": "user", "content": "Hi! how are you?"}
#     ]
#     asyncio.run(get_resp(messages))

    # asyncio.run(get_lmres("Hi! how are you?"))

# def get_llm(model: str = "gpt-4.1", base: str = "gpt"):
#     return ChatOpenAI(
#         model=model, temperature=0, api_key=os.environ.get("OPENAI_API_KEY")
#     )
