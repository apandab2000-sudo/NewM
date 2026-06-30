import pymongo
from pydantic import BaseModel, Field
from beanie import Document
from typing import List, Dict, Optional
from app.appConfig import settings


class Plotly_Graph(BaseModel):
    graph_id: int
    plotly_code: str
    chart_type: str


class Suggestion(BaseModel):
    suggestion_id: int
    user_query: str
    sql_code: str
    sql_table: list[dict]
    approach: Optional[str] = None
    category: Optional[str] = None


class InightsTablePart(BaseModel):
    sql: str
    table: list[dict] = []

class Insights(BaseModel):
    distinct_insights: List = Field(default=[])
    consolidated_insight: str = Field(default="")
    insights_data: List[Optional[InightsTablePart]] = [] 

class Transaction(Document):  # This is the model
    transaction_id: int
    table: List[Dict] = Field(default=[])
    approach: str | None = None
    graphs: List[Plotly_Graph] = Field(default=[])
    insights: Insights = Field(default=Insights())
    suggestions: List[Suggestion] = Field(default=[])

    class Settings:
        name = settings.nosql_collection
        indexes = [
            [
                ("transaction_id", pymongo.DESCENDING),
            ]
        ]
