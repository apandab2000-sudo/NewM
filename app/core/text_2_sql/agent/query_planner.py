from sqlalchemy.ext.asyncio import AsyncSession
from app.core.helper import get_system_prompt
from app.core.helper import get_system_prompt
from app.core.llm_connections.base import LLMBase, TokenUsage
from app.logger import get_logger
from .models import QueryPlannerModel


logger = get_logger(__name__)



USER_PROMPT = """
User query: {user_query}
Active filters: {filters}
NLU_Output: {nlu_result}
Database_Schema: {db_schema}
"""


class QueryPlanner:
    def __init__(self, dbname: str, llm: LLMBase):
        self.dbname = dbname
        self.llm = llm
        self.token_usage = TokenUsage()


    async def run(self, user_query: str, filters: str, nlu_result: str, db_schema: str):
        system_prompt = get_system_prompt(self.dbname, "query_planner")

        user_prompt = USER_PROMPT.format(
            user_query=user_query,
            filters=filters,
            nlu_result=nlu_result,
            db_schema=db_schema
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await self.llm.generate(messages, json_schema=QueryPlannerModel)
        self.token_usage += self.llm.token_usage
        return response.parsed_json
