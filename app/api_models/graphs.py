from pydantic import BaseModel, Field, model_serializer
from typing import List, Dict, Any, Optional
from .chats import ResetChat, ConversationFilter
from .tables import GetTable


class GetGraph(GetTable):
    query_key: str
    color_palette: Optional[List[str]] = None
    table: List[Dict[str, Any]] = []

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)


class EditGraph(ResetChat):
    chat_id: str
    query_key: str
    query: str
    table: List[Dict[str, Any]]
    color_palette: List[str]
    filters: List[ConversationFilter]
    chart_type: Optional[str] = "auto"
    chart_sub_type: Optional[str] = "auto"
    graph_id: Optional[str] = "0"
    sql: str
    previous_user_query: str

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)