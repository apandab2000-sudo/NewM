from app.core.llms import get_llm_response, TokenUsage
from app.core.prompts import PromptGetter
from app.logger import get_logger
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional
from app.models import ReportSelectable

class ReportComponent:
    def __init__(
            self,
            dbname: str,
            llm,
            llm_name: str
        ):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
    
    async def extract_possible_routes(self, question: str):
        sys_prompt = self.prompt_getter.get_prompt("report_component_route")
        messages = [{"role": "system", "content": sys_prompt}]
        messages.append({"role": "user", "content": question})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        return results
    
    async def generate_insights_from_table(self, insights_metadata:str, table):
        sys_prompt = self.prompt_getter.get_prompt("report_insights_prompt")
        
        df = pd.DataFrame(table)
        table_stats = df.describe(include="all")
        user_content = f"Here is the table - {table} and table stats - {table_stats}. Adhere to following {insights_metadata}"
        
        messages = [{"role": "system", "content": sys_prompt}]
        messages.append({"role": "user", "content": user_content})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        return results
    


class ReportChat:
    def __init__(self,
            dbname: str,
            llm,
            llm_name: str
        ) -> None:
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
        self.schema_str = None

    def get_schema_str(self):
        schema_text_file_path = f"app/core/schema_strings/{self.dbname}.txt"
        with open(schema_text_file_path, "r", encoding="UTF-8") as f:
            self.schema_str = f.read()
        return self.schema_str

    async def identify_intent(self, query: str, history: List[Dict[str, str]] = []):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_intent_identification")

        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str()
        )
        
        messages = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage.input_tokens += token_usage.input_tokens
        self.token_usage.output_tokens += token_usage.output_tokens
        self.token_usage.cached_tokens += token_usage.cached_tokens
        return results


    async def kpi_verification(self, query: str, history: List[Dict[str, str]] = []):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_kpi_verification")

        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str()
        )
        
        messages = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage.input_tokens += token_usage.input_tokens
        self.token_usage.output_tokens += token_usage.output_tokens
        self.token_usage.cached_tokens += token_usage.cached_tokens
        return results


# class ReportCOmponentTable(ReportComponent):
#     def __init__(self, dbname: str, llm, llm_name: str, question: str):
#         super().__init__(dbname, llm, llm_name, question)

#     async def get_sql_from_query(self):
#         sys_prompt = self.prompt_getter.get_prompt("report_component_route")
#         messages = [{"role": "system", "content": sys_prompt}]
#         messages.append({"role": "user", "content": self.question})

#         results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
#         self.token_usage = token_usage
#         return results

    