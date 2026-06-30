from app.core.llms import get_llm_response, TokenUsage, get_llm_response_with_tool
from app.core.prompts import PromptGetter
from app.logger import get_logger
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional, Any
from app.models import ReportSelectable
import json
import asyncio
from app.core.table_from_sql import get_table_from_sql_parallel, get_table_from_sql
from app.databases.connections import client_connection_pool 
from app.core.table_from_sql import get_table_from_sql
from app.core.graphs.echarts.graphs import GraphGenerator
from app.logger import get_logger

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

    # async def generate_storyboard(self, context: str):
    #     """Step 3: Generate a logical story of report components"""
    #     sys_prompt = self.prompt_getter.get_prompt("report_builder_step3_storyboard").format(
    #         schema=self.get_schema_str(),
    #         context=context,
    #         # We pass kpis specifically to help the prompt fill descriptions
    #         kpis=context 
    #     )
    #     messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Generate the storyboard recommendations."}]
    #     return await self._get_response(messages)

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
    report: Optional[List[str]] = None
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
            agent_state: AgentState
        ) -> None:
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
        self.agent_state = agent_state


    async def workflow_agent(self, query: str, chat_history: list = []) -> str | None:
        """
        Given a user query it will first determine the step to be executed and as a result
        
        :param query: Description
        :type query: str
        :return: Description
        :rtype: str
        """
        sys_prompt = self.prompt_getter.get_prompt("workflow_system_prompt")
        current_state = {
            "build_type": self.agent_state.build_type,
            "intent": self.agent_state.intent,
            "kpis": self.agent_state.kpis,
            "contextual_scope": self.agent_state.additional_details,
            "structure": self.agent_state.structure,
            "report": self.agent_state.report,
            "completed_stsps": self.agent_state.completed_steps
        }      
        sys_prompt = sys_prompt.format(current_state = self.agent_state)
        messages = [{"role": "user", "content": sys_prompt}]
        
        if chat_history:
            messages.extend(chat_history)

        messages += [{"role": "user", "content": query}]

        response, token_usage = await get_llm_response_with_tool(self.llm, self.llm_name, messages, tools)

        self.token_usage.input_tokens += token_usage.input_tokens
        self.token_usage.output_tokens += token_usage.output_tokens
        self.token_usage.cached_tokens += token_usage.cached_tokens
        
        if not response:
            logger.error("NOT ABLE TO GENERATE ANY RESPONSE")
            return None
        
        if response.output[0].type == "message":  # if the output is just a message
            return json.loads(response.output_text)

        # case of tool calll
        messages += response.output     # appending the output of workflow orchestrator to messages
        
        for item in response.output: # will only run if output is resulte din tool call
            if item.type == "function_call":
                if item.name == "extract_or_modify_intent":
                    tool_resp = await self.extract_or_modify_intent(query)                    
                    messages.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": tool_resp
                    })
                if item.name == "extract_or_modify_kpis":
                    tool_resp = await self.extract_or_modify_kpis(query)                    
                    messages.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": tool_resp
                    })
                if item.name == "extract_or_modify_contextual_scope":
                    tool_resp = await self.extract_or_modify_contextual_scope(query)                    
                    messages.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": tool_resp
                    })
                if item.name == "build_or_modify_structure":
                    tool_resp = await self.build_or_modify_structure(query)                    
                    messages.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": tool_resp
                    })
                if item.name == "build_or_modify_report":
                    tool_resp = await self.build_or_modify_report(query)                    
                    messages.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": tool_resp
                    })

        print("#############################")
        print(messages[-1])
        print("#############################")

        response, token_usage = await get_llm_response_with_tool(self.llm, self.llm_name, messages, tools) 

        self.token_usage.input_tokens += token_usage.input_tokens
        self.token_usage.output_tokens += token_usage.output_tokens
        self.token_usage.cached_tokens += token_usage.cached_tokens

        if not response:
            logger.error("NOT ABLE TO GENERATE ANY RESPONSE")
            return None
        
        if response.output[0].type == "functon_call":
            logger.error("Result of conseuquent tools calls")
            return None
        
        return json.loads(response.output_text)


    async def extract_or_modify_intent(self, query: str) -> str:
        self.agent_state.completed_steps = []
        sys_prompt = self.prompt_getter.get_prompt("workflow_intent_identification_prompt")
        sys_prompt = sys_prompt.format(schema=self.get_schema_str(), current_intent = self.agent_state.intent) 
        messages = [{"role": "user", "content": sys_prompt}]

        self.agent_state.intent_messages += [{"role": "user", "content": query}]

        messages += self.agent_state.intent_messages

        print("######## INTENT MESSAGES ########")
        print(self.agent_state.intent_messages)
        print("######## / INTENT MESSAGES ########")
        
        for m in messages:
            if isinstance(m["content"], dict):
                m["content"] = json.dumps(m["content"])

        resp = await self._get_response(messages)
        self.agent_state.intent_messages += [{"role": "assistant", "content": resp}]
        
        self.agent_state.intent = resp["intent"]
        self.agent_state.build_type = resp["build_type"]

        if resp["case"].upper() == "CASE_1" and self.agent_state.initial_query==None:
            self.agent_state.initial_query = query

        return json.dumps(resp)
    

    async def extract_or_modify_kpis(self, query: str) -> str:
        self.agent_state.completed_steps = ["extract_or_modify_intent"]

        sys_prompt = self.prompt_getter.get_prompt("workflow_kpi_prompt")
        sys_prompt = sys_prompt.format(
            schema=self.get_schema_str(), 
            intent = self.agent_state.intent,
            current_kpis = self.agent_state.kpis
        ) 
        messages = [{"role": "user", "content": sys_prompt}]

        self.agent_state.kpi_messages += [{"role": "user", "content": query}]

        messages += self.agent_state.kpi_messages

        print("######## KPI MESSAGES ########")
        print(self.agent_state.kpi_messages)
        print("######## / KPI MESSAGES ########")
        
        for m in messages:
            if isinstance(m["content"], dict):
                m["content"] = json.dumps(m["content"])

        resp = await self._get_response(messages)
        self.agent_state.kpi_messages += [{"role": "assistant", "content": resp}]
        
        self.agent_state.kpis = resp["kpis"]
        return json.dumps(resp)

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


    # async def build_or_modify_report(self, query: str):
    #     self.agent_state.completed_steps = ["extract_or_modify_intent", "extract_or_modify_kpis", "extract_or_modify_contextual_scope", "build_or_modify_structure"]
        

    #     # sys_prompt = self.prompt_getter.get_prompt("workflow_report_prompt")
    #     # sys_prompt = sys_prompt.format(
    #     #     schema=self.get_schema_str(), 
    #     #     intent = self.agent_state.intent,
    #     #     current_kpis = self.agent_state.kpis
    #     # ) 
    #     # messages = [{"role": "user", "content": sys_prompt}]

    #     # self.agent_state.kpi_messages += [{"role": "user", "content": query}]

    #     # messages += self.agent_state.kpi_messages

    #     # print("######## KPI MESSAGES ########")
    #     # print(self.agent_state.kpi_messages)
    #     # print("######## / KPI MESSAGES ########")
        
    #     # for m in messages:
    #     #     if isinstance(m["content"], dict):
    #     #         m["content"] = json.dumps(m["content"])

    #     # resp = await self._get_response(messages)
    #     # self.agent_state.kpi_messages += [{"role": "assistant", "content": resp}]
        
    #     # self.agent_state.kpis = resp["kpis"]
    #     # return json.dumps(resp)
    
    # async def build_or_modify_report(self, query: str):
    #     self.agent_state.completed_steps = [
    #         "extract_or_modify_intent", 
    #         "extract_or_modify_kpis", 
    #         "extract_or_modify_contextual_scope", 
    #         "build_or_modify_structure"
    #     ]

    #     if not self.agent_state.structure:
    #         return json.dumps({
    #             "response": "I couldn't find a report structure to build. Please define the structure first.",
    #             "status": "error"
    #         })

    #     # Prepare the SQL Generation Prompt
    #     sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
    #     schema_str = self.get_schema_str()
        
    #     # We will iterate through all sections and components to generate SQL
    #     # Using a copy of the structure to populate with SQL
    #     report_output = json.loads(json.dumps(self.agent_state.structure)) 
        
    #     sql_tasks = []
    #     component_refs = []

    #     # Gather all components that need SQL generation
    #     for section in report_output.get("sections", []):
    #         for component in section.get("components", []):
    #             # Prepare context for the Text-to-SQL prompt
    #             prompt_context = {
    #                 "dialect": "mssql", 
    #                 "schema": schema_str,
    #                 "examples": "",
    #                 "title": component.get("title"),
    #                 "descriptiion": component.get("description"),
    #                 "bound_metrics": component.get("bound_metrics"),
    #                 "bound_dimensions": component.get("bound_dimensions"),
    #                 "bound_time_grain": component.get("bound_time_grain"),
    #                 "filters": component.get("applied_filters")
    #             }
                
    #             formatted_sql_prompt = sql_prompt_template.format(**prompt_context)
                
    #             # We use the internal _get_response or a direct LLM call
    #             messages = [{"role": "user", "content": formatted_sql_prompt}]
    #             sql_tasks.append(self._get_response(messages))
    #             component_refs.append(component)

    #     # Execute SQL generation in parallel for performance
    #     sql_results = await asyncio.gather(*sql_tasks)

    #     # Assign generated SQL back to the components
    #     for i, result in enumerate(sql_results):
    #         # result is the dict returned by _get_response
    #         if result and "sql_query" in result:
    #             component_refs[i]["sql_query"] = result["sql_query"]
    #         else:
    #             component_refs[i]["sql_query"] = None
    #             logger.error(f"Failed to generate SQL for component: {component_refs[i].get('title')}")

    #     # Update the agent state with the full report (Structure + SQL)
    #     self.agent_state.report = report_output
        
    #     # Append to report messages for history
    #     self.agent_state.report_messages += [
    #         {"role": "user", "content": query},
    #         {"role": "assistant", "content": "The report has been successfully generated based on the defined structure."}
    #     ]

    #     # Return a friendly confirmation to the user
    #     return json.dumps({
    #         "response": "I have successfully generated the report and the underlying data queries. You can now preview the final dashboard.",
    #         "report_title": report_output.get("report_title"),
    #         "status": "completed"
    #     })


############ working as expected ##############
    # async def build_or_modify_report(self, query: str):
    #     self.agent_state.completed_steps = [
    #         "extract_or_modify_intent", 
    #         "extract_or_modify_kpis", 
    #         "extract_or_modify_contextual_scope", 
    #         "build_or_modify_structure"
    #     ]

    #     if not self.agent_state.structure:
    #         return json.dumps({"response": "No report structure found. Please define the layout first.", "status": "error"})

    #     # 1. GENERATE SQL QUERIES
    #     sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
    #     schema_str = self.get_schema_str()
    #     report_data_structure = json.loads(json.dumps(self.agent_state.structure)) 
        
    #     sql_tasks = []
    #     component_list = []
    #     for section in report_data_structure.get("sections", []):
    #         for comp in section.get("components", []):
    #             prompt_context = {
    #                 "dialect": "mssql", 
    #                 "schema": schema_str,
    #                 "examples": "", 
    #                 "title": comp.get("title"),
    #                 "descriptiion": comp.get("description"),
    #                 "bound_metrics": comp.get("bound_metrics"),
    #                 "bound_dimensions": comp.get("bound_dimensions"),
    #                 "bound_time_grain": comp.get("bound_time_grain"),
    #                 "filters": comp.get("applied_filters")
    #             }
    #             messages = [{"role": "user", "content": sql_prompt_template.format(**prompt_context)}]
    #             sql_tasks.append(self._get_response(messages))
    #             component_list.append(comp)

    #     sql_results = await asyncio.gather(*sql_tasks)

    #     # 2. EXECUTE SQL QUERIES (Parallel)
    #     execution_tasks = []
    #     executed_components = []
        
    #     # client_connection_pool IS the pool object, no need to call .get()
    #     pool = client_connection_pool 

    #     for i, result in enumerate(sql_results):
    #         if result and "sql_query" in result:
    #             query_str = result["sql_query"]
    #             component_list[i]["sql_query"] = query_str 
                
    #             # Pass the pool object directly
    #             execution_tasks.append(get_table_from_sql(
    #                 pool=pool,
    #                 sql_query=query_str,
    #                 row_limit=20,
    #                 query_timeout=60
    #             ))
    #             executed_components.append(component_list[i])

    #     # Execute all queries at once
    #     data_results = await asyncio.gather(*execution_tasks)

    #     # 3. ASSIGN DATA (QueryResult is an object)
    #     for i, data_resp in enumerate(data_results):
    #         # Check the status attribute of the QueryResult object
    #         if data_resp.status == "success":
    #             executed_components[i]["data"] = data_resp.rows
    #             executed_components[i]["columns"] = data_resp.columns
    #         else:
    #             executed_components[i]["data"] = []
    #             # Log the specific error for debugging
    #             logger.error(f"SQL execution failed: {data_resp.status} - {getattr(data_resp, 'error', 'Unknown Error')}")
    #             executed_components[i]["error"] = data_resp.status

    #     # 4. SAVE TO STATE AND RETURN CLEAN RESPONSE
    #     self.agent_state.report = report_data_structure
        
    #     return json.dumps({
    #         "response": "The report has been successfully generated and populated with data. The dashboard is now ready for review.",
    #         "status": "completed"
    #     })

#################################################################
    # async def build_or_modify_report(self, query: str):
    #     self.agent_state.completed_steps = [
    #         "extract_or_modify_intent", 
    #         "extract_or_modify_kpis", 
    #         "extract_or_modify_contextual_scope", 
    #         "build_or_modify_structure"
    #     ]

    #     if not self.agent_state.structure:
    #         return json.dumps({"response": "No structure found.", "status": "error"})

    #     # 1. GENERATE SQL (MSSQL Dialect)
    #     sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
    #     schema_str = self.get_schema_str()
    #     report_data_structure = json.loads(json.dumps(self.agent_state.structure)) 
        
    #     sql_tasks = []
    #     component_list = []
    #     for section in report_data_structure.get("sections", []):
    #         for comp in section.get("components", []):
    #             prompt_context = {
    #                 "dialect": "SQL Server",
    #                 "schema": schema_str,
    #                 "examples": "", 
    #                 "title": comp.get("title"),
    #                 "descriptiion": comp.get("description"),
    #                 "bound_metrics": comp.get("bound_metrics"),
    #                 "bound_dimensions": comp.get("bound_dimensions"),
    #                 "bound_time_grain": comp.get("bound_time_grain"),
    #                 "filters": comp.get("applied_filters")
    #             }
    #             messages = [{"role": "user", "content": sql_prompt_template.format(**prompt_context)}]
    #             sql_tasks.append(self._get_response(messages))
    #             component_list.append(comp)

    #     sql_results = await asyncio.gather(*sql_tasks)

    #     # 2. EXECUTE SQL
    #     execution_tasks = []
    #     executed_components = []
    #     pool = client_connection_pool 

    #     for i, result in enumerate(sql_results):
    #         if result and "sql_query" in result:
    #             query_str = result["sql_query"]
    #             component_list[i]["sql_query"] = query_str 
                
    #             execution_tasks.append(get_table_from_sql(
    #                 pool=pool,
    #                 sql_query=query_str,
    #                 row_limit=20,
    #                 query_timeout=60 
    #             ))
    #             executed_components.append(component_list[i])

    #     data_results = await asyncio.gather(*execution_tasks)

    #     # 3. ASSIGN DATA AND COLLECT TECHNICAL METADATA FOR THE AGENT
    #     execution_summary = []
    #     success_count = 0

    #     for i, data_resp in enumerate(data_results):
    #         comp = executed_components[i]
            
    #         # Metadata we want the Agent to know about
    #         comp_info = {
    #             "component_id": comp.get("component_id"),
    #             "title": comp.get("title"),
    #             "status": data_resp.status,
    #             "row_count": 0,
    #             "columns": []
    #         }

    #         if data_resp.status == "success":
    #             comp["data"] = data_resp.rows
    #             comp["columns"] = data_resp.columns
                
    #             # Populate metadata
    #             comp_info["row_count"] = len(data_resp.rows)
    #             comp_info["columns"] = data_resp.columns
    #             success_count += 1
    #         else:
    #             comp["data"] = []
    #             comp["error"] = data_resp.status
            
    #         execution_summary.append(comp_info)

    #     # 4. UPDATE STATE (Save the heavy data to the DB)
    #     self.agent_state.report = report_data_structure
        
    #     # 5. RETURN TECHNICAL SUMMARY TO THE AGENT
    #     # The agent uses this JSON block to generate its text response.
    #     report_status = "Successfully Generated" if success_count == len(executed_components) else "Partially Generated"
        
    #     return json.dumps({
    #         "response": {
    #             "message": f"Report building process finished with status: {report_status}.",
    #             "report_title": report_data_structure.get("report_title"),
    #             "total_components": len(executed_components),
    #             "successfully_populated": success_count,
    #             "component_details": execution_summary # The Agent sees IDs, row counts, and columns here
    #         },
    #         # "options": ["View Dashboard", "Download PDF", "Modify Filters"],
    #         "status": "completed"
    #     })

####################################### working without insights #########

    # async def build_or_modify_report(self, query: str):
    #     self.agent_state.completed_steps = [
    #         "extract_or_modify_intent", "extract_or_modify_kpis", 
    #         "extract_or_modify_contextual_scope", "build_or_modify_structure"
    #     ]

    #     if not self.agent_state.structure:
    #         return json.dumps({"response": "No structure found.", "status": "error"})

    #     # 1. SQL GENERATION (Parallel)
    #     sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
    #     schema_str = self.get_schema_str()
    #     report_data_structure = json.loads(json.dumps(self.agent_state.structure)) 
        
    #     sql_tasks = []
    #     component_list = []
    #     for section in report_data_structure.get("sections", []):
    #         for comp in section.get("components", []):
    #             prompt_context = {
    #                 "dialect": "SQL Server",
    #                 "schema": schema_str,
    #                 "examples": "", 
    #                 "title": comp.get("title"),
    #                 "descriptiion": comp.get("description"),
    #                 "bound_metrics": comp.get("bound_metrics"),
    #                 "bound_dimensions": comp.get("bound_dimensions"),
    #                 "bound_time_grain": comp.get("bound_time_grain"),
    #                 "filters": comp.get("applied_filters")
    #             }
    #             messages = [{"role": "user", "content": sql_prompt_template.format(**prompt_context)}]
    #             sql_tasks.append(self._get_response(messages))
    #             component_list.append(comp)

    #     sql_results = await asyncio.gather(*sql_tasks)

    #     # 2. DATA EXECUTION (Parallel)
    #     execution_tasks = []
    #     for i, result in enumerate(sql_results):
    #         query_str = result.get("sql_query") if result else None
    #         component_list[i]["sql_query"] = query_str
    #         if query_str:
    #             execution_tasks.append(get_table_from_sql(
    #                 pool=client_connection_pool,
    #                 sql_query=query_str,
    #                 row_limit=20,
    #                 query_timeout=60
    #             ))
    #         else:
    #             execution_tasks.append(asyncio.sleep(0)) # Placeholder for failed SQL

    #     data_results = await asyncio.gather(*execution_tasks)

    #     # 3. POST-PROCESSING (Graphs & Insights)
    #     # We collect insight tasks to run them in parallel at the end
    #     insight_tasks = []
    #     insight_task_map = {} # Maps task index to component index

    #     for i, data_resp in enumerate(data_results):
    #         comp = component_list[i]
            
    #         # Initialize component_output with defaults
    #         comp["component_output"] = {
    #             "sql": comp.get("sql_query"),
    #             "table": None,
    #             "table_columns": None,
    #             "graph": None,
    #             "graph_title": None,
    #             "insights": None
    #         }

    #         # If SQL succeeded, process Table and Graphs
    #         if hasattr(data_resp, 'status') and data_resp.status == "success":
    #             # Convert tuples to List[Dict] (JSON format)
    #             table_json = [dict(zip(data_resp.columns, row)) for row in data_resp.rows]
    #             comp["component_output"]["table"] = table_json
    #             comp["component_output"]["table_columns"] = data_resp.columns

    #             # GENERATE GRAPHS (if component is a chart)
    #             if comp.get("type") == "chart" and table_json:
    #                 try:
    #                     df = pd.DataFrame(table_json)
    #                     graph_maker = GraphGenerator(df)
    #                     graph_maker.correct_data_()
    #                     graphs_list = graph_maker.generate_graphs()
                        
    #                     comp["component_output"]["graph"] = graphs_list[:1] # Take primary graph
    #                     comp["component_output"]["graph_title"] = comp.get("title")
    #                 except Exception as e:
    #                     logger.error(f"Graph generation failed for {comp.get('component_id')}: {e}")

    #             # PREPARE INSIGHTS TASKS (if component is insights or chart)
    #             if comp.get("type") in ["insights", "chart"] and table_json:
    #                 # We add to parallel tasks to avoid sequential LLM calls
    #                 t = self.generate_insights_from_table("", table_json)
    #                 insight_task_map[len(insight_tasks)] = i
    #                 insight_tasks.append(t)

    #     # Run all Insight LLM calls in parallel
    #     if insight_tasks:
    #         insight_results = await asyncio.gather(*insight_tasks)
    #         for task_idx, result in enumerate(insight_results):
    #             comp_idx = insight_task_map[task_idx]
    #             if result and "summary" in result:
    #                 component_list[comp_idx]["component_output"]["insights"] = result["summary"]

    #     # 4. FINAL STATE SYNC
    #     self.agent_state.report = report_data_structure
        
    #     # Calculate success for the agent response
    #     success_count = sum(1 for c in component_list if c["component_output"]["table"] is not None)
        
    #     execution_summary = []
    #     for c in component_list:
    #         out = c["component_output"]
    #         execution_summary.append({
    #             "component_id": c.get("component_id"),
    #             "title": c.get("title"),
    #             "rows": len(out["table"]) if out["table"] else 0,
    #             "has_graph": out["graph"] is not None,
    #             "has_insights": out["insights"] is not None
    #         })

    #     return json.dumps({
    #         "response": {
    #             "message": f"Report '{report_data_structure.get('report_title')}' generated.",
    #             "total_components": len(component_list),
    #             "success_count": success_count,
    #             "details": execution_summary
    #         },
    #         "options": ["View Dashboard", "Export Excel"],
    #         "status": "completed"
    #     })


#########################
    async def build_or_modify_report(self, query: str):
        """
        Generates SQL, executes data fetching, generates graphs, 
        and produces insights for all components in the report structure.
        """
        self.agent_state.completed_steps = [
            "extract_or_modify_intent", 
            "extract_or_modify_kpis", 
            "extract_or_modify_contextual_scope", 
            "build_or_modify_structure"
        ]

        if not self.agent_state.structure:
            return json.dumps({
                "response": "I couldn't find a report structure to build. Please define the layout first.",
                "status": "error"
            })

        # --- STEP 1: GENERATE SQL QUERIES (Parallel) ---
        sql_prompt_template = self.prompt_getter.get_prompt("workflow_text_2_sql_prompt")
        schema_str = self.get_schema_str()
        
        # Deep copy the structure to populate it with data
        report_data_structure = json.loads(json.dumps(self.agent_state.structure)) 
        
        sql_tasks = []
        component_list = []

        for section in report_data_structure.get("sections", []):
            for comp in section.get("components", []):
                prompt_context = {
                    "dialect": "SQL Server", # Ensuring MSSQL Dialect
                    "schema": schema_str,
                    "examples": "", 
                    "title": comp.get("title"),
                    "descriptiion": comp.get("description"), # Matching your prompt key
                    "bound_metrics": comp.get("bound_metrics"),
                    "bound_dimensions": comp.get("bound_dimensions"),
                    "bound_time_grain": comp.get("bound_time_grain"),
                    "filters": comp.get("applied_filters")
                }
                
                formatted_prompt = sql_prompt_template.format(**prompt_context)
                messages = [{"role": "user", "content": formatted_prompt}]
                
                sql_tasks.append(self._get_response(messages))
                component_list.append(comp)

        # Generate all SQL queries in parallel
        sql_results = await asyncio.gather(*sql_tasks)

        # --- STEP 2: EXECUTE SQL QUERIES (Parallel) ---
        execution_tasks = []
        pool = client_connection_pool # Uses the AioODBCPool instance

        for i, result in enumerate(sql_results):
            query_str = result.get("sql_query") if result else None
            component_list[i]["sql_query"] = query_str
            
            if query_str:
                execution_tasks.append(get_table_from_sql(
                    pool=pool,
                    sql_query=query_str,
                    row_limit=20,
                    query_timeout=60 
                ))
            else:
                # Append a dummy task for components that failed SQL generation
                execution_tasks.append(asyncio.sleep(0)) 

        data_results = await asyncio.gather(*execution_tasks)

        # --- STEP 3: POST-PROCESSING (Graphs & Insights) ---
        # Initialize ReportComponent for insights as per your reference code
        insights_generator = ReportComponent(
            dbname=self.dbname,
            llm=self.llm,
            llm_name=self.llm_name
        )

        insight_tasks = []
        insight_task_map = {} # Maps insight task index back to component_list index

        for i, data_resp in enumerate(data_results):
            comp = component_list[i]
            sql_used = comp.get("sql_query")
            
            # Initialize component_output key structure
            comp["component_output"] = {
                "sql": sql_used,
                "table": None,
                "table_columns": None,
                "graph": None,
                "graph_title": None,
                "insights": None
            }

            # If the database execution was successful
            if hasattr(data_resp, 'status') and data_resp.status == "success":
                # Convert tuples to List of Dicts (table_json)
                table_json = [dict(zip(data_resp.columns, row)) for row in data_resp.rows]
                comp["component_output"]["table"] = table_json
                comp["component_output"]["table_columns"] = data_resp.columns

                # A. GENERATE GRAPHS (Only for 'chart' types)
                if comp.get("type") == "chart" and table_json:
                    try:
                        df = pd.DataFrame(table_json)
                        graph_maker = GraphGenerator(df)
                        graph_maker.correct_data_()
                        graphs_list = graph_maker.generate_graphs()
                        
                        comp["component_output"]["graph"] = graphs_list[:1] # Take the primary graph
                        comp["component_output"]["graph_title"] = comp.get("title")
                    except Exception as e:
                        logger.error(f"Graph generation failed for {comp.get('component_id')}: {e}")

                # B. PREPARE INSIGHTS TASKS (For 'insights' or 'chart' types)
                if comp.get("type") in ["insights", "chart"] and table_json:
                    # Pass empty metadata string and the table data
                    t = insights_generator.generate_insights_from_table("", table_json)
                    insight_task_map[len(insight_tasks)] = i
                    insight_tasks.append(t)

        # Run all Insight LLM calls in parallel
        if insight_tasks:
            insight_results = await asyncio.gather(*insight_tasks)
            for task_idx, ins_result in enumerate(insight_results):
                comp_idx = insight_task_map[task_idx]
                if ins_result and "summary" in ins_result:
                    component_list[comp_idx]["component_output"]["insights"] = ins_result["summary"]

        # --- STEP 4: STATE SYNC & TECHNICAL SUMMARY ---
        # Update the final agent state with the hydrated report (SQL + Data + Graphs + Insights)
        self.agent_state.report = report_data_structure
        
        # Prepare a technical summary so the Agent can generate a clear text response
        success_count = sum(1 for c in component_list if c["component_output"]["table"] is not None)
        
        execution_summary = []
        for c in component_list:
            out = c["component_output"]
            execution_summary.append({
                "component_id": c.get("component_id"),
                "title": c.get("title"),
                "status": "Success" if out["table"] is not None else "Failed/Timeout",
                "row_count": len(out["table"]) if out["table"] else 0,
                "graph_generated": out["graph"] is not None,
                "insights_generated": out["insights"] is not None
            })

        return json.dumps({
            "response": {
                "message": f"Report building completed for '{report_data_structure.get('report_title')}'.",
                "total_components": len(component_list),
                "successfully_populated": success_count,
                "technical_details": execution_summary
            },
            # "options": ["View Dashboard", "Export to PDF", "Modify Filters"],
            "status": "completed"
        })



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
    
