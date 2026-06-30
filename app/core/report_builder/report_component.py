from app.core.llms import get_llm_response, TokenUsage, get_llm_response_with_tool
from app.core.prompts import PromptGetter
from app.logger import get_logger
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional, Any
from app.models import ReportSelectable
import json
import asyncio
from app.databases.client_sql.operations import (
    get_table_from_sql, 
    get_table_and_status_and_columns
)
from app.core.graphs.echarts.graphs import GraphGenerator
from app.logger import get_logger
import numpy as np

logger = get_logger()

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
    
    def _process_kpi_logic(self, table_json, title):
        """
        Transforms raw table data into a KPI object.
        Calculates: Current Value, Growth %, and Sparkline (last 10 points).
        """
        if not table_json:
            return None
        
        clean_title = str(title).replace("_", " ").title()


        df = pd.DataFrame(table_json)
        # Identify numerical columns only
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if not num_cols:
            return None

        # We take the first numerical column for a single KPI card
        target_col = num_cols[0]
        series = df[target_col].dropna().tolist()

        if not series:
            return None

        current_val = series[-1]
        previous_val = series[-2] if len(series) > 1 else None
        
        growth_pct = 0
        if previous_val is not None and previous_val != 0:
            growth_pct = ((current_val - previous_val) / previous_val) * 100

        return {
            "title": clean_title,
            "value": round(current_val, 2),
            "previous_value": round(previous_val, 2) if previous_val is not None else None,
            "growth_percentage": round(growth_pct, 2),
            "growth_status": "up" if growth_pct >= 0 else "down",
            "sparkline": series[-10:]
            # "unit": "" 
        }

    def _process_smartart_logic(self, table_json, title, style="list"):
        """
        Transforms table rows into SmartArt items.
        First column = Label, Second column = Description.
        """
        if not table_json:
            return None

        df = pd.DataFrame(table_json)
        limit = 10 if style == "list" else 7
        df = df.head(limit) 
        cols = df.columns.tolist()
        
        if not cols:
            return None

        items = []
        for _, row in df.iterrows():
            # Extract label and description (handle missing description column)
            label = str(row[cols[0]]).replace("_", " ").title()
            description = str(row[cols[1]]) if len(cols) > 1 else None
            
            items.append({
                "label": label,
                "description": description
            })

        return {
            "title": title.replace("_", " ").title(),
            "style": style,
            "items": items,
            "count": len(items)
        }


    async def generate_paragraph_text(self, objective: str, table_data=None, word_limit=200):
        """
        Uses the LLM to generate a narrative paragraph.
        If table_data is provided, it describes the data.
        """
        sys_prompt = self.prompt_getter.get_prompt("paragraph_generation_prompt")
        
        user_content = f"Objective: {objective}\nWord Limit: {word_limit} words."
        if table_data:
            user_content += f"\nBase your narrative on this data: {table_data}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content}
        ]

        # Call LLM
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        
        # Expecting LLM to return {"text": "..."}
        return results.get("text") if isinstance(results, dict) else results

    async def generate_header_data(self, report_name: str, report_desc: str, user_query: str, content_context: str):
            sys_prompt = self.prompt_getter.get_prompt("header_generation_prompt")
            
            user_content = (
                f"REPORT METADATA:\n- Name: {report_name or 'Untitled'}\n- Goal: {report_desc or 'Not specified'}\n\n"
                f"CURRENT REPORT CONTENT (Base the title on this):\n{content_context}\n\n"
                f"USER INSTRUCTION: {user_query}"
            )

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ]

            results, _ = await get_llm_response(self.llm, self.llm_name, messages)
            return results if isinstance(results, dict) else {}
            
    async def generate_list_component_items(self, user_query: str, table_data: list, title: str):
        """
        Unified LLM-driven List Processor.
        The LLM decides if it should return raw items or analytical reasoning points 
        based on the user's question and the data provided.
        """
        sys_prompt = self.prompt_getter.get_prompt("list_generation_prompt")
        
        user_content = (
            f"User Question: {user_query}\n"
            f"Data Provided: {table_data}\n"
            f"Suggested Title: {title}"
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content}
        ]

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        
        if isinstance(results, dict):
            return results
        return {"title": title, "items": [str(results)]}


    # def _process_indicator_logic(self, table_json, title, include_trends=False):
    #     if not table_json:
    #         return None

    #     df = pd.DataFrame(table_json)
    #     # Identify all numerical columns
    #     num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
    #     if not num_cols:
    #         return None

    #     indicator_results = []
    #     for col in num_cols:
    #         series = df[col].dropna().tolist()
    #         if not series:
    #             continue

    #         current_val = series[-1]
            
    #         display_title = col.replace("_", " ").title() if len(num_cols) > 1 else title
            
    #         card = {
    #             "title": display_title,
    #             "value": round(current_val, 2),
    #             "unit": ""
    #         }

    #         # Force comparison if data is available and trends are requested
    #         if include_trends and len(series) > 1:
    #             prev_val = series[-2]
    #             growth_pct = ((current_val - prev_val) / prev_val) * 100 if prev_val != 0 else 0
                
    #             card.update({
    #                 "previous_value": round(prev_val, 2),
    #                 "growth_percentage": round(growth_pct, 2),
    #                 "growth_status": "up" if growth_pct >= 0 else "down",
    #                 "sparkline": series[-10:] 
    #             })
            
    #         indicator_results.append(card)

    #     return indicator_results

class ReportChatBkp:
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

    async def identify_intent(self, query: str, history: List = []):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_intent_identification").format(
            schema=self.get_schema_str()
        )
        messages = [{"role": "system", "content": sys_prompt}]
        if history: messages.extend(history)
        messages.append({"role": "user", "content": query})
        return await self._get_response(messages)


    async def kpi_verification(self, query: str, history: List, intent: str, current_selections: List[str]):
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

   
    async def generate_storyboard(self, context: str, query: str = "", history: list = []):
        sys_prompt = self.prompt_getter.get_prompt("report_builder_step3_storyboard").format(
            schema=self.get_schema_str(),
            context=context
        )
        
        messages = [{"role": "system", "content": sys_prompt}]
        if history: messages.extend(history)
        
        # If the user is giving feedback on the storyboard, we send that as the user message
        user_content = query if query else "Please generate the recommended storyboard components."
        messages.append({"role": "user", "content": user_content})

        return await self._get_response(messages)
    

# class Kpis(BaseModel):
#     metrics: Optional[List[str]] = None
#     dimensions: Optional[List[str]] = None
#     time_grains: Optional[List[str]] = None
#     audience: Optional[List[str]] = None


class AgentState(BaseModel):
    initial_query: Optional[str] = None
    intent_messages: List[Dict[str, Any]] = []
    kpi_messages: List[Dict[str, Any]] = []
    additional_detail_messages: List[Dict[str, Any]] = []
    structure_messages: List[Dict[str, Any]] = []
    report_messages: List[Dict[str, Any]] = []
    intent: Optional[str] = None
    kpis: Optional[Dict[str, Any]] = None
    structure: Optional[Dict[str, Any]] = None
    # report: Optional[List[str]] = None
    report: Optional[Dict[str, Any]] = None  # Changed from List to Dict

    build_type: Optional[Literal["report", "dashboard"]] = None
    additional_details: Optional[Dict[str, Any]] = None
    completed_steps: List[
        Literal[
            "extract_or_modify_intent", 
            "extract_or_modify_kpis",
            "extract_or_modify_contextual_scope",
            "build_or_modify_structure", 
            "build_or_modify_report",
            None
        ]
    ] = []


tools = [
    {
        "type": "function",
        "name": "extract_or_modify_intent",
        "description": "Extracts or modifies the Intent",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
        #     "properties": {
        #         "query": {
        #             "type": "string",
        #             "description": "User provided query"
        #         }
        #     },
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "extract_or_modify_kpis",
        "description": "Extract or modifies KPIs in form of dimensions, metrics and time grains applicable on data.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            #     "intent": {
            #         "type": "string",
            #         "description": "detailed intent extracted from extract_intent tool"
            #     }
            # },
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "extract_or_modify_contextual_scope",
        "description": "Extracts or modifies additional details like scoping ,auedience, filters etc.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            #     "intent": {
            #         "type": "string",
            #         "description": "detailed intent extracted from extract_intent tool"
            #     }
            # },
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "build_or_modify_structure",
        "description": "Builds/modifies the structure/layout of report or dashboard",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            #     "intent": {
            #         "type": "string",
            #         "description": "detailed intent extracted from extract_intent tool"
            #     }
            # },
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "build_or_modify_report",
        "description": "Builds or modifies the report or dashbaord. ",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            #     "intent": {
            #         "type": "string",
            #         "description": "detailed intent extracted from extract_intent tool"
            #     }
            # },
            "required": [],
            "additionalProperties": False
        }
    }
]


class ReportChat:
    def __init__(self,
            dbname: str,
            llm,
            llm_name: str,
            agent_state: AgentState,
            vector_client = None
        ) -> None:
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
        self.agent_state = agent_state
        self.vector_client = vector_client


    async def extract_or_modify_intent(self, query: str) -> str:
        """Extract intent with error handling"""
        try:
            self.agent_state.completed_steps = []
            sys_prompt = self.prompt_getter.get_prompt("workflow_intent_identification_prompt")
            sys_prompt = sys_prompt.format(
                schema=self.get_schema_str(), 
                current_intent=self.agent_state.intent or "Not yet determined"
            )
            messages = [{"role": "user", "content": sys_prompt}]

            self.agent_state.intent_messages += [{"role": "user", "content": query}]
            messages += self.agent_state.intent_messages

            logger.info("######## INTENT MESSAGES ########")
            logger.info(json.dumps(self.agent_state.intent_messages))
            
            for m in messages:
                if isinstance(m.get("content"), dict):
                    m["content"] = json.dumps(m["content"])

            resp = await self._get_response(messages)
            
            if not resp:
                logger.error("Intent extraction returned empty response")
                return json.dumps({
                    "error": "Failed to identify intent",
                    "status": "failed"
                })
            
            self.agent_state.intent_messages += [{"role": "assistant", "content": json.dumps(resp) if isinstance(resp, dict) else resp}]
            
            self.agent_state.intent = resp.get("intent") if isinstance(resp, dict) else None
            self.agent_state.build_type = resp.get("build_type") if isinstance(resp, dict) else None

            if isinstance(resp, dict) and resp.get("case", "").upper() == "CASE_1" and self.agent_state.initial_query is None:
                self.agent_state.initial_query = query

            return json.dumps(resp) if isinstance(resp, dict) else resp
        
        except Exception as e:
            logger.error(f"Error in extract_or_modify_intent: {str(e)}", exc_info=True)
            return json.dumps({
                "error": f"Intent extraction failed: {str(e)}",
                "status": "failed"
            })

    async def extract_or_modify_kpis(self, query: str) -> str:
        """Extract KPIs with error handling"""
        try:
            self.agent_state.completed_steps = ["extract_or_modify_intent"]

            sys_prompt = self.prompt_getter.get_prompt("workflow_kpi_prompt")
            sys_prompt = sys_prompt.format(
                schema=self.get_schema_str(), 
                intent=self.agent_state.intent or "Not determined",
                current_kpis=json.dumps(self.agent_state.kpis) if self.agent_state.kpis else "{}"
            )
            messages = [{"role": "user", "content": sys_prompt}]

            self.agent_state.kpi_messages += [{"role": "user", "content": query}]
            messages += self.agent_state.kpi_messages

            logger.info("######## KPI MESSAGES ########")
            logger.info(json.dumps(self.agent_state.kpi_messages))
            
            for m in messages:
                if isinstance(m.get("content"), dict):
                    m["content"] = json.dumps(m["content"])

            resp = await self._get_response(messages)
            
            if not resp:
                logger.error("KPI extraction returned empty response")
                return json.dumps({
                    "error": "Failed to identify KPIs",
                    "status": "failed"
                })
            
            self.agent_state.kpi_messages += [{"role": "assistant", "content": json.dumps(resp) if isinstance(resp, dict) else resp}]
            
            self.agent_state.kpis = resp.get("kpis") if isinstance(resp, dict) else None
            return json.dumps(resp) if isinstance(resp, dict) else resp
        
        except Exception as e:
            logger.error(f"Error in extract_or_modify_kpis: {str(e)}", exc_info=True)
            return json.dumps({
                "error": f"KPI extraction failed: {str(e)}",
                "status": "failed"
            })

    async def extract_or_modify_contextual_scope(self, query: str):
        self.agent_state.completed_steps = ["extract_or_modify_intent", "extract_or_modify_kpis"]

        sys_prompt = self.prompt_getter.get_prompt("workflow_additional_details_prompt")
        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str(), 
            intent = self.agent_state.intent,
            kpis = self.agent_state.kpis,
            current_additional_details = self.agent_state.additional_details
        ) 
        messages = [{"role": "user", "content": sys_prompt}]

        self.agent_state.additional_detail_messages += [{"role": "user", "content": query}]

        messages += self.agent_state.additional_detail_messages

        print("######## CONTEXTUAL SCOPE MESSAGES ########")
        print(self.agent_state.additional_detail_messages)
        print("######## / CONTEXTUAL SCOPE MESSAGES ########")
        
        for m in messages:
            if isinstance(m["content"], dict):
                m["content"] = json.dumps(m["content"])

        resp = await self._get_response(messages)
        self.agent_state.additional_detail_messages += [{"role": "assistant", "content": resp}]
        
        self.agent_state.additional_details = resp
        return json.dumps(resp)
    

    async def build_or_modify_structure(self, query: str):
        self.agent_state.completed_steps = ["extract_or_modify_intent", "extract_or_modify_kpis", "extract_or_modify_contextual_scope"]

        sys_prompt = self.prompt_getter.get_prompt("workflow_structure_prompt")
        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str(), 
            intent = self.agent_state.intent,
            kpis = self.agent_state.kpis,
            scope = self.agent_state.additional_details,
            current_structure = self.agent_state.structure
        ) 
        messages = [{"role": "user", "content": sys_prompt}]

        self.agent_state.structure_messages += [{"role": "user", "content": query}]

        messages += self.agent_state.structure_messages

        print("######## STRUCTURE MESSAGES ########")
        print(self.agent_state.structure_messages)
        print("######## / STRUCTURE MESSAGES ########")
        
        for m in messages:
            if isinstance(m["content"], dict):
                m["content"] = json.dumps(m["content"])

        resp = await self._get_response(messages)
        self.agent_state.structure_messages += [{"role": "assistant", "content": resp}]
        
        self.agent_state.structure = resp

        if resp:
            report_structure = {}
            report_structure["report_title"] = resp["report_title"]
            report_structure["sections"] = []
            for section in resp["sections"]:
                report_structure["sections"].append(
                    {
                        "heading": section["heading"],
                        "section_id": section["section_id"],
                        "components": [
                            {
                                "component_id": c["component_id"],
                                "title": c["title"],
                                "type": c["type"]
                            } for c in section["components"]
                        ]
                    }
                )
            return json.dumps(report_structure)
        return None


################# new tool added 
    async def refine_report_component(self, query: str, modification_type: str = "enhance") -> str:
        """
        Modify existing report components without regenerating.
        
        Types:
        - add_insights: Add analytical insights to components
        - add_metric: Add new metrics/dimensions
        - add_dimension: Add dimensional breakdowns
        - enhance: General enhancement
        """
        if not self.agent_state.report:
            return json.dumps({
                "error": "No report to modify",
                "status": "failed"
            })
        sys_prompt = self.prompt_getter.get_prompt("refine_component_prompt")

        # Find the component in the generated report
        component = self._find_component_by_id(component_id)
        if not component:
            return json.dumps({"error": "Component not found"})
        
        sys_prompt = sys_prompt.format(
            component=json.dumps(component),
            current_insights=component.get("component_output", {}).get("insights")
        )
        
        messages = [{"role": "user", "content": sys_prompt}]
        messages.append({"role": "user", "content": query})
        
        try:
            response, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
            
            self.token_usage.input_tokens += token_usage.input_tokens
            self.token_usage.output_tokens += token_usage.output_tokens
            self.token_usage.cached_tokens += token_usage.cached_tokens

            if not response:
                return json.dumps({
                    "status": "failed",
                    "error": "Failed to generate modifications"
                })

            refined_data = json.loads(response) if isinstance(response, str) else response

            # Apply modifications to report
            if modification_type == "add_insights":
                await self._add_insights_to_report(query)
            elif modification_type == "add_metric":
                await self._add_metrics_to_report(query)
            elif modification_type == "add_dimension":
                await self._add_dimensions_to_report(query)
            else:
                await self._enhance_report(query)

            # Track modification in state
            if not hasattr(self.agent_state, 'modifications'):
                self.agent_state.modifications = []
            
            self.agent_state.modifications.append({
                "type": modification_type,
                "query": query,
                "timestamp": datetime.now().isoformat()
            })

            return json.dumps({
                "status": "success",
                "message": refined_data.get("message", "Report modified successfully"),
                "modifications": refined_data.get("modifications", [])
            })

        except Exception as e:
            logger.error(f"Error refining report: {str(e)}")
            return json.dumps({
                "status": "failed",
                "error": f"Modification failed: {str(e)}"
            })

    async def _add_insights_to_report(self, query: str):
        """Add insights to the first component or executive summary."""
        if isinstance(self.agent_state.report, dict):
            if "sections" in self.agent_state.report:
                # Add to executive summary first
                for section in self.agent_state.report.get("sections", []):
                    if section.get("section_id") == "exec_summary":
                        if "insights" not in section:
                            section["insights"] = []
                        section["insights"].append({
                            "query": query,
                            "timestamp": datetime.now().isoformat()
                        })
                        break

    async def _add_metrics_to_report(self, query: str):
        """Add metrics to report components."""
        if isinstance(self.agent_state.report, dict):
            if "sections" in self.agent_state.report:
                for section in self.agent_state.report.get("sections", []):
                    for component in section.get("components", []):
                        if component.get("type") in ["kpi_card", "chart"]:
                            if "suggested_metrics" not in component:
                                component["suggested_metrics"] = []
                            component["suggested_metrics"].append(query)
                            break

    async def _add_dimensions_to_report(self, query: str):
        """Add dimensional breakdowns."""
        if isinstance(self.agent_state.report, dict):
            if "sections" in self.agent_state.report:
                for section in self.agent_state.report.get("sections", []):
                    for component in section.get("components", []):
                        if "bound_dimensions" in component:
                            component["bound_dimensions"].append(query)

    async def _enhance_report(self, query: str):
        """General enhancement logic."""
        if isinstance(self.agent_state.report, dict):
            if "enhancements" not in self.agent_state.report:
                self.agent_state.report["enhancements"] = []
            self.agent_state.report["enhancements"].append({
                "description": query,
                "timestamp": datetime.now().isoformat()
            })

    def _summarize_report(self) -> str:
        """Create a brief summary of current report structure."""
        if not self.agent_state.report:
            return "Empty report"
        
        if isinstance(self.agent_state.report, dict):
            sections = self.agent_state.report.get("sections", [])
            return f"Report with {len(sections)} sections and {sum(len(s.get('components', [])) for s in sections)} components"
        
        return str(type(self.agent_state.report))



    async def run_full_pipeline(self, query: str):
        """EXPRESS TRACK: For direct 'Generate Report' requests."""
        logger.info("Executing Full Auto-Generation Pipeline")
        await self.extract_or_modify_intent(query)
        await self.extract_or_modify_kpis(query)
        # Skip Step 3 (Scope) for auto-gen to prevent loops
        self.agent_state.additional_details = {}
        await self.build_or_modify_structure(query)
        final_report = await self.build_or_modify_report(query)
        return json.loads(final_report)

   
    async def workflow_agent(self, query: str, client_pool: Any,skip_intent: dict = None, chat_history: list = []) -> dict:
        """
        Orchestrator with Intent Clarification Gate.
        
        Flow:
        1. Intent Identification: Extract intent from query
        2. Intent Validation: If unclear (CASE_2), ask clarifying questions
        3. Clarification Loop: Keep asking until intent is clear (CASE_1)
        4. Proceed to KPIs: Once intent is confirmed, continue pipeline
        5. Safety Checks: Prevent unwanted auto-generation based on user keywords
        """
        # Determine current state before we start the loop
        was_discovery_phase = self.agent_state.intent is None
        
        # Keywords to check what the user actually wants
        query_lc = query.lower()
        user_wants_report = any(x in query_lc for x in ["report", "dashboard", "build all", "final"])
        user_wants_structure = any(x in query_lc for x in ["structure", "layout", "blueprint"])

        sys_prompt = self.prompt_getter.get_prompt("workflow_system_prompt_v3").format(
            current_state=self.agent_state.model_dump()
        )
        messages = [{"role": "system", "content": sys_prompt}]
        if chat_history: 
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        # --- START REASONING LOOP ---
        for i in range(4): # Max iterations to prevent infinite loops
            logger.info(f"Workflow iteration {i+1}")
            
            try:
                response, token_usage = await get_llm_response_with_tool(
                    self.llm, self.llm_name, messages, tools
                )
                self._track_tokens(token_usage)

                # SAFETY CHECK 1: Validate response object
                if not response:
                    logger.error("No response from LLM")
                    return {
                        "response": "I encountered an issue processing your request. Please try again.",
                        "next_action": "error",
                        "status": "failed",
                        "options": None
                    }

                if not response.output or len(response.output) == 0:
                    logger.error("Empty output from LLM response")
                    return {
                        "response": "The system couldn't generate a proper response. Please try again.",
                        "next_action": "error",
                        "status": "failed",
                        "options": None
                    }

                # Check response type
                response_type = response.output[0].type if response.output else None
                logger.info(f"LLM Response Type: {response_type}")

                # =========================================================================
                # CASE A: LLM wants to call one or more tools
                # =========================================================================
                if response_type == "function_call":
                    tool_name = response.output[0].name
                    logger.info(f"Tool called: {tool_name}")
                    tool_result = await self._call_tool(tool_name, query, client_pool)

                    # ─────────────────────────────────────────────────────────────────
                    # RULE 1: DISCOVERY PHASE HANDLING (Intent Extraction)
                    # If we are in discovery phase (no intent yet), run extract_or_modify_intent
                    # and check if intent is CLEAR before proceeding to KPIs
                    # ─────────────────────────────────────────────────────────────────
                    if was_discovery_phase and tool_name == "extract_or_modify_intent":
                        logger.info(f"Guided Start: Executing {tool_name} to identify intent.")
                        
                        # Execute the intent extraction tool
                        tool_result = await self._call_tool(tool_name, query, client_pool)
                        
                        # Validate tool result
                        if not tool_result:
                            logger.error(f"Tool {tool_name} returned None")
                            return {
                                "response": f"Failed to process step: {tool_name}",
                                "next_action": "error",
                                "status": "failed",
                                "options": None
                            }
                        
                        logger.info(f"Tool result: {str(tool_result)[:200]}")
                        
                        # Parse tool result to check intent clarity
                        try:
                            intent_result = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse intent result")
                            return {
                                "response": "Failed to analyze your request. Please try again.",
                                "next_action": "error",
                                "status": "failed",
                                "options": None
                            }
                        
                        # ═══════════════════════════════════════════════════════════════
                        # INTENT CLARITY CHECK
                        # ═══════════════════════════════════════════════════════════════
                        case = intent_result.get("case", "").upper()
                        intent_identified = intent_result.get("intent_identified", False)
                        
                        logger.info(f"Intent Case: {case}, Intent Identified: {intent_identified}")
                        
                        # CASE 1: INTENT IS CLEAR - Proceed to next step (KPIs)
                        if case == "CASE_1" and intent_identified:
                            logger.info("✓ Intent is CLEAR. Moving to KPI extraction.")
                            
                            # Update agent state with identified intent
                            self.agent_state.intent = intent_result.get("intent")
                            self.agent_state.build_type = intent_result.get("build_type")
                            
                            # Add to messages for context (CORRECT FORMAT)
                            messages.append(response.output[0])
                            messages.append({
                                "type": "function_call_output",
                                "call_id": response.output[0].call_id,
                                "output": tool_result if isinstance(tool_result, str) else json.dumps(tool_result)
                            })
                            
                            # Continue the loop - LLM will now call extract_or_modify_kpis
                            logger.info("Looping back for next tool decision...")
                            continue
                        
                        # CASE 2: INTENT IS AMBIGUOUS - Ask clarifying questions
                        elif case == "CASE_2" or not intent_identified:
                            logger.info("⚠ Intent is AMBIGUOUS. Asking for clarification.")
                            
                            # Get suggestions from the tool result
                            suggestions = intent_result.get("suggestions", [])
                            reasoning = intent_result.get("reasoning", "")
                            
                            # Format the response with clarifying questions
                            clarification_message = self._format_clarification_message(
                                reasoning=reasoning,
                                suggestions=suggestions
                            )
                            
                            return {
                                "response": clarification_message,
                                "next_action": "waiting_for_clarification",
                                "status": "intent_unclear",
                                "options": suggestions if suggestions else None,
                                "reasoning": reasoning
                            }
                        
                        else:
                            logger.warning(f"Unexpected case: {case}")
                            return {
                                "response": "Unable to determine your request clearly. Could you please provide more details?",
                                "next_action": "waiting_for_clarification",
                                "status": "unclear",
                                "options": None
                            }

                        # ─────────────────────────────────────────────────────────────────
                        # RULE 2: KPI EXTRACTION (After intent is confirmed)
                        # ─────────────────────────────────────────────────────────────────
                        if tool_name == "extract_or_modify_kpis":
                            logger.info("Executing KPI Extraction")
                            
                            # Verify we have an intent before extracting KPIs
                            if not self.agent_state.intent:
                                logger.error("No intent found before KPI extraction")
                                return {
                                    "response": "Cannot extract KPIs without a clear intent. Please clarify your request first.",
                                    "next_action": "waiting_for_clarification",
                                    "status": "missing_intent",
                                    "options": None
                                }
                            
                            tool_result = await self._call_tool(tool_name, query,client_pool)
                            
                            if not tool_result:
                                logger.warning(f"Tool {tool_name} returned empty result")
                                tool_result = json.dumps({
                                    "error": f"Tool execution failed: {tool_name}",
                                    "status": "failed"
                                })
                            
                            # Add tool call and result to messages (CORRECT FORMAT)
                            messages.append(response.output[0])
                            messages.append({
                                "type": "function_call_output",
                                "call_id": response.output[0].call_id,
                                "output": tool_result if isinstance(tool_result, str) else json.dumps(tool_result)
                            })
                            
                            # Continue the loop
                            logger.info("Looping back for next tool decision...")
                            continue

                    # ─────────────────────────────────────────────────────────────────
                    # RULE 3: SPECIFICITY CHECK
                    # If user asked for structure, but LLM tries to call 'build_report',
                    # and user DID NOT mention the word 'report', we force a break.
                    # ─────────────────────────────────────────────────────────────────
                    if tool_name == "build_or_modify_report" and user_wants_structure and not user_wants_report:
                        logger.info("Preventing auto-report generation: User only asked for structure.")
                        return {
                            "response": "I have generated the report structure for you. Would you like me to proceed and fetch the data to build the final report now?",
                            "next_action": "waiting_for_approval",
                            "status": "structure_complete",
                            "options": None
                        }

                    # ─────────────────────────────────────────────────────────────────
                    # NORMAL TOOL EXECUTION: Execute all tools in this round
                    # ─────────────────────────────────────────────────────────────────
                    messages.extend(response.output)
                    
                    for tool_call in response.output:
                        if tool_call.type == "function_call":
                            logger.info(f"Executing tool: {tool_call.name}")
                            tool_result = await self._call_tool(tool_call.name, query,client_pool)
                            
                            if not tool_result:
                                logger.warning(f"Tool {tool_call.name} returned empty result")
                                tool_result = json.dumps({
                                    "error": f"Tool execution failed: {tool_call.name}",
                                    "status": "failed"
                                })
                            
                            messages.append({
                                "type": "function_call_output",
                                "call_id": tool_call.call_id,
                                "output": tool_result if isinstance(tool_result, str) else json.dumps(tool_result)
                            })
                    
                    # ─────────────────────────────────────────────────────────────────
                    # If the tool we just ran was 'build_or_modify_report', we're done
                    # ─────────────────────────────────────────────────────────────────
                    if any(tc.name == "build_or_modify_report" for tc in response.output):
                        logger.info("Report building tool executed. Returning result.")
                        try:
                            result = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                            if "options" not in result:
                                result["options"] = None
                            return result
                        except Exception as e:
                            logger.error(f"Failed to parse tool result: {e}")
                            return tool_result if isinstance(tool_result, dict) else {
                                "error": str(e),
                                "status": "failed",
                                "options": None
                            }
                    
                    # Loop back to see if LLM wants to chain the next allowed tool
                    logger.info("Looping back for next tool decision...")
                    continue
                
                # =========================================================================
                # CASE B: LLM returned a text message (not a function call)
                # =========================================================================
                elif response_type == "message":
                    logger.info("LLM returned a message response")
                    
                    # SAFETY CHECK 2: Validate output_text exists and is not empty
                    if not hasattr(response, 'output_text') or not response.output_text:
                        logger.error(f"Message response has empty output_text. Response object: {response}")
                        return {
                            "response": "The system generated an empty response. Please try again.",
                            "next_action": "error",
                            "status": "failed",
                            "options": None
                        }
                    
                    try:
                        logger.info(f"Parsing message: {response.output_text[:200]}")
                        parsed = json.loads(response.output_text)
                        if "options" not in parsed:
                            parsed["options"] = None
                        return parsed
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON decode error: {str(je)}")
                        logger.error(f"Raw text: {response.output_text}")
                        return {
                            "response": response.output_text[:500],
                            "next_action": "waiting_for_approval",
                            "status": "parsing_failed",
                            "options": None
                        }
                
                # =========================================================================
                # CASE C: Unexpected response type
                # =========================================================================
                else:
                    logger.warning(f"Unexpected response type: {response_type}")
                    return {
                        "response": f"Unexpected response type: {response_type}",
                        "next_action": "error",
                        "status": "failed",
                        "options": None
                    }

            except Exception as e:
                logger.error(f"Workflow iteration {i} failed: {str(e)}", exc_info=True)
                return {
                    "response": f"An error occurred during processing: {str(e)}",
                    "next_action": "error",
                    "status": "failed",
                    "error_details": str(e),
                    "options": None
                }

        # =========================================================================
        # Max iterations reached - request too complex
        # =========================================================================
        logger.warning("Max workflow iterations reached")
        return {
            "response": "The request was too complex to complete in one turn. Please try a more specific request.",
            "next_action": "error",
            "status": "max_iterations_reached",
            "options": None
        }


    def _format_clarification_message(self, reasoning: str = "", suggestions: list = []) -> str:
        """
        Formats a clarification message based on the LLM's understanding.
        Uses the reasoning from intent extraction to ask relevant questions.
        """
        base_message = "I understand you want to create a report, but I need a bit more clarity:\n\n"
        
        # Add the LLM's own reasoning about what was unclear
        if reasoning:
            base_message += f"**What I understood**: {reasoning}\n\n"
        
        base_message += "**Could you please clarify:**\n\n"
        
        # If the LLM provided suggestions, use them directly
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            base_message += "**Here are some common clarifications I might need:**\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                base_message += f"{i}. {suggestion}\n"
            base_message += "\n"
        
        # Add generic fallback guidance
        base_message += (
            "Or feel free to provide any additional details that would help me understand your needs better, such as:\n"
            "- Specific time periods or date ranges\n"
            "- Particular metrics or KPIs you care about\n"
            "- How you'd like the data organized or grouped\n"
            "- Any specific filters or conditions\n"
            "- Who will be using this report\n\n"
        )
        
        base_message += "**Just reply with your clarification, and I'll build the perfect report for you!**"
        
        return base_message

    def _track_tokens(self, usage):
        """Track token usage safely"""
        if usage:
            self.token_usage.input_tokens += usage.input_tokens
            self.token_usage.output_tokens += usage.output_tokens
            self.token_usage.cached_tokens += getattr(usage, 'cached_tokens', 0)

    async def _call_tool(self, tool_name: str, query: str, client_pool: Any):
        """
        Execute a tool with comprehensive error handling.
        Returns a dict or JSON string representation.
        """
        try:
            logger.info(f"Calling tool: {tool_name}")
            
            if tool_name == "extract_or_modify_intent":
                return await self.extract_or_modify_intent(query)
            elif tool_name == "extract_or_modify_kpis":
                return await self.extract_or_modify_kpis(query)
            elif tool_name == "extract_or_modify_contextual_scope":
                return await self.extract_or_modify_contextual_scope(query)
            elif tool_name == "build_or_modify_structure":
                return await self.build_or_modify_structure(query)
            elif tool_name == "build_or_modify_report":
                return await self.build_or_modify_report(query,client_pool)
            else:
                error_msg = f"Unknown tool: {tool_name}"
                logger.error(error_msg)
                return json.dumps({
                    "error": error_msg,
                    "status": "failed"
                })
        
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {str(e)}", exc_info=True)
            return json.dumps({
                "error": f"Tool {tool_name} failed: {str(e)}",
                "status": "failed",
                "tool_name": tool_name
            })

    async def run_full_pipeline(self, query: str):
        """Pipeline for automatic generation."""
        await self.extract_or_modify_intent(query)
        await self.extract_or_modify_kpis(query)
        self.agent_state.additional_details = {}
        await self.build_or_modify_structure(query)
        return await self.build_or_modify_report(query)


    async def _auto_generate_report(self, query: str) -> dict:
        """Auto-generate report with default suggestions."""
        try:
            # Step 1: Extract/Modify Intent
            if not self.agent_state.intent:
                intent_resp = await self.extract_or_modify_intent(query)
            
            # Step 2: Extract/Modify KPIs
            if not self.agent_state.kpis:
                kpi_resp = await self.extract_or_modify_kpis(query)
            
            # Step 3: Skip scope (use defaults)
            self.agent_state.additional_details = {}
            self.agent_state.completed_steps.append("extract_or_modify_contextual_scope")
            
            # Step 4: Build structure
            if not self.agent_state.structure:
                structure_resp = await self.build_or_modify_structure(query)
            
            # Step 5: Build report
            report_resp = await self.build_or_modify_report(query)
            
            return {
                "response": "Report auto-generated successfully",
                "next_action": "report_generated",
                "completed_steps": self.agent_state.completed_steps,
                "options": {}
            }
        except Exception as e:
            logger.error(f"Auto-generate report error: {str(e)}")
            return {
                "response": f"Auto-generation failed: {str(e)}",
                "error": str(e),
                "next_action": "error",
                "options": {}
            }


    def get_schema_str(self):
        schema_text_file_path = f"app/core/schema_strings/{self.dbname}.txt"
        with open(schema_text_file_path, "r", encoding="UTF-8") as f:
            self.schema_str = f.read()
        return self.schema_str
    
    def get_next_step(self):
        return 
    
    async def _get_response(self, messages):
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage.input_tokens += token_usage.input_tokens
        self.token_usage.output_tokens += token_usage.output_tokens
        self.token_usage.cached_tokens += token_usage.cached_tokens
        return results
    

    async def build_or_modify_report(self, query: str, client_pool: Any):
            """
            The final stage of the pipeline. Converts the logical structure into a 
            hydrated report with SQL, Tables, Graphs, and AI-generated Insights.
            """
            # Mark step as active
            if "build_or_modify_report" not in self.agent_state.completed_steps:
                self.agent_state.completed_steps.append("build_or_modify_report")

            # 1. VALIDATION: Ensure we have a blueprint to build from
            if not self.agent_state.structure:
                logger.error("Attempted to build report without a structure in AgentState.")
                return json.dumps({
                    "response": "I couldn't find a report structure to build. Please let me design the layout first.",
                    "status": "error",
                    "next_action": "waiting_for_approval"
                })

            logger.info(f"Building Report: {self.agent_state.structure.get('report_title')}")

            # 2. PREPARE SQL GENERATION
            sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
            schema_str = self.get_schema_str()
            
            # Deep copy structure to avoid mutating state mid-process
            report_output = json.loads(json.dumps(self.agent_state.structure)) 
            
            sql_tasks = []
            component_flat_list = []

            # Gather all components across all sections
            for section in report_output.get("sections", []):
                for comp in section.get("components", []):
                    prompt_context = {
                        "dialect": "SQL Server", # MSSQL specific
                        "schema": schema_str,
                        "examples": "", 
                        "title": comp.get("title"),
                        "descriptiion": comp.get("description", ""),
                        "bound_metrics": comp.get("bound_metrics", []),
                        "bound_dimensions": comp.get("bound_dimensions", []),
                        "bound_time_grain": comp.get("bound_time_grain", ""),
                        "filters": comp.get("applied_filters", [])
                    }
                    
                    # Create the prompt for this specific component
                    formatted_prompt = sql_prompt_template.format(**prompt_context)
                    messages = [{"role": "user", "content": formatted_prompt}]
                    
                    # Schedule SQL Generation
                    sql_tasks.append(self._get_response(messages))
                    component_flat_list.append(comp)

            # Execute all Text-to-SQL calls in parallel
            sql_results = await asyncio.gather(*sql_tasks)

            # 3. EXECUTE GENERATED SQL (Parallel Data Fetching)
            execution_tasks = []
            for i, result in enumerate(sql_results):
                sql_query = result.get("sql_query") if result else None
                component_flat_list[i]["sql_query"] = sql_query # Store SQL for transparency
                
                if sql_query:
                    # Schedule DB execution
                    # execution_tasks.append(get_table_from_sql(
                    #     pool=client_pool,
                    #     sql_query=sql_query,
                    #     row_limit=50,
                    #     query_timeout=60 
                    # ))
                    execution_tasks.append(get_table_from_sql(
                        pool=client_pool,
                        dbname=self.dbname,
                        sql_query=sql_query,
                        row_limit=50,
                        query_timeout=60 
                    ))
                else:
                    # Placeholder for components where SQL failed
                    execution_tasks.append(asyncio.sleep(0)) 

            data_results = await asyncio.gather(*execution_tasks)

            # 4. POST-PROCESSING: Tables, Graphs, and Insights
            insights_generator = ReportComponent(
                dbname=self.dbname,
                llm=self.llm,
                llm_name=self.llm_name
            )

            insight_tasks = []
            insight_task_map = {} # Tracks which insight task belongs to which component

            for i, data_resp in enumerate(data_results):
                comp = component_flat_list[i]
                
                # Initialize the output container for the UI
                comp["component_output"] = {
                    "sql": comp.get("sql_query"),
                    "table": None,
                    "table_columns": None,
                    "graph": None,
                    "graph_title": None,
                    "insights": None,
                    "status": "failed"
                }

                # If Data Fetching succeeded
                if hasattr(data_resp, 'status') and data_resp.status == "success":
                    # Convert list of tuples to list of dicts (JSON serializable)
                    table_json = [dict(zip(data_resp.columns, row)) for row in data_resp.rows]
                    comp["component_output"]["table"] = table_json
                    comp["component_output"]["table_columns"] = data_resp.columns
                    comp["component_output"]["status"] = "success"

                    # A. GENERATE GRAPHS (Only for chart types)
                    if comp.get("type") == "chart" and table_json:
                        try:
                            df = pd.DataFrame(table_json)
                            graph_maker = GraphGenerator(df)
                            graph_maker.correct_data_()
                            graphs_list = graph_maker.generate_graphs()
                            
                            comp["component_output"]["graph"] = graphs_list[:1] 
                            comp["component_output"]["graph_title"] = comp.get("title")
                        except Exception as e:
                            logger.error(f"Graph failed for {comp.get('component_id')}: {e}")

                    # B. QUEUE INSIGHTS GENERATION (For charts/insights/tables)
                    if comp.get("type") in ["insights", "chart", "table"] and table_json:
                        # Pass table to LLM for narrative summary
                        t = insights_generator.generate_insights_from_table("", table_json)
                        insight_task_map[len(insight_tasks)] = i
                        insight_tasks.append(t)

            # 5. RUN INSIGHTS IN PARALLEL
            if insight_tasks:
                logger.info(f"Generating AI Insights for {len(insight_tasks)} components...")
                insight_results = await asyncio.gather(*insight_tasks)
                for task_idx, ins_result in enumerate(insight_results):
                    comp_idx = insight_task_map[task_idx]
                    if ins_result and "summary" in ins_result:
                        component_flat_list[comp_idx]["component_output"]["insights"] = ins_result["summary"]

            # 6. FINALIZE STATE
            self.agent_state.report = report_output
            
            # Calculate summary for Orchestrator response
            success_count = sum(1 for c in component_flat_list if c["component_output"]["status"] == "success")
            
            execution_summary = []
            for c in component_flat_list:
                out = c["component_output"]
                execution_summary.append({
                    "id": c.get("component_id"),
                    "title": c.get("title"),
                    "status": out["status"],
                    "has_data": out["table"] is not None,
                    "has_graph": out["graph"] is not None
                })

            logger.info(f"Report Generation Complete. Success Rate: {success_count}/{len(component_flat_list)}")

            # 7. RETURN FINAL JSON TO ORCHESTRATOR
            return json.dumps({
                "response": f"I've successfully built the report '{report_output.get('report_title')}'. The data has been fetched and analyzed.",
                "report_title": report_output.get("report_title"),
                "total_components": len(component_flat_list),
                "successfully_populated": success_count,
                "technical_details": execution_summary,
                "status": "completed",
                "next_action": "report_generated"
            })
######################### add insights after building report
    async def add_insights_to_component(self, query: str):
        """
        Adds AI-generated insights to report components.
        
        Supports multiple targeting methods:
        - By position: "first", "second", "third", "last"
        - By type: "add insights to the kpi card", "add insights to the table"
        - By name: "add insights to Total Sell In Gross Revenue"
        - By section: "add insights to executive summary section"
        
        Examples:
        - "add insights to first kpi"
        - "add insights to second chart"
        - "add insights to Total Sell In Gross Revenue"
        - "add insights to exec_summary section"
        """
        try:
            if not self.agent_state.report:
                return json.dumps({
                    "error": "No report found to add insights to",
                    "status": "failed"
                })

            logger.info(f"Processing insights request: {query}")

            # ===== STEP 1: PARSE THE QUERY TO EXTRACT TARGET =====
            target_component, target_info = await self._identify_target_component(query)

            if not target_component:
                return json.dumps({
                    "error": f"Could not find matching component. {target_info.get('suggestion', '')}",
                    "status": "not_found",
                    "available_components": target_info.get("available_components", [])
                })

            logger.info(f"Target component identified: {target_component.get('component_id')}")

            # ===== STEP 2: EXTRACT TABLE DATA FROM COMPONENT =====
            component_output = target_component.get("component_output", {})
            table_data = component_output.get("table")

            if not table_data:
                return json.dumps({
                    "error": f"No data available in '{target_component.get('title')}' to generate insights",
                    "status": "no_data"
                })

            logger.info(f"Generating insights from {len(table_data)} rows")

            # ===== STEP 3: GENERATE INSIGHTS =====
            try:
                insights_generator = ReportComponent(
                    dbname=self.dbname,
                    llm=self.llm,
                    llm_name=self.llm_name
                )

                insights_result = await insights_generator.generate_insights_from_table(
                    insights_metadata=f"Insights for: {target_component.get('title')}",
                    table=table_data
                )

                if not insights_result or "summary" not in insights_result:
                    return json.dumps({
                        "error": "Failed to generate insights from data",
                        "status": "failed"
                    })

                insights_html = insights_result["summary"]

                # ===== STEP 4: UPDATE COMPONENT IN REPORT =====
                target_component["component_output"]["insights"] = insights_html
                
                logger.info(f"Insights added to {target_component.get('component_id')}")

                return json.dumps({
                    "response": f"I've added detailed insights to '{target_component.get('title')}'. The analysis reveals key trends and performance metrics.",
                    "component_id": target_component.get("component_id"),
                    "component_title": target_component.get("title"),
                    "component_type": target_component.get("type"),
                    "insights_preview": insights_html[:150] + "...",
                    "status": "success"
                })

            except Exception as e:
                logger.error(f"Error generating insights: {str(e)}", exc_info=True)
                return json.dumps({
                    "error": f"Failed to generate insights: {str(e)}",
                    "status": "failed"
                })

        except Exception as e:
            logger.error(f"Error in add_insights_to_component: {str(e)}", exc_info=True)
            return json.dumps({
                "error": f"Unexpected error: {str(e)}",
                "status": "failed"
            })


    async def _identify_target_component(self, query: str) -> tuple:
        """
        Intelligently identify which component the user is referring to.
        
        Returns: (target_component_dict, info_dict)
        """
        query_lower = query.lower()
        
        # Flatten all components from all sections
        all_components = []
        for section in self.agent_state.report.get("sections", []):
            for comp in section.get("components", []):
                all_components.append({
                    "component": comp,
                    "section_id": section.get("section_id"),
                    "section_heading": section.get("heading")
                })

        if not all_components:
            return None, {"suggestion": "No components found in report."}

        # ===== METHOD 1: POSITIONAL REFERENCE (first, second, third, last) =====
        position_keywords = {
            "first": 0,
            "second": 1,
            "third": 2,
            "fourth": 3,
            "fifth": 4,
            "last": -1,
            "previous": -1
        }

        for keyword, index in position_keywords.items():
            if keyword in query_lower:
                # Filter by type if specified
                component_type = self._extract_type_from_query(query_lower)
                
                if component_type:
                    # Filter by type first
                    filtered = [c["component"] for c in all_components 
                            if c["component"].get("type") == component_type]
                    if filtered and len(filtered) > index:
                        return filtered[index], {"method": "positional", "keyword": keyword}
                else:
                    # Just use position
                    if len(all_components) > index:
                        return all_components[index]["component"], {"method": "positional", "keyword": keyword}

        # ===== METHOD 2: TYPE-BASED REFERENCE (kpi card, chart, table) =====
        type_keywords = {
            "kpi": "kpi_card",
            "chart": "chart",
            "table": "table",
            "card": "kpi_card",
            "graph": "chart"
        }

        for keyword, comp_type in type_keywords.items():
            if keyword in query_lower:
                matching = [c["component"] for c in all_components 
                        if c["component"].get("type") == comp_type]
                if matching:
                    # If "first kpi card" → return first; if "add insights to table" → return first table
                    position = self._extract_position_from_query(query_lower)
                    if position is not None and position < len(matching):
                        return matching[position], {"method": "type_based", "type": comp_type}
                    elif matching:
                        return matching[0], {"method": "type_based", "type": comp_type}

        # ===== METHOD 3: NAME/TITLE REFERENCE (exact or fuzzy match) =====
        for comp_info in all_components:
            comp = comp_info["component"]
            title = comp.get("title", "").lower()
            
            # Check for exact component_id match
            if comp.get("component_id").lower() in query_lower:
                return comp, {"method": "name_based", "match_type": "component_id"}
            
            # Check for title keyword match
            title_words = title.split()
            query_words = query_lower.split()
            
            matches = sum(1 for word in title_words if word in query_words)
            if matches >= 2:  # At least 2 words match
                return comp, {"method": "name_based", "match_type": "title"}

        # ===== METHOD 4: SECTION REFERENCE =====
        for section in self.agent_state.report.get("sections", []):
            section_id = section.get("section_id", "").lower()
            section_heading = section.get("heading", "").lower()
            
            if section_id in query_lower or section_heading in query_lower:
                components = section.get("components", [])
                if components:
                    # If "executive summary", return first component of that section
                    kpi_cards = [c for c in components if c.get("type") == "kpi_card"]
                    if kpi_cards:
                        return kpi_cards[0], {"method": "section_based", "section": section_heading}
                    else:
                        return components[0], {"method": "section_based", "section": section_heading}

        # ===== NO MATCH FOUND: RETURN HELPFUL INFO =====
        component_list = [
            f"{i+1}. {c['component'].get('title')} ({c['component'].get('type')}) - Section: {c['section_heading']}"
            for i, c in enumerate(all_components)
        ]

        return None, {
            "suggestion": "Please specify which component to add insights to. Use 'first', 'second', etc., or the component name.",
            "available_components": component_list
        }


    def _extract_type_from_query(self, query_lower: str) -> str:
        """Extract component type from query (kpi_card, chart, table)"""
        type_map = {
            "kpi": "kpi_card",
            "card": "kpi_card",
            "chart": "chart",
            "graph": "chart",
            "table": "table"
        }
        
        for keyword, comp_type in type_map.items():
            if keyword in query_lower:
                return comp_type
        return None


    def _extract_position_from_query(self, query_lower: str) -> int:
        """Extract position number from query (first=0, second=1, etc.)"""
        positions = {
            "first": 0, "1st": 0,
            "second": 1, "2nd": 1,
            "third": 2, "3rd": 2,
            "fourth": 3, "4th": 3,
            "fifth": 4, "5th": 4
        }
        
        for keyword, index in positions.items():
            if keyword in query_lower:
                return index
        return None