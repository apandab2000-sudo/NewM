import json
import logging
from typing import Any, Dict, List, Optional
from app.core.dashboards.agents.base_agent import BaseAgent
from app.core.dashboards.agents.models import AgentResult, DashboardComponent, DashboardDesign
from app.core.llm_connections.base import LLMBase


logger = logging.getLogger(__name__)


DESIGN_SYSTEM_PROMPT = """
You are a world-class UI/UX Designer specialising in executive analytics dashboards.
Your task: produce a complete DashboardDesign JSON that defines layout, sections, and components.

Design Principles:
- Start with a powerful summary section (KPI cards: 3-5 hero metrics)
- Organise by business domain (e.g. Sales, Operations, Finance)
- Mix chart types purposefully: trends → line, comparisons → bar, share → pie/donut
- Every component MUST have a clear business intent
- Provide 1-2 fallback_component_types per component (e.g. bar_chart → ["table","kpi_card"])
- Mark mission-critical components priority=1, exploratory ones priority=2

Output STRICT JSON matching this schema (no markdown, no commentary):
{
  "title": "string",
  "subtitle": "string",
  "theme": "professional-dark | light-clean | executive-blue",
  "dashboard_filters": [
    {
      "title": "string",
      "subtitle": "string",
      "scope": "dashboard",
      "column": "table.column",
      "sql": "SELECT DISTINCT column FROM table ORDER BY 1"
    }
  ],
  "sections": [
    {
      "title": "string",
      "subtitle": "string",
      "filters": [],
      "components": [
        {
          "title": "string",
          "subtitle": "string",
          "component_type": "kpi_card|bar_chart|line_chart|pie_chart|table|text_insight|heatmap|combination",
          "sql": "SELECT ...",
          "chart_type": null,
          "intent": "Business purpose of this component",
          "priority": 1,
          "fallback_component_types": ["table"],
          "filters": [],
          "sub_components": []
        }
      ]
    }
  ]
}

SQL Rules:
- Dialect: {dialect}
- Read-only queries only
- All column references must use schema-qualified names
- KPI cards: return a single row with labelled columns
- Charts: return rows suitable for axis rendering (category + value columns)
- Tables: max 20 rows unless filtered
"""

REPAIR_SYSTEM_PROMPT = """
You are a UI/UX Designer fixing a broken executive dashboard.

You are given:
1. The original DashboardDesign JSON
2. A list of components that have NO data or FAILED with SQL errors

Your task:
- For each failed component, propose a REPLACEMENT component with:
  * A different component_type (use fallback_component_types as hints)
  * A different SQL query targeting the same or related business area
  * Same section placement
- You may also suggest removing a low-priority (priority=2) component entirely (use "action": "remove")

Output STRICT JSON:
{
  "repairs": [
    {
      "section_title": "string",
      "original_component_title": "string",
      "action": "replace | remove",
      "replacement": {
        "title": "...",
        "subtitle": "...",
        "component_type": "...",
        "sql": "...",
        "intent": "...",
        "priority": 1,
        "fallback_component_types": [],
        "filters": [],
        "sub_components": []
      }
    }
  ]
}

SQL Dialect: {dialect}
"""


class UIUXDesignerAgent(BaseAgent):
    """
    Agent 1: UI/UX Designer
    - Produces initial DashboardDesign from schema + user request
    - Can repair designs when DataEngineerAgent reports empty/failed components
    """

    def __init__(self, llm: LLMBase, model: str, dialect: str = "postgresql"):
        super().__init__("UIUXDesignerAgent", llm, model, dialect)

    async def _run(self, messages: List[Dict], system: str = "") -> Dict[str, Any]:
        """
        Override this to plug in your actual LLM client.
        Expected to return a parsed dict from the LLM's JSON output.
        
        Example for Anthropic:
            response = await self.llm.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=messages,
            )
            return json.loads(response.content[0].text)
        """
        raise NotImplementedError(
            "Inject your LLM client implementation by subclassing or monkey-patching _run"
        )

    async def design(
        self,
        user_request: str,
        schema: str,
        analysis_context: Optional[List[Dict]] = None,
    ) -> AgentResult:
        """
        Step 1: Produce full DashboardDesign JSON from schema.
        """
        self._log("Starting dashboard design...")
        system = DESIGN_SYSTEM_PROMPT.format(dialect=self.dialect)
        context_str = json.dumps(analysis_context or [], default=str)

        messages = [
            {
                "role": "user",
                "content": (
                    f"User Request:\n{user_request}\n\n"
                    f"Database Schema:\n{schema}\n\n"
                    f"Data Analysis Context (optional):\n{context_str}"
                ),
            }
        ]

        try:
            raw = await self._call_llm(messages, system=system)
            design = DashboardDesign.model_validate(raw)
            self._log(
                f"Design complete: {len(design.sections)} sections, "
                f"{sum(len(s.components) for s in design.sections)} components"
            )
            return AgentResult(agent=self.name, success=True, data=design)
        except Exception as e:
            self._log(f"Design failed: {e}", "error")
            return AgentResult(agent=self.name, success=False, error=str(e))

    async def repair(
        self,
        original_design: DashboardDesign,
        failed_components: List[Dict[str, str]],
        schema: str,
    ) -> AgentResult:
        """
        Step 3 (optional): Patch the design when components have no data.
        Returns a new patched DashboardDesign.
        """
        self._log(f"Repairing {len(failed_components)} failed components...")
        system = REPAIR_SYSTEM_PROMPT.format(dialect=self.dialect)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Original Design:\n{original_design.model_dump_json(indent=2)}\n\n"
                    f"Failed Components:\n{json.dumps(failed_components, indent=2)}\n\n"
                    f"Database Schema:\n{schema}"
                ),
            }
        ]

        try:
            raw = await self._call_llm(messages, system=system)
            repairs = raw.get("repairs", [])
            patched_design = self._apply_repairs(original_design, repairs)
            self._log(f"Repair complete: {len(repairs)} repairs applied")
            return AgentResult(agent=self.name, success=True, data=patched_design)
        except Exception as e:
            self._log(f"Repair failed: {e}", "error")
            return AgentResult(agent=self.name, success=False, error=str(e))

    def _apply_repairs(
        self, design: DashboardDesign, repairs: List[Dict]
    ) -> DashboardDesign:
        """Apply repair instructions to the design in-place."""
        repair_index: Dict[str, Dict] = {
            r["original_component_title"]: r for r in repairs
        }

        for section in design.sections:
            new_components = []
            for component in section.components:
                repair = repair_index.get(component.title)
                if repair is None:
                    new_components.append(component)
                    continue

                if repair["action"] == "remove":
                    self._log(f"Removing component: {component.title}")
                    continue

                if repair["action"] == "replace" and repair.get("replacement"):
                    self._log(
                        f"Replacing '{component.title}' → '{repair['replacement']['title']}'"
                    )
                    try:
                        new_comp = DashboardComponent.model_validate(repair["replacement"])
                        new_comp.status = "replaced"
                        new_components.append(new_comp)
                    except Exception as e:
                        self._log(f"Invalid replacement for {component.title}: {e}", "warning")
                        new_components.append(component)
                else:
                    new_components.append(component)

            section.components = new_components

        return design