import json
from app.core.helper import get_system_prompt
from app.logger import get_logger
from app.core.llms import TokenUsage, get_llm_response_with_tool_basic
from functools import partial
from .tools import (
    get_distinct_values_for_column_of_table, 
    check_value_existence_in_column, 
    get_value_range_for_column,
    get_column_metadata_for_table,
    get_similar_values_for_column,
    tools as fallback_tools
)
from .helper import parse_where_clause_filters


logger = get_logger(__name__)


MAX_ITERATIONS = 10


USER_MESSAGE = """
Please investigate why and provide a helpful explanation with alternatives.
 
---
USER'S ORIGINAL QUESTION:
{user_query}
 
GENERATED SQL (returned 0 rows):
{sql_query}
 
TABLES INVOLVED:
{tables_display}
 
EXTRACTED WHERE CLAUSE FILTERS:
{filters_display}
---
 
Please investigate each filter and explain what went wrong and what the user can try instead.
"""
   
    
class FallbackHandler:
    def __init__(self, dbname: str, llm, llm_name, client_pool):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.client_pool = client_pool

        self.token_usage = TokenUsage()

        self.get_distinct = partial(get_distinct_values_for_column_of_table, dbname, client_pool)
        self.check_existence = partial(check_value_existence_in_column, dbname, client_pool)
        self.get_value_range = partial(get_value_range_for_column, dbname, client_pool)
        self.get_column_metadata = partial(get_column_metadata_for_table, dbname)
        self.get_similar_values = partial(get_similar_values_for_column, dbname, client_pool)

        self.messages = []
    
    
    def get_where_clause_filters(self, sql_query: str, dialect: str = "mssql"):
        if dialect == "mssql":
            new_dialect = "tsql"
        else:
            new_dialect = dialect
        return parse_where_clause_filters(sql_query, new_dialect)


    async def get_tool_response(self, tool_name: str, dialect: str, tool_inputs: dict):
        print(tool_name)
        try:
            if tool_name == "get_distinct_values_for_column_of_table":
                return await self.get_distinct(dialect=dialect, **tool_inputs)
            elif tool_name == "check_value_existence_in_column":
                return await self.check_existence(dialect=dialect, **tool_inputs)
            elif tool_name == "get_value_range_for_column":
                return await self.get_value_range(dialect=dialect, **tool_inputs)
            elif tool_name == "get_column_metadata_for_table":
                return await self.get_column_metadata(**tool_inputs)
            elif tool_name == "get_similar_values_for_column":
                return await self.get_similar_values(dialect=dialect, **tool_inputs)
            else:
                logger.error(f"Unknown tool requested: {tool_name}")
                return {
                    "status": "error",
                    "message": f"Unknown tool requested: {tool_name}",
                    "response": None
                }
        except Exception as e:
             logger.error(f"Error executing tool {tool_name} with inputs {tool_inputs}: {e}")
             return {
                 "status": "error",
                 "message": f"Error executing tool {tool_name}: {str(e)}",
                 "response": None
             }
    
    
    async def run(self, user_query: str, filters: str, sql_query: str | None = None, dialect: str = "mssql"):
        where_clause_context = self.get_where_clause_filters(sql_query, dialect=dialect) if sql_query else None

        where_clause_filters = where_clause_context["filters"] if where_clause_context else None
        where_clause_tables = where_clause_context["tables"] if where_clause_context else None

        system_prompt = get_system_prompt(self.dbname, "fallback_handler")

        user_message = USER_MESSAGE.format(
            user_query=user_query,
            sql_query=sql_query or "N/A",
            tables_display=", ".join(where_clause_tables) if where_clause_tables else "N/A",
            filters_display=json.dumps(where_clause_filters, indent=2) if where_clause_filters else "N/A"
        )

        logger.info(
            f"Starting fallback agent | db={self.dbname} | "
            f"filters={len(where_clause_filters) if where_clause_filters else 0} | "
            f"tables={where_clause_tables if where_clause_tables else []}"
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": user_message})

        for i in range(MAX_ITERATIONS):
            response, token_usage = await get_llm_response_with_tool_basic(
                self.llm, self.llm_name, messages, fallback_tools
            )
            self.token_usage += token_usage
            
            assistant_message = response.choices[0].message
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ] if assistant_message.tool_calls else None,
                }
            )

            if response.choices[0].finish_reason == "tool_calls":
                for tc in response.choices[0].message.tool_calls:
                    tool_resp = await self.get_tool_response(
                        tool_name=tc.function.name, 
                        dialect=dialect,
                        tool_inputs=json.loads(tc.function.arguments),
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,   # Must match the tool call ID
                            "content": json.dumps(tool_resp),
                        }
                    )

            self.messages = messages
            if response.choices[0].finish_reason == "stop":
                logger.info(f"Fallback agent finished successfully at iteration {i+1}")
                return response.choices[0].message.content 
            else:
                logger.debug(f"Fallback agent did not finish successfully at iteration {i+1}")
