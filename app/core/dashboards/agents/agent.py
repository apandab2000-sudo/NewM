import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.llms import TokenUsage, get_llm_response
from app.databases.client_sql.connections import BaseConnectionPool
from app.databases.client_sql.operations import QueryResult, get_table_from_sql
from app.logger import get_logger


logger = get_logger(__name__)


FilterScope = Literal["dashboard", "section", "component"]
ComponentType = Literal["kpi_card", "graph", "text", "insight", "combination"]


class DashboardFilter(BaseModel):
	title: str
	subtitle: Optional[str] = ""
	scope: FilterScope
	column: str
	sql: str
	section_title: Optional[str] = None
	component_title: Optional[str] = None


class DashboardSubComponent(BaseModel):
	title: str
	subtitle: Optional[str] = ""
	component_type: Literal["kpi_card", "graph", "text", "insight"]
	sql: str
	chart_type: Optional[str] = None
	intent: Optional[str] = ""
	filters: List[DashboardFilter] = Field(default_factory=list)


class DashboardComponent(BaseModel):
	title: str
	subtitle: Optional[str] = ""
	component_type: ComponentType
	sql: str
	chart_type: Optional[str] = None
	intent: Optional[str] = ""
	filters: List[DashboardFilter] = Field(default_factory=list)
	sub_components: List[DashboardSubComponent] = Field(default_factory=list)

	@model_validator(mode="after")
	def validate_combination_component(self):
		if self.component_type == "combination" and len(self.sub_components) == 0:
			raise ValueError("Combination components must contain sub_components")
		if self.component_type != "combination" and len(self.sub_components) > 0:
			raise ValueError("Only combination components can include sub_components")
		return self


class DashboardSection(BaseModel):
	title: str
	subtitle: Optional[str] = ""
	filters: List[DashboardFilter] = Field(default_factory=list)
	components: List[DashboardComponent] = Field(default_factory=list)


class ExecutiveDashboardOutput(BaseModel):
	title: str
	subtitle: Optional[str] = ""
	sections: List[DashboardSection]
	dashboard_filters: List[DashboardFilter] = Field(default_factory=list)


class ExecutiveDashboardAgent:
	"""
	Agent to build an executive dashboard JSON plan from schema + optional sampled data analysis.

	Flow:
	1) Read schema context.
	2) Ask LLM if data profiling queries are required and generate them.
	3) Run generated SQL queries against client DB (tool access).
	4) Ask LLM for final dashboard JSON with sections, components, filters, titles/subtitles.
	5) Validate final JSON against pydantic schema.
	"""

	def __init__(
		self,
		dbname: str,
		llm: Any,
		llm_name: str,
		dialect: str = "mssql",
		max_analysis_queries: int = 6,
		analysis_row_limit: int = 50,
		query_timeout: int = 45,
	):
		self.dbname = dbname
		self.llm = llm
		self.llm_name = llm_name
		self.dialect = dialect
		self.max_analysis_queries = max_analysis_queries
		self.analysis_row_limit = analysis_row_limit
		self.query_timeout = query_timeout
		self.token_usage: TokenUsage = TokenUsage()

	def _load_schema(self) -> str:
		schema_text_file_path = f"app/core/schema_strings/{self.dbname}.txt"
		with open(schema_text_file_path, "r", encoding="UTF-8") as f:
			return f.read()

	def _accumulate_usage(self, usage: TokenUsage):
		self.token_usage.input_tokens += usage.input_tokens
		self.token_usage.output_tokens += usage.output_tokens
		self.token_usage.cached_tokens += usage.cached_tokens

	def _build_analysis_prompt(self, schema: str) -> str:
		return f"""
You are an executive dashboard planner.

You are given database schema and a dashboard request. Decide whether sampling data is required.
If required, return compact analysis SQL queries that help discover:
- best KPI candidates,
- key trends,
- segmentation dimensions,
- high-priority filters.

Rules:
- SQL must be valid {self.dialect}.
- Read-only SQL only.
- Prefer lightweight aggregations.
- Max {self.max_analysis_queries} queries.
- Use only tables and columns from schema.

Output strict JSON only with this shape:
{{
  "requires_data_analysis": true,
  "analysis_sql_queries": [
	{{"id": "q1", "purpose": "...", "sql": "SELECT ..."}}
  ],
  "dashboard_title_hint": "...",
  "dashboard_subtitle_hint": "..."
}}

Schema:
{schema}
""".strip()

	def _build_final_prompt(self, schema: str, analysis_context: str) -> str:
		return f"""
You are an executive dashboard architect.

Build a complete dashboard JSON definition with:
- dashboard title and subtitle
- sections (each with title, subtitle)
- components under each section
- filters at dashboard / section / component scopes

Component rules:
- component_type must be one of: kpi_card, graph, text, insight, combination
- every component must include title, subtitle, sql, and component_type
- if component_type is combination, include sub_components
- sub_components can only be: kpi_card, graph, text, insight
- each sub_component must include title, subtitle, sql, and component_type

Filter rules:
- every filter must include title, subtitle, scope, column, sql
- scope must be one of: dashboard, section, component
- for section/component scope, include section_title/component_title when applicable

Output requirements:
- Strict JSON only
- No markdown
- SQL must be valid {self.dialect}
- Keep SQL execution-safe and read-only

Return JSON matching exactly this structure:
{{
  "title": "Dashboard title",
  "subtitle": "Dashboard subtitle",
  "dashboard_filters": [
	{{
	  "title": "...",
	  "subtitle": "...",
	  "scope": "dashboard",
	  "column": "table.column",
	  "sql": "SELECT DISTINCT ..."
	}}
  ],
  "sections": [
	{{
	  "title": "Section title",
	  "subtitle": "Section subtitle",
	  "filters": [],
	  "components": [
		{{
		  "title": "Component title",
		  "subtitle": "Component subtitle",
		  "component_type": "kpi_card",
		  "sql": "SELECT ...",
		  "chart_type": null,
		  "intent": "...",
		  "filters": [],
		  "sub_components": []
		}}
	  ]
	}}
  ]
}}

Schema:
{schema}

Data analysis context (optional):
{analysis_context}
""".strip()

	def _format_query_result(self, item: Dict[str, str], query_result: QueryResult) -> Dict[str, Any]:
		preview_rows = [dict(zip(query_result.columns, row)) for row in query_result.rows[:8]] if query_result.columns else []
		return {
			"id": item.get("id", ""),
			"purpose": item.get("purpose", ""),
			"sql": item.get("sql", ""),
			"status": query_result.status,
			"error": query_result.error,
			"row_count": query_result.row_count,
			"columns": query_result.columns,
			"preview_rows": preview_rows,
		}

	async def _generate_analysis_queries(self, user_request: str, schema: str) -> Dict[str, Any]:
		sys_prompt = self._build_analysis_prompt(schema)
		messages = [
			{"role": "system", "content": sys_prompt},
			{"role": "user", "content": user_request},
		]
		result, usage = await get_llm_response(self.llm, self.llm_name, messages)
		self._accumulate_usage(usage)

		if not isinstance(result, dict):
			return {
				"requires_data_analysis": False,
				"analysis_sql_queries": [],
				"dashboard_title_hint": "Executive Dashboard",
				"dashboard_subtitle_hint": "Generated from schema",
			}
		result.setdefault("requires_data_analysis", False)
		result.setdefault("analysis_sql_queries", [])
		result["analysis_sql_queries"] = result.get("analysis_sql_queries", [])[: self.max_analysis_queries]
		return result

	async def _run_analysis_queries(
		self,
		client_pool: BaseConnectionPool,
		analysis_queries: List[Dict[str, str]],
	) -> List[Dict[str, Any]]:
		results: List[Dict[str, Any]] = []
		for item in analysis_queries:
			sql = item.get("sql", "").strip()
			if not sql:
				continue
			query_result = await get_table_from_sql(
				pool=client_pool,
				db_name=self.dbname,
				sql_query=sql,
				row_limit=self.analysis_row_limit,
				query_timeout=self.query_timeout,
			)
			results.append(self._format_query_result(item, query_result))
		return results

	async def _generate_final_dashboard(
		self,
		user_request: str,
		schema: str,
		analysis_context: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		sys_prompt = self._build_final_prompt(schema=schema, analysis_context=json.dumps(analysis_context, default=str))
		messages = [
			{"role": "system", "content": sys_prompt},
			{"role": "user", "content": user_request},
		]

		result, usage = await get_llm_response(self.llm, self.llm_name, messages)
		self._accumulate_usage(usage)

		if not isinstance(result, dict):
			raise ValueError("LLM did not return a JSON object for dashboard output")
		return result

	async def build_executive_dashboard_json(
		self,
		user_request: str,
		client_pool: BaseConnectionPool,
	) -> Dict[str, Any]:
		"""
		Public API method.

		Returns a validated dictionary with:
		- title
		- subtitle
		- dashboard_filters
		- sections
		"""
		schema = self._load_schema()

		analysis_plan = await self._generate_analysis_queries(user_request=user_request, schema=schema)
		analysis_context: List[Dict[str, Any]] = []

		if analysis_plan.get("requires_data_analysis"):
			analysis_context = await self._run_analysis_queries(
				client_pool,
				analysis_plan.get("analysis_sql_queries", []),
			)

		raw_dashboard = await self._generate_final_dashboard(
			user_request=user_request,
			schema=schema,
			analysis_context=analysis_context,
		)

		validated = ExecutiveDashboardOutput.model_validate(raw_dashboard)
		output = validated.model_dump()
		output["analysis_queries"] = analysis_plan.get("analysis_sql_queries", [])
		output["analysis_results"] = analysis_context
		return output
