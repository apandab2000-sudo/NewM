
from typing import Any, Dict, List, Literal, Optional
from app.logger import get_logger 
from pydantic import BaseModel, Field, model_validator
 

logger = get_logger(__name__)
 
# ─────────────────────────────────────────────
# Shared Data Models
# ─────────────────────────────────────────────
 
ComponentType = Literal["kpi_card", "bar_chart", "line_chart", "pie_chart",
                         "table", "text_insight", "heatmap", "combination"]
 
FilterScope = Literal["dashboard", "section", "component"]
 
 
class ComponentFilter(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    scope: FilterScope
    column: str = Field(..., description="Column in format 'table.column'")
    sql: str = Field(..., description="SQL query for the filter", examples="SELECT DISTINCT column FROM table ORDER BY column")
    section_title: Optional[str] = None
    component_title: Optional[str] = None
 
 
class SubComponent(BaseModel):
    sub_component_id: str
    title: str
    subtitle: Optional[str] = ""
    component_type: Literal["kpi_card", "bar_chart", "line_chart", "pie_chart",
                             "table", "text_insight"]
    sql: str
    chart_type: Optional[str] = None
    intent: Optional[str] = ""
 
 
class DashboardComponent(BaseModel):
    component_id: str
    title: str
    subtitle: Optional[str] = ""
    component_type: ComponentType
    sql: str
    chart_type: Optional[str] = Field(None, description="Specific chart type for graph components")
    intent: Optional[str] = ""
    priority: int = 1            
    fallback_component_types: List[str] = Field(default_factory=list)
    filters: List[ComponentFilter] = Field(default_factory=list)    
    sub_components: List[SubComponent] = Field(default_factory=list)
 
    # Runtime fields (populated by DataEngineerAgent)
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: int = 0
    sql_error: Optional[str] = None
    status: Literal["pending", "ok", "empty", "error", "replaced"] = "pending"
 
    @model_validator(mode="after")
    def validate_combination(self):
        if self.component_type == "combination" and not self.sub_components:
            raise ValueError("combination component must have sub_components")
        return self
 
 
class DashboardSection(BaseModel):
    section_id: str
    title: str
    subtitle: Optional[str] = ""
    filters: Optional[List[ComponentFilter]] = Field(default=None, default_factory=list)
    components: List[DashboardComponent] = Field(default_factory=list)
 
 
class DashboardDesign(BaseModel):
    title: str = Field(..., description="Dashboard title")
    subtitle: Optional[str] = ""
    color_palette: Optional[List[str]] = Field(..., description="List of color palette for the dashboard")
    dashboard_filters: Optional[List[ComponentFilter]] = Field(default=None, default_factory=list)
    sections: List[DashboardSection] = Field(default_factory=list)



class AgentResult(BaseModel):
    agent: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    token_usage: Dict[str, int] = Field(default_factory=dict)
 
 
class ComponentValidationReport(BaseModel):
    total: int = 0
    ok: int = 0
    empty: int = 0
    error: int = 0
    replaced: int = 0
    failed_components: List[Dict[str, str]] = Field(default_factory=list)
 
    @property
    def needs_recovery(self) -> bool:
        return self.empty > 0 or self.error > 0
 