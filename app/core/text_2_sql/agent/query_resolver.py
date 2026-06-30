import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.helper import get_system_prompt
# from app.core.llms
# from app.core.helper import get_system_prompt
# from app.core.llm_connections.base import LLMBase, TokenUsage
from app.logger import get_logger
# from .models import QueryResolverModel
# from app.core.llm_connections.base import LLMBase, TokenUsage
from app.core.llms import get_llm_response, TokenUsage
from .models import QueryResolverModel


logger = get_logger(__name__)


USER_PROMPT = """
User query: {user_query}
Active filters: {filters}
Recent chat history:
{chat_history}
"""


class QueryResolver:
    def __init__(self, dbname: str, llm, llm_name):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name

        self.token_usage = TokenUsage()

    def get_formatted_chat_history(self, chat_history: list = [], num_history: int = 2):
        if chat_history:
            resolved_questions = []
            for entry in chat_history:
                if entry["role"] == "assistant":
                    content_json = json.loads(entry["content"])
                    if content_json["status"] == "complete":
                        resolved_questions.append(f"response: {content_json['response'][0]['sql_query']}")
                    elif content_json["status"] == "awaiting_human_input":
                        resolved_questions.append(f"response: {content_json['response']}")
                    else:
                        pass
                else:
                    resolved_questions.append(f"Ques: {entry['content']}")
            if resolved_questions:
                return "\n".join(resolved_questions[-num_history*2:])
            print("#####################")
            print(resolved_questions)
            print("#####################")
        return "None"


    async def run(self, user_query: str, filters: str, chat_history: list = [], num_history: int = 1):
        system_prompt = get_system_prompt(self.dbname, "query_resolver")
        chat_history = self.get_formatted_chat_history(chat_history=chat_history, num_history=num_history)

        user_prompt = USER_PROMPT.format(
            user_query=user_query,
            filters=filters,
            chat_history=chat_history
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage += token_usage
        resolved_query_mappings = QueryResolverModel(**results)
        logger.info("Resolved Query results: %s", resolved_query_mappings.model_dump(), extra={"event_type": "query_resolved", "db_name": self.dbname})
        return resolved_query_mappings

        # response = await self.llm.generate(messages, json_schema=QueryResolverModel, max_tokens=200)
        # self.token_usage += self.llm.token_usage
        # return response.parsed_json
