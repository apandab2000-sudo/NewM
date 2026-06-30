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

    # async def identify_intent(self, query: str, history: List[Dict[str, str]] = []):
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_intent_identification")

    #     sys_prompt = sys_prompt.format(
    #         schema=self.get_schema_str()
    #     )
        
    #     messages = [{"role": "system", "content": sys_prompt}]
    #     if history:
    #         messages.extend(history)
    #     messages.append({"role": "user", "content": query})

    #     results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
    #     self.token_usage.input_tokens += token_usage.input_tokens
    #     self.token_usage.output_tokens += token_usage.output_tokens
    #     self.token_usage.cached_tokens += token_usage.cached_tokens
    #     return results


    # async def kpi_verification(self, query: str, history: List[Dict[str, str]] = []):
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_kpi_verification")

    #     sys_prompt = sys_prompt.format(
    #         schema=self.get_schema_str()
    #     )
        
    #     messages = [{"role": "system", "content": sys_prompt}]
    #     if history:
    #         messages.extend(history)
    #     messages.append({"role": "user", "content": query})

    #     results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
    #     self.token_usage.input_tokens += token_usage.input_tokens
    #     self.token_usage.output_tokens += token_usage.output_tokens
    #     self.token_usage.cached_tokens += token_usage.cached_tokens
    #     return results

    async def identify_intent(self, query: str, history: List = []):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_intent_identification").format(
            schema=self.get_schema_str()
        )
        messages = [{"role": "system", "content": sys_prompt}]
        if history: messages.extend(history)
        messages.append({"role": "user", "content": query})
        return await self._get_response(messages)


    # async def kpi_verification(self, query: str, history: List[Dict], current_selections: List[str]):
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_kpi_verification").format(
    #         schema=self.get_schema_str()
    #     )
        
    #     # We tell the LLM to detect if the user is ready to move to Dimensions
    #     user_content = (
    #         f"Context History: {history}\n"
    #         f"User Query/Action: {query if query else 'User updated selection boxes'}\n"
    #         f"Current Selected KPIs: {', '.join(current_selections)}\n"
    #         "Instruction: If the user query indicates they are happy with the list or want to move to the next step (e.g., 'proceed', 'looks good', 'next'), set 'proceed_to_next_step' to true."
    #     )
        
    #     messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}]
    #     return await self._get_response(messages)

    async def kpi_verification(self, query: str, history: List, intent: str, current_selections: List[str]):
        # FIXED: Now correctly accepts 'intent' argument
        sys_prompt = self.prompt_getter.get_prompt("report_builder_kpi_verification").format(
            schema=self.get_schema_str()
        )
        
        user_content = (
            f"Context History: {history}\n"
            f"Analytical Intent: {intent}\n"
            f"User Query/Action: {query if query else 'User updated selection boxes'}\n"
            f"Current Selected KPIs: {', '.join(current_selections)}\n"
            "Instruction: If the user query indicates they are happy with the list or want to move to the next step (e.g., 'proceed', 'looks good', 'next'), set 'status' to 'confirmed'."
        )
        
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}]
        return await self._get_response(messages)

    # async def dimension_verification(self, query: str, selected_kpis: List[str], history: List = []):
    #     # Suggest dims/time and check for natural language confirmation
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_dimension_step").format(
    #         schema=self.get_schema_str(),
    #         selected_kpis=", ".join(selected_kpis)
    #     )
    #     messages = [{"role": "system", "content": sys_prompt}]
    #     if history: messages.extend(history)
    #     messages.append({"role": "user", "content": query})
    #     return await self._get_response(messages)

    async def generate_questions(self, context: str):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_question_generator").format(
            schema=self.get_schema_str(),
            context=context
        )
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Generate 8-10 questions."}]
        return await self._get_response(messages)

    async def _get_response(self, messages):
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

    async def dimension_verification(self, query: str, selected_kpis: List[str], existing_selections: str, history: List = []):
        # FIX: Added 'existing_selections' to the format call to match the prompt
        sys_prompt = self.prompt_getter.get_prompt("report_builder_dimension_extraction").format(
            schema=self.get_schema_str(),
            selected_kpis=", ".join(selected_kpis),
            existing_selections=existing_selections  # Now provided!
        )
        messages = [{"role": "system", "content": sys_prompt}]
        if history: messages.extend(history)
        messages.append({"role": "user", "content": query if query else "Suggest dimensions based on selected KPIs."})
        return await self._get_response(messages)


    # async def identify_intent_and_requirements(self, query: str, selectables: list = []):
    #         sys_prompt = self.prompt_getter.get_prompt("report_builder_extraction_prompt")
            
    #         # Format existing selections so the LLM knows what is already picked
    #         selections_str = ", ".join([f"{s.option}" for s in selectables if s.is_selected])
            
    #         sys_prompt = sys_prompt.format(
    #             schema=self.get_schema_str(),
    #             query=query,
    #             existing_selections=selections_str
    #         )
            
    #         messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": query}]
    #         results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
    #         # self.token_usage.add(token_usage) 
    #         return results

############### working but extracting everything at once ##########

    # async def identify_intent_and_requirements(self, query: str, selectables: list = []):
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_extraction_prompt")
        
    #     # Format existing selections for context
    #     selections_str = ", ".join([f"{s.field}:{s.option}" for s in selectables if s.is_selected])
        
    #     sys_prompt = sys_prompt.format(
    #         schema=self.get_schema_str(),
    #         query=query,
    #         existing_selections=selections_str
    #     )
        
    #     messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": query}]
    #     results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        
    #     # IMPORTANT: Keep token tracking active
    #     self.token_usage.input_tokens += token_usage.input_tokens
    #     self.token_usage.output_tokens += token_usage.output_tokens
    #     self.token_usage.cached_tokens += token_usage.cached_tokens
        
    #     return results

    async def step_1_kpis(self, query: str, selectables: list = []):
        """Focuses strictly on Intent and KPIs."""
        sys_prompt = self.prompt_getter.get_prompt("report_builder_step1_kpis")
        selections_str = ", ".join([f"{s.option}" for s in selectables if s.is_selected and s.field == "kpis"])
        
        sys_prompt = sys_prompt.format(schema=self.get_schema_str(), query=query, existing_kpis=selections_str)
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": query}]
        
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        # self.token_usage.add(token_usage) # Assuming an add method or manual increment
        return results

    async def step_2_dimensions(self, query: str, selected_kpis: list, selectables: list = []):
        """Suggests Dimensions and Time Grain based on locked KPIs."""
        sys_prompt = self.prompt_getter.get_prompt("report_builder_step2_dims")
        selections_str = ", ".join([f"{s.option}" for s in selectables if s.is_selected and s.field in ["dimensions", "time_grain"]])
        
        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str(),
            selected_kpis=", ".join(selected_kpis),
            existing_selections=selections_str
        )
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": query}]
        
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        # self.token_usage.add(token_usage)
        return results

    async def step_3_questions(self, kpis: list, dims: list, grains: list):
        """Generates 8-10 natural language questions."""
        sys_prompt = self.prompt_getter.get_prompt("report_builder_step3_questions")
        context = f"KPIs: {kpis}, Dimensions: {dims}, Time Grains: {grains}"
        
        sys_prompt = sys_prompt.format(schema=self.get_schema_str(), context=context)
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Generate 8-10 questions."}]
        
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        # self.token_usage.add(token_usage)
        return results

    async def generate_questions(self, context: str):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_step3_questions").format(
            schema=self.get_schema_str(),
            context=context
        )
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Generate 8-10 questions."}]
        return await self._get_response(messages)