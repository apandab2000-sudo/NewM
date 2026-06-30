from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Optional, List, Dict, Literal


class QueryResolverModel(BaseModel):
    resolved_query: str = Field(..., description="The resolved user query that is fully self-contained and can be understood without any additional context.")
    dependency: Literal["INDEPENDENT", "DEPENDENT"] = Field(..., description="Whether the original user query was independent or dependent on chat history.")


class ExtractedEntities(BaseModel):
    entities: List[str] = Field(default_factory=list, description="Domain nouns, verbs and adverbs in exact sequence if specified that likely correspond to table or column names.")
    metrics: List[str] = Field(default_factory=list, description="Measurable quantities or aggregation targets (revenue, count, avg price).")
    entity_values: List[str] = Field(default_factory=list, description="Specific filter values referenced (e.g. 'shipped', 'India', 'Q3 2024').")
    time_references: List[str] = Field(default_factory=list, description="Any date or time expressions (e.g. 'last month', '2023', 'Q1').")
    intent: List[str] = Field(default_factory=list, description="Intent of the query, out of: LOOKUP, AGGREGATION, RANKING, COMPARISON, TREND, FILTERING, MULTI-HOP, EXISTENCE, DISTRIBUTION, CORRELATION.")

    @field_validator("entities", "metrics", "entity_values", "time_references", "intent", mode="before")
    @classmethod
    def deduplicate(cls, v):
        seen, out = set(), []
        for item in v or []:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out



class QueryPlannerSteps(BaseModel):
    step_id: int = Field(..., description="Step identifier")
    description: str = Field(..., description="What this step does")
    cte_name: Optional[str] = Field(None, description="Snake_case name for CTE, or null if final SELECT")
    depends_on: List[int] = Field(default_factory=list, description="Steps this step depends on")
    tables_needed: List[str] = Field(default_factory=list, description="Tables needed for this step")
    operation: str = Field(..., description="Operation type: filter, aggregate, join, rank, compare, union, ...")
    output_columns: List[str] = Field(default_factory=list, description="Columns produced by this step")

class QueryPlannerModel(BaseModel):
    strategy: str = Field(..., description="Query planning strategy like direct, cte_chain, subquery, window, set_op, hybrid")
    is_simple: bool = Field(..., description="Whether the query can be executed in a single step without CTEs or subqueries.")
    estimated_complexity: Literal["low", "medium", "high"] = Field(..., description="Estimated complexity of the query.")
    planner_notes: str = Field(..., description="Brief reasoning — 1-3 sentences.")
    steps: List[QueryPlannerSteps] = Field(..., description="Steps involved in the query plan.")


# class ExtractedEntities(BaseModel):
#     entities: list[str] = Field(default_factory=list, description="Domain nouns, table/column name hints")
#     metrics: list[str] = Field(default_factory=list, description="Aggregations, KPIs, measurable quantities")
#     entity_values: list[str] = Field(default_factory=list, description="Filter values, categorical references")
#     time_references: list[str] = Field(default_factory=list, description="Date/time expressions for type-aware column filtering")
#     intent: list[str] = Field(default_factory=lambda: ["SELECT"], description="SQL intent: SELECT | AGGREGATE | COMPARE | TREND")

#     @field_validator("entities", "metrics", "entity_values", "time_references", "intent", mode="before")
#     @classmethod
#     def deduplicate(cls, v):
#         seen, out = set(), []
#         for item in v or []:
#             key = item.strip().lower()
#             if key and key not in seen:
#                 seen.add(key)
#                 out.append(item.strip())
#         return out
    

class TableCandidates(BaseModel):
    table_name: str
    score: float
    source: Literal["vector", "keyword", "relationship"]
    payload: dict = Field(default_factory=dict)

    # columns: Optional[list[str]] = Field(default_factory=list)
    # relationships: Optional[list[str]] = Field(default_factory=list)


class ColumnCandidates(BaseModel):
    table_name: str
    column_name: str
    score: float
    data_type: str = ""
    is_pk: bool = False
    is_fk: bool = False


class ColumnValueCandidate(BaseModel):
    entity_value: str
    table_name: str
    column_name: str
    score: float
    matched_value: Optional[str]

    def to_mapping_string(self):
        return (
            f"-- '{self.entity_value}' maps to "
            f"{self.table_name}.{self.column_name} = '{self.matched_value}' "
            f"(score={self.score:.2f})"
        )