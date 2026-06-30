from pydantic import BaseModel, field_validator, Field, ValidationError, model_validator
from typing import List, Any, Optional, Dict, Literal, Union


class UserName(BaseModel):
    user_name: str

    @field_validator("user_name", mode="before")
    @classmethod
    def clean_user_name(cls, user_name: str):
        if not len(user_name.strip().split(" ")) == 2:
            raise ValidationError(
                "Not a valid user name. user name must contain white space separated first name and last name only without other special characters"
            )
        return user_name.strip().lower()
    
    @property
    def first_name(self) -> str:
        return self.clean_user_name(self.user_name).split(" ")[0]

    @property
    def last_name(self) -> str:
        return self.clean_user_name(self.user_name).split(" ")[1]

    @property
    def email_id(self) -> str:
        cleaned_user_name = self.clean_user_name(self.user_name)
        cleaned_user_name = cleaned_user_name.split(" ")
        return f"{cleaned_user_name[0]}.{cleaned_user_name[1]}@eclerx.com"


class ResetChat(UserName):
    dbname: str

    @field_validator("dbname", mode="before")
    @classmethod
    def check_type_validity(cls, dbname: str):
        return dbname.strip().lower()
    

class ReseChatWIthAddOns(ResetChat):
    use_filters_cache: Optional[bool] = True
    use_prompt_suggestions_cache: Optional[bool] = True

    
class GetModelsRequest(BaseModel):
    user_name: str
    dbname: Optional[str] = None
    
class CustomDashboard(ResetChat):
    user_query: str
    color_palette: Optional[List[str]] = None

    @field_validator("user_query", mode="after")
    @classmethod
    def correct_query(cls, user_query: str):
        query_split = user_query.split(" ")
        query_split = [q.strip() for q in query_split if len(q.strip()) > 0]
        return " ".join(query_split)

    
class DashboardToConversation(ResetChat):
    chat_id: str
    query_key: str

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)


class ConversationFilter(BaseModel):
    alias: str
    col_name: str
    selected_values: List[Any]


class UpdateFiltersInput(ReseChatWIthAddOns):
    chat_id: str
    last_filter: Optional[str] = None
    filters: Optional[List[ConversationFilter]] = []


class GetTable(ResetChat):
    query: str
    chat_id: str
    chat_history_query_id: Optional[str] = Field(default="0")
    filters: Optional[List[ConversationFilter]] = None
    use_cached_sql: Optional[bool] = True
    max_rows: Optional[int] = Field(default=500, description="Maximum number of rows to fetch for the tables")

    @field_validator("query", mode="after")
    @classmethod
    def correct_query(cls, query: str):
        query_split = query.split(" ")
        query_split = [q.strip() for q in query_split if len(q.strip()) > 0]
        return " ".join(query_split)


class GetGraph(GetTable):
    query_key: str
    color_palette: Optional[List[str]] = None
    table: List[Dict[str, Any]] = []
    chat_id: Optional[str] = None

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)
    

class GetInsights(GetGraph):
    sql: str


class GetSuggestions(GetGraph):
    insight: str = Field(default="")


class SuggestionAnalysis(GetTable):
    query_key: str
    color_palette: Optional[List[str]] = None

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)
    

class ClickEvent(BaseModel):
    X: str
    Y: str
    legend: Optional[str] = ""

class DrilldownFeature(BaseModel):
    alias: str    
    col_name: str 

class DoubleClick(GetInsights):
    graph_id: str
    click_event: List[ClickEvent]
    filters: Optional[List[ConversationFilter]] = None
    drilldown_features: Optional[List[DrilldownFeature]] = None
    chart_type: Optional[str] = ""


class PositiveFeedback(BaseModel):
    chat_id: str
    query_key: str
    dbname: str
    query: str
    sql: str

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)

class NegativeFeedback(ResetChat):
    chat_id: str
    query_key: str
    feedback_list: list[dict] = Field(examples=[[{"component":"", "comment": ""}]])

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)
    

class ShareConversation(BaseModel):
    dbname: str
    chat_id: str
    target_users: list[UserName]

    @field_validator("dbname", mode="before")
    @classmethod
    def check_type_validity(cls, dbname: str):
        return dbname.strip().lower()
    
class DeleteConversation(UserName):
    chat_id: str

class DeleteUserQuestion(ResetChat):
    chat_id: str
    query_key: str
    filters: Optional[List[ConversationFilter]] = None

    @property
    def transaction_id(self) -> int:
        return int(self.query_key)
    



################### SETUP #######################
class DBInitRequest(BaseModel):
    dbname: str
    table_list: Optional[List[str]] = None

class TableFetchRequest(BaseModel):
    table_list: List[str]

class ColumnMetadata(BaseModel):
    col_name: Optional[str] = ""
    data_type: Optional[str] = ""
    alias_required: bool = False
    description_required: bool = False
    primary_key: bool = False
    foreign_key: bool = False
    alias: Optional[str] = ""
    description: Optional[str] = ""

class TableMetadata(BaseModel):
    table: Optional[str] = ""
    column_details: List[ColumnMetadata]

class CorrectionRequest(TableFetchRequest):
    db_name: str #added for /iod/self-serve/corrections_and_business_context/
    relationships: list = []
    table_details: List[TableMetadata]

class KpiList(BaseModel):
    kpi: str
    context: str

class FormulaList(BaseModel):
    name: str
    calculations: str

class BusinessContext(BaseModel):
    question: str
    filters: Optional[List[ConversationFilter]]
    sql_query: str
    approach: str | None = None
    context_type: Literal["sample_sql_query", "column_value"] = "sample_sql_query"
    is_positive_example: bool = True
    user_id: int | None = None

class SaveBusinessContext(BaseModel):
    dbname: str
    business_knowledge: Optional[str]
    role: Optional[List]
    domain: Optional[List]
    kpis: List[Optional[KpiList]]
    formulas: List[Optional[FormulaList]]
    sample_questions: List[Optional[BusinessContext]]
    connection_type: str = "mssql"
    target_audience: Optional[List[str]] = None
    business_objectives: Optional[List[str]] = None


# WHAT IF ANALSYIS
class TargetVariable(ResetChat):
    table_name: str

class ModelRequestLineage(TargetVariable):
    target_column: str

class TrainModelRequest(TargetVariable):
    target_column: str
    fields_to_exclude: Optional[List[str]] = None

class FinalizeModel(TargetVariable):
    target_column: str
    model_version: int

class TrainModelStatus(BaseModel):
    job_id: str

class PredictionFeature(BaseModel):
    variable: str
    value: Any

class PredictionFeatureRequest(ResetChat):
    model_id: int

class PredictRequest(PredictionFeatureRequest):
    features: List[PredictionFeature]


class ModelUsageRequest(PredictionFeatureRequest):
    days: int = Field(default=30, description="Number of days to look back")


class DashboardFilters(BaseModel):
    user_name: Optional[str] = None     
    db_name: Optional[str] = None        
    api_name: Optional[str] = None   

    @property
    def first_last(self):
        if self.user_name and " " in self.user_name.strip():
            parts = self.user_name.strip().split(" ")
            return parts[0].lower(), parts[1].lower()
        return None, None

class AdminDashboardRequest(UserName):
    filters: Optional[DashboardFilters] = None

class FilterValueRequest(UserName):
    # Literal ensures only these 3 strings are accepted at the schema level
    filter_type: Literal["user_name", "db_name", "api_name"]


class ReportId(ResetChat):
    report_name: str
    report_description: Optional[str] = None

class UpdateReport(ReportId):
    report_id: int
    is_active: bool


class TableComponent(BaseModel):
    component_type: Literal["table"]
    sql: Optional[str] = None
    columns: Optional[List[str]] = None 
    grouped: bool | None = None


class GraphComponent(BaseModel):
    component_type: Literal["graph"]
    sql: Optional[str] = None
    title: Optional[str] = None
    graph_type: Optional[str] = None
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    legend: Optional[str] = None
    color_palette: Optional[List[str]] = None


class InsightsComponent(BaseModel):
    component_type: Literal["insights"]
    sql: Optional[str] = None
    word_limit: Optional[int] = 100
    tone: Optional[str] = None
    format: Literal["text", "html", "markdown"] = "text"
    audience: Optional[str] = None


class KpiCardComponent(BaseModel):
    component_type: Literal["kpi_card", "indicator"] # Allows both names
    sql: Optional[str] = None
    title: Optional[str] = None
    unit: Optional[str] = ""

class MetricGridComponent(BaseModel):
    component_type: Literal["metric_grid"]
    sql: Optional[str] = None
    title: Optional[str] = None

class SmartArtComponent(BaseModel):
    component_type: Literal["smartart"]
    sql: Optional[str] = None
    title: Optional[str] = None
    style: Optional[Literal["list", "process", "hierarchy", "cycle"]] = "list"

class ParagraphComponent(BaseModel):
    component_type: Literal["paragraph"]
    sql: Optional[str] = None # Optional: Use SQL data as context for the text
    title: Optional[str] = None
    word_limit: Optional[int] = 200
    format: Literal["text", "html", "markdown"] = "text"

class HeaderComponent(BaseModel):
    component_type: Literal["header"]
    title: Optional[str] = None
    subtitle: Optional[str] = None
    report_context: Optional[str] = None 


class ListComponent(BaseModel):
    component_type: Literal["list"]
    sql: Optional[str] = None
    title: Optional[str] = None
    numbered: bool = False
    # "simple" for names/tags, "reasoning" for analytical points
    # list_type: Literal["simple", "reasoning"] = "simple"


# class IndicatorComponent(BaseModel):
#     component_type: Literal["indicator"] # Unified Name
#     sql: Optional[str] = None
#     title: Optional[str] = None
#     include_trends: bool = False 
#     is_grid: bool = False

ComponentMetadata = Union[
    TableComponent, 
    GraphComponent, 
    InsightsComponent, 
    KpiCardComponent, 
    MetricGridComponent,
    # IndicatorComponent
    SmartArtComponent,
    ParagraphComponent,
    HeaderComponent,
    ListComponent
]

class ReportComponentId(ResetChat):
    report_id: int
    component_name: Optional[str] = None
    component_description: Optional[str] = None
    # component_metadata: Optional[Union[TableComponent, GraphComponent, InsightsComponent]] = Field(None, discriminator="component_type")
    component_metadata: Optional[ComponentMetadata] = Field(None, discriminator="component_type")

class UpdateReportComponentId(ResetChat):
    report_id: int
    component_id: int
    component_name: Optional[str] = None
    component_description: Optional[str] = None
    query: Optional[str] = None
    # component_metadata: Optional[Union[TableComponent, GraphComponent, InsightsComponent]] = Field(None, discriminator="component_type")
    component_metadata: Optional[ComponentMetadata] = Field(None, discriminator="component_type")


class ReportChats(ResetChat):
    report_id: int
    query: str

class ReportConversation(ResetChat):
    report_id: int


class ReportConversationResponse(BaseModel):
    chat_id: str
    report_id: int
    prompt_suggestions: Optional[List[str]] = None
    status: int = 200
    status_message: Literal["success", "failure"] = "success"


class ReportSelectable(BaseModel):
    field: str
    option: str
    is_selected: bool
    type: Optional[str] = None
    # metadata: Optional[dict] = None

class ReportGeneration(ReportConversation):
    chat_id: str
    query: str
    selectables: Optional[List[ReportSelectable]] = None
    confirm: bool = False  # Set to true when user clicks 'Confirm/Generate'

class DbConnectionCreate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    dialect: Literal["mssql", "pgsql", "mysql", "clickhouse", "duckdb"] = "mssql"
    db: Optional[str] = None
    name: str
    description: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value
    

class AiModelMappings(BaseModel):
    sql: str
    suggestions: str
    insights: str
    graph: str


class DatasetCreate(BaseModel):
    db_name: str
    db_schema: Optional[str] = None
    ai_provider: Literal["openai", "azure_openai", "gemini", "anthropic"] = "openai"
    ai_model_mappings: Optional[AiModelMappings] = None
    graph_type: Literal["plotlycharts", "echarts"] = "plotlycharts"
    connection_id: int
    
    @field_validator("db_name", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value
    
class TablesToUse(BaseModel):
    tables_to_use: List[str]


class ColumnMappings(BaseModel):
    column_name: str
    alias: Optional[str] = None
    order_by: Literal["asc", "desc"] = "asc"
    default: Optional[List[str]] = None
    indexed: bool = True

class TableColumnSelections(BaseModel):
    table: str
    columns: list[ColumnMappings]

class ConfigureFilters(BaseModel):
    table_column_filters: List[TableColumnSelections]