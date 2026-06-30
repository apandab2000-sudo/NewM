from langchain_core.prompts import PromptTemplate
import json
import re
from prompts import PromptGetter
from app.logger import get_logger

logger = get_logger()

class DRILLDOWN_LLM:
    def __init__(self, dbname: str, llm, client_db):
        self.client = dbname
        self.llm = llm
        self.client_db = client_db
        self.prompt_getter = PromptGetter(dbname)
        self.token_usage_dict = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0
        }

        schema_text_file_path = f"app/core/schema_strings/{dbname}.txt"
        with open(schema_text_file_path, "r", encoding="UTF-8") as f:
            self.schema_str = f.read()

        self.generated_tables = []

    async def get_reformulated_question(self, user_query, click_filter, drilldown_col_name):
        prompt = self.prompt_getter.get_prompt("drilldown_reformulated_question_prompt")
        prompt = PromptTemplate.from_template(prompt)
        pr = prompt.invoke({
            "user_query": user_query,
            "click_filter": click_filter,
            "drilldown_col_name": drilldown_col_name,
            "schema": self.schema_str
            })
        response = await self.llm.ainvoke(pr)
        # response = await self.llm.ainvoke(prompt)
        json_match = re.search(r"\{[\s\S]*\}", response.content)

        if not json_match:
            return ""

        json_match = json.loads(json_match.group(0))
        modified_user_query = json_match['reformulated_question']

        self.token_usage_dict["input_tokens"] += response.usage_metadata["input_tokens"]
        self.token_usage_dict["output_tokens"] += response.usage_metadata["output_tokens"]
        print("Token usage after self sufficiency check", self.token_usage_dict)

        
        return modified_user_query

