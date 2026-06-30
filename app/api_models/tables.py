from pydantic import BaseModel, Field, field_serializer
from typing import List, Any, Optional, Literal
from .chats import ResetChat, ConversationFilter
import re


class GetTable(ResetChat):
    query: str
    chat_id: str | None = Field(default=None, description="Unique identifier for the chat session, used for caching and tracking purposes")
    chat_history_query_id: Optional[str] = Field(default="0")
    filters: Optional[List[ConversationFilter]] = None
    use_cached_sql: Optional[bool] = True
    max_rows: Optional[int] = Field(default=500, description="Maximum number of rows to fetch for the tables")

    @field_serializer("query")
    def correct_query(self, query: str):
        query_split = query.split(" ")
        query_split = [q.strip() for q in query_split if len(q.strip()) > 0]
        return " ".join(query_split)


class TablesRequest(BaseModel):
    user_query: str = Field(..., description="User's query for text to sql and fetch tables from the database")
    chat_id: str = Field(..., description="Unique identifier for the chat session")
    filters: Optional[List[ConversationFilter]] = Field(default_factory=list, description="List of filters applied to the query")
    use_cached_sql: Optional[bool] = Field(default=True, description="Flag to indicate whether to use cached SQL query for fetching tables")
    maximum_sql_response_length: Optional[int] = Field(default=1000, description="Maximum number of rows to fetch for the tables")

    @field_serializer("user_query")
    def serialize_user_query(self, value: str) -> str:
        value = value.strip()
        value = re.sub(r'\s+', ' ', value) 
        return value.strip()

class TablesResponse(BaseModel):
    query_key: str = Field(..., description="Unique identifier for the query, analogous to transaction_id")
    sql: str = Field(..., description="The SQL query generated from the user's input")
    approach: str = Field(..., description="The approach used for generating the SQL query")
    table: Optional[List[dict]] = Field(default_factory=list, description="List of tables fetched based on the SQL query")
    table_columns: Optional[List[str]] = Field(default_factory=dict, description="list of columns for each table fetched")
    status_message: Literal["success", "awaiting_human_input", "error"] = Field(..., description="Status message indicating the result of the table fetching operation")
    multiple_response: bool = Field(default=False, description="Flag to indicate if there are multiple responses for the query")