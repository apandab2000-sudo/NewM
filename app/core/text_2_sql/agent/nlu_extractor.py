from app.core.helper import get_system_prompt
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.core.llm_connections.base import LLMBase
from app.core.llms import get_llm_response, TokenUsage
from .models import ExtractedEntities


from app.logger import get_logger


logger = get_logger(__name__)


# USER_PROMPT = """
# User query: {user_query}
# Active filters: {filters}
# Recent chat history:
# {chat_history}
# """


USER_PROMPT = """
User query: {user_query}
Active filters: {filters}
"""


class NLUExtractor:
    def __init__(self, dbname: str, llm, llm_name: str = "gpt-4.1"):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name

        self.token_usage = TokenUsage()


    # def get_chat_history_questions(self, chat_history: Optional[list] = None, num_history: int = 2) -> str:
    #     if not chat_history:
    #         return "None"
        
    #     seen = set()
    #     lines = []

    #     for entry in reversed(chat_history):
    #         q = entry.user_query.strip()
    #         if q and q not in seen:
    #             seen.add(q)
    #             lines.append(f"{len(lines) + 1}. {q}")

    #         # if len(lines) >= num_history:
    #         #     break

    #     return "\n".join(lines) if lines else "None"  
    
    async def run(
        self, 
        user_query: str, 
        filters: str, 
        chat_history: Optional[list] = None
    ) -> str:
        
        system_prompt = get_system_prompt(self.dbname, "nlu_extractor")
        
        # chat_history_questions = self.get_chat_history_questions(chat_history)
        
        user_prompt = USER_PROMPT.format(
            user_query=user_query,
            filters=filters,
            # chat_history=chat_history_questions
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage += token_usage
        entities = ExtractedEntities(**results)
        logger.info("NLU extracted: %s", entities.model_dump())
        return entities


#     - entities:       list[str]   Domain nouns that likely correspond to table or column names.
# - metrics:        list[str]   Measurable quantities or aggregation targets (revenue, count, avg price).
# - entity_values:  list[str]   Specific filter values referenced (e.g. 'shipped', 'India', 'Q3 2024').
# - time_references: list[str]  Any date or time expressions (e.g. 'last month', '2023', 'Q1').
# - intent:         list[str]   out of: LOOKUP, AGGREGATION, RANKING, COMPARISON, TREND, FILTERING, MULTI-HOP, EXISTENCE, DISTRIBUTION, CORRELATION
 

USER_PROMPT2 = """
User query: {user_query}
Active filters: {filters}
"""

class NLUExtractorV2:
    def __init__(self, dbname: str, llm: LLMBase):
        self.dbname = dbname
        self.llm = llm
        from app.core.llm_connections.base import TokenUsage
        self.token_usage = TokenUsage()
    
    async def run(
        self, 
        user_query: str, 
        filters: str, 
        temperature: float = 0.0,
        max_tokens: int = 500
    ) -> ExtractedEntities:
        
        system_prompt = get_system_prompt(self.dbname, "nlu_extractor_v2")
                
        user_prompt = USER_PROMPT2.format(
            user_query=user_query,
            filters=filters
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        results = await self.llm.generate(
            messages, 
            json_schema=ExtractedEntities, 
            temperature=temperature, 
            max_tokens=max_tokens
        )
        self.token_usage += results.token_usage
        logger.info("NLU extracted: %s", results.parsed_json.model_dump())
        return results.parsed_json