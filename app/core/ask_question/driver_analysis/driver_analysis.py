import pandas as pd
import os
from pathlib import Path
from typing import Any
import json
import yaml
import re
from types import SimpleNamespace
from app.core.helper import make_json_safe
from app.databases.client_sql.operations import get_table_from_sql, get_table_and_status_and_columns
from app.logger import get_logger
import asyncio
import time

from app.core.prompts import PromptGetter


logger = get_logger(__name__)

PROJECT_ROOT = Path(os.getenv("IOD_PROJECT_ROOT", Path(__file__).resolve().parents[4]))
APP_DIR = Path(os.getenv("IOD_APP_DIR", PROJECT_ROOT / "app"))
BUSINESS_DATA_DIR = Path(os.getenv("IOD_BUSINESS_DATA_DIR", PROJECT_ROOT / "business_data"))
CLIENT_CONFIG_PATH = APP_DIR / "clientConfig.yaml"
SCHEMA_STRINGS_DIR = APP_DIR / "core" / "schema_strings"
DRIVER_ANALYSIS_QUERY_TIMEOUT_SECONDS = 12


DEFAULT_DRIVER_ANALYSIS_PROMPT = """
Read the SQL query and identify features for driver analysis.

SQL:
{sql_query}

Return only valid JSON:
{{
  "aggregated_features": [],
  "available_features": []
}}
"""


DEFAULT_SQL_PROMPT_FOR_KPI = """
You are an expert {dialect} SQL analyst. Generate one executable SQL query for the user request.

Use the previous user question and SQL from chat history as context. Reuse the same table, filters, and metric logic when relevant.

Schema:
{schema}

Return SQL only. Do not include markdown, JSON, explanations, or commentary.
"""


class DriverAnalysis:
    def __init__(
        self,
        client: str,
        llm: Any,
        client_db: Any,
        table: list[dict[str, Any]],
        user_query: str,
        sql_code: str,
    ) -> None:
        # Initializes analysis context: dataset, LLM, DB connection, config, and prompts.
        if not client or not client.strip():
            raise ValueError("DriverAnalysis requires a non-empty client name")
        if llm is None:
            raise ValueError("DriverAnalysis requires an LLM instance")
        if client_db is None:
            raise ValueError("DriverAnalysis requires a client database pool")
        if not isinstance(table, list) or not table:
            raise ValueError("DriverAnalysis requires non-empty table data")
        if not user_query or not user_query.strip():
            raise ValueError("DriverAnalysis requires a non-empty user query")
        if not sql_code or not sql_code.strip():
            raise ValueError("DriverAnalysis requires non-empty SQL")

        self.client = client
        self.llm = llm
        self.client_db = client_db
        self.df = pd.DataFrame(table)
        self.previous_user_query = user_query
        self.sql_code = sql_code
        self.sql_query_table = None
        self.prompt_getter = PromptGetter

        if not CLIENT_CONFIG_PATH.exists():
            raise FileNotFoundError(f"Client config not found: {CLIENT_CONFIG_PATH}")
        with open(CLIENT_CONFIG_PATH, "r", encoding="utf-8") as f:
            self.config_dict = yaml.safe_load(f)
        # Tolerant config lookup allows datasets to exist in the app DB before being added to clientConfig.yaml
        self.available_tables = self.config_dict.get(client, {}).get("DATABASE", {}).get("available_tables", [])
        self.db_dialect = (
            self.config_dict.get(client, {}).get("DATABASE", {}).get("dialect")
            or self.config_dict.get(client, {}).get("CONNECTION", {}).get("dialect")
            or getattr(getattr(client_db, "dialect", None), "name", None)
            or "mssql"
        )
        try:
            self.prompt_getter = PromptGetter(client)
        except ModuleNotFoundError:
            logger.warning("Prompt module not found for %s; using default driver-analysis prompts", client)
            self.prompt_getter = None

    def _get_prompt(self, prompt_name: str, default_prompt: str) -> str:
        """Return a client prompt when available, otherwise use a safe default."""
        # Functionality: fetches dataset-specific prompts while safely falling back to defaults.
        if not self.prompt_getter:
            return default_prompt
        try:
            return self.prompt_getter.get_prompt(prompt_name)
        except AttributeError:
            logger.warning("Prompt %s not found for %s; using default", prompt_name, self.client)
            return default_prompt

    async def _invoke_llm(self, prompt_value: Any) -> SimpleNamespace:
        """Invoke either a LangChain chat model or the app's LLMBase wrapper."""
        # Normalizes LLM calls across LangChain and custom LLM wrapper implementations.
        if hasattr(self.llm, "ainvoke"):
            return await self.llm.ainvoke(prompt_value)

        messages = []
        if hasattr(prompt_value, "to_messages"):
            for message in prompt_value.to_messages():
                role = "assistant" if message.type == "ai" else message.type
                if role == "human":
                    role = "user"
                messages.append({"role": role, "content": message.content})
        else:
            messages.append({"role": "user", "content": str(prompt_value)})

        response = await self.llm.generate(messages=messages)
        content = getattr(response, "content", None)
        if content is None:
            content = getattr(response, "parsed_json", None)
        if content is None:
            content = getattr(response, "raw_response", None)
        return SimpleNamespace(content=content if isinstance(content, str) else json.dumps(content))

    async def get_features_from_sql(self) -> dict[str, list[str]]:
        """Extract available features from SQL QUERY"""
        # Asks LLM to identify aggregate and available metrics, falls back to SQL parsing if JSON fails.
        driver_analysis_prompt = self._get_prompt("driver_analysis_prompt", DEFAULT_DRIVER_ANALYSIS_PROMPT)
        # prompt = PromptTemplate.from_template(driver_analysis_prompt)
        # pr = prompt.invoke({"sql_query": self.sql_code})
        pr = driver_analysis_prompt.format(sql_query=self.sql_code)
        resp = await self._invoke_llm(pr)
        try:
            processed_resp = json.loads(resp.content.replace("json", "").replace("`", ""))
        except json.JSONDecodeError:
            logger.warning(
                "Driver feature extraction returned invalid JSON; using SQL fallback",
                extra={"event_type": "driver_feature_extraction_json_error", "client": self.client},
            )
            processed_resp = self._extract_features_from_sql_fallback()
        logger.debug(
            "Driver feature extraction result",
            extra={
                "event_type": "driver_feature_extraction",
                "client": self.client,
                "aggregated_feature_count": len(processed_resp.get("aggregated_features", [])),
                "available_feature_count": len(processed_resp.get("available_features", [])),
            },
        )
        return processed_resp

    def _extract_features_from_sql_fallback(self) -> dict[str, list[str]]:
        """Best-effort SQL feature extraction when the LLM response is not JSON."""
        # Parses SQL aliases and GROUP BY fields as fallback when LLM JSON parsing fails.
        aliases = re.findall(r"\bas\s+([\w\[\]]+)", self.sql_code, flags=re.IGNORECASE)
        group_by_match = re.search(r"\bgroup\s+by\s+(.+?)(?:\border\s+by\b|$)", self.sql_code, flags=re.IGNORECASE | re.DOTALL)
        group_features = []
        if group_by_match:
            group_features = [
                part.strip().split(".")[-1].strip("[]")
                for part in group_by_match.group(1).split(",")
                if part.strip()
            ]
        return {
            "aggregated_features": [alias.strip("[]") for alias in aliases],
            "available_features": group_features + [alias.strip("[]") for alias in aliases],
        }

    def get_available_table_in_sql_query(self) -> str | None:
        # Identifies source table by matching against config or inferring from FROM/JOIN clauses.
        tables_present = [t for t in self.available_tables if t.lower() in self.sql_code.lower()]
        if len(tables_present) > 0:
            self.sql_query_table = tables_present[0]
        else:
            # Fallback: when clientConfig has no available_tables entry,
            # infer the first table after FROM/JOIN from the generated SQL.
            table_matches = re.findall(r"\b(?:from|join)\s+([\w\.\[\]]+)", self.sql_code, flags=re.IGNORECASE)
            if table_matches:
                self.sql_query_table = table_matches[0].split(".")[-1].strip("[]")
        return self.sql_query_table

    async def get_correlated_dataframe(self) -> pd.DataFrame:
        # Detect table before loading correlation file (prevents attempting to load overall_None.csv)
        self.get_available_table_in_sql_query()
        if not self.sql_query_table:
            logger.warning(
                "No available table found in SQL query for driver analysis",
                extra={"event_type": "driver_analysis_table_not_found", "client": self.client},
            )
            return pd.DataFrame()

        base_path = BUSINESS_DATA_DIR / self.client / "corr_datasets"
        corr_file_path = base_path / f"overall_{self.sql_query_table}.csv"
        if not corr_file_path.exists():
            logger.warning(
                "Correlation dataset not found",
                extra={
                    "event_type": "driver_analysis_correlation_file_not_found",
                    "client": self.client,
                    "table": self.sql_query_table,
                    "path": str(corr_file_path),
                },
            )
            return pd.DataFrame()

        corr_matrix = pd.read_csv(corr_file_path)

        corr_matrix_features = pd.concat([corr_matrix["column_1"], corr_matrix["column_2"]]).dropna().unique().tolist()
        logger.debug(
            "Loaded driver-analysis correlation data",
            extra={
                "event_type": "driver_analysis_correlation_loaded",
                "client": self.client,
                "table": self.sql_query_table,
                "rows": corr_matrix.shape[0],
            },
        )

        sql_features = await self.get_features_from_sql()

        primary_feature_in_sql_query_list = sql_features["aggregated_features"]
        overall_feature_in_sql_query_list = sql_features["available_features"]

        corr_df = pd.DataFrame()

        # Fuzzy matching instead of exact set intersection: handles naming variations like GTN vs GTN_Qtr_Value
        primary_feature = self._match_correlation_feature(corr_matrix_features, primary_feature_in_sql_query_list)
        if primary_feature:
            corr_df = self._correlations_for_feature(corr_matrix, primary_feature)

            if corr_df.shape[0] == 0:
                primary_feature = None
        else:
            primary_feature = None

        if not primary_feature:
            # Fallback to fuzzy matching across all features to handle naming variations
            filtered_primary_feature = self._match_all_correlation_features(
                corr_matrix_features,
                overall_feature_in_sql_query_list,
            )
            for p in filtered_primary_feature:
                primary_feature = p
                corr_df = self._correlations_for_feature(corr_matrix, primary_feature)

                if corr_df.shape[0] > 2:
                    break
        logger.debug(
            "Selected driver-analysis primary feature",
            extra={
                "event_type": "driver_analysis_primary_feature",
                "client": self.client,
                "primary_feature": primary_feature,
            },
        )

        return corr_df.iloc[:3]

    def _correlations_for_feature(self, corr_matrix: pd.DataFrame, primary_feature: str) -> pd.DataFrame:
        left_matches = corr_matrix[corr_matrix["column_1"] == primary_feature].copy()
        right_matches = corr_matrix[corr_matrix["column_2"] == primary_feature].copy()
        if not right_matches.empty:
            right_matches[["column_1", "column_2"]] = right_matches[["column_2", "column_1"]]
        return pd.concat([left_matches, right_matches], ignore_index=True).sort_values("correlation", ascending=False)

    @staticmethod
    def _normalize_feature_name(feature: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(feature).lower())

    def _match_correlation_feature(self, corr_features: list[str], sql_features: list[str]) -> str | None:
        matches = self._match_all_correlation_features(corr_features, sql_features)
        return matches[0] if matches else None

    def _match_all_correlation_features(self, corr_features: list[str], sql_features: list[str]) -> list[str]:
        """Match SQL aliases like GTN_Qtr_Value back to base correlation metrics like GTN."""
        sql_feature_set = {str(feature) for feature in sql_features}
        exact_matches = [feature for feature in corr_features if feature in sql_feature_set]
        if exact_matches:
            return exact_matches

        normalized_sql_features = [self._normalize_feature_name(feature) for feature in sql_features]
        fuzzy_matches = []
        for corr_feature in corr_features:
            normalized_corr_feature = self._normalize_feature_name(corr_feature)
            if not normalized_corr_feature:
                continue
            if any(
                normalized_corr_feature in sql_feature
                or sql_feature in normalized_corr_feature
                for sql_feature in normalized_sql_features
                if sql_feature
            ):
                fuzzy_matches.append(corr_feature)

        return fuzzy_matches

    def get_schema_str(self) -> str:
        schema_text_file_path = SCHEMA_STRINGS_DIR / f"{self.client}.txt"
        if not schema_text_file_path.exists():
            logger.warning(
                "Schema string not found for driver analysis",
                extra={
                    "event_type": "driver_analysis_schema_file_not_found",
                    "client": self.client,
                    "path": str(schema_text_file_path),
                },
            )
            return ""

        with open(schema_text_file_path, "r", encoding="utf-8") as f:
            final_str = f.read()
        return final_str

    def process_sql_response(self, sql_code: str) -> str:
        sql_code = sql_code.replace("`", "").replace("json", "").replace("\n", " ").replace("sql", "")
        return sql_code

    async def execute_query(self, user_query: str, db_dialect: str) -> str:
        sql_prompt_for_kpi = self._get_prompt("sql_prompt_for_kpi", DEFAULT_SQL_PROMPT_FOR_KPI)
        system_prompt = sql_prompt_for_kpi.format(schema=self.get_schema_str(), dialect=db_dialect)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"previous user query: {self.previous_user_query}"},
            {"role": "assistant", "content": f"{self.sql_code}"},
            {"role": "user", "content": user_query},
        ]


        # prompt = PromptTemplate.from_template(sql_prompt_for_kpi)
        # full_prompt = ChatPromptTemplate.from_messages(
        #     [
        #         SystemMessagePromptTemplate(prompt=prompt),
        #         MessagesPlaceholder("chat_history"),
        #         ("human", "{user_input}"),
        #     ]
        # )

        # chat_history = [HumanMessage(content=self.previous_user_query), AIMessage(content=self.sql_code)]

        # pr = full_prompt.invoke({
        #     "schema": self.get_schema_str(),
        #     "user_input": user_query,
        #     "dialect": db_dialect,
        #     "chat_history": chat_history
        # })

        resp = await self._invoke_llm(messages)
        resp = self.process_sql_response(resp.content)
        return resp

    async def get_sql_from_queries(self, queries: list[str]) -> list[dict[str, Any]]:
        tasks = []
        # Use config dialect instead of database object attribute for better test/deployment flexibility
        db_dialect = self.db_dialect
        for query in queries:
            task = asyncio.create_task(self.execute_query(query, db_dialect))
            tasks.append(task)
        results = await asyncio.gather(*tasks)

        tasks = []
        t1 = time.time()
        for r in results:
            # Updated to pass client parameter for proper dataset context in query execution
            task = asyncio.create_task(
                get_table_from_sql(
                    self.client_db,
                    self.client,
                    r,
                    query_timeout=DRIVER_ANALYSIS_QUERY_TIMEOUT_SECONDS,
                )
            )
            tasks.append(task)
        sql_query_results = await asyncio.gather(*tasks)
        logger.debug(
            "Driver-analysis follow-up query execution completed",
            extra={
                "event_type": "driver_analysis_followup_query_timing",
                "client": self.client,
                "duration_seconds": time.time() - t1,
                "query_count": len(results),
            },
        )

        sql_tables_updated = []
        for s in sql_query_results:
            table_json, table_status, _ = get_table_and_status_and_columns(s)
            if table_status != "success":
                sql_tables_updated.append([])
                continue

            # Using make_json_safe for consistent value handling (replaces handle_large_decimal_values)
            table_json = make_json_safe(table_json)
            sql_tables_updated.append(table_json)

        results_list = []

        for q, s, t in zip(queries, results, sql_tables_updated):
            if len(t) > 0:
                results_list.append({
                    "user_query": q,
                    "sql_code": s,
                    "sql_table": t
                })
        return results_list

    # async def fix_sql_programming_error(self, prompt: Any, sql_code: str, error_message: str) -> str:
    #     logger.debug("Attempting to fix driver-analysis SQL programming error")
    #     prompt.messages.append(AIMessage(content=sql_code))
    #     human_message = f"""update sql code to resolve the error
    #     {error_message}
    #     provide updated sql in below format
    #     ```sql
    #     sql query
    #     ```"""
    #     prompt.messages.append(HumanMessage(content=human_message))
    #     sql_code = await self._invoke_llm(prompt)
    #     sql_code = sql_code.content
    #     query_result = await get_table_from_sql(
    #         self.client_db,
    #         self.client,
    #         sql_code,
    #         query_timeout=DRIVER_ANALYSIS_QUERY_TIMEOUT_SECONDS,
    #     )
    #     self.generated_table, table_status, _ = get_table_and_status_and_columns(query_result)
    #     if table_status != "success":
    #         return ""
    #     return sql_code

#
#
#
#
#
#
#
# def get_driver_analysis_sql():
#     sql_code = "SELECT     Calendar_Year,     Calendar_Month,     Region,     COUNT(ID) AS Stock_Out_Count FROM     M360_DB.dbo.HP_Availability_Data_29042024 WHERE     Availability = 'Out of Stock' GROUP BY     Calendar_Year,     Calendar_Month,     Region ORDER BY     Calendar_Year,     Calendar_Month,     Region; "
#
#     da = DriverAnalysis(
#         client = "m360_2",
#         table=[{'Calendar_Year': 2023, 'Calendar_Month': 1, 'Region': 'APAC', 'Stock_Out_Count': 83518}, {'Calendar_Year': 2023, 'Calendar_Month': 2, 'Region': 'APAC', 'Stock_Out_Count': 33618}, {'Calendar_Year': 2023, 'Calendar_Month': 3, 'Region': 'APAC', 'Stock_Out_Count': 38893}, {'Calendar_Year': 2023, 'Calendar_Month': 4, 'Region': 'APAC', 'Stock_Out_Count': 35360}, {'Calendar_Year': 2023, 'Calendar_Month': 5, 'Region': 'APAC', 'Stock_Out_Count': 38092}, {'Calendar_Year': 2023, 'Calendar_Month': 6, 'Region': 'APAC', 'Stock_Out_Count': 37381}, {'Calendar_Year': 2023, 'Calendar_Month': 7, 'Region': 'APAC', 'Stock_Out_Count': 33542}, {'Calendar_Year': 2023, 'Calendar_Month': 8, 'Region': 'APAC', 'Stock_Out_Count': 38332}, {'Calendar_Year': 2023, 'Calendar_Month': 9, 'Region': 'APAC', 'Stock_Out_Count': 51398}, {'Calendar_Year': 2023, 'Calendar_Month': 10, 'Region': 'APAC', 'Stock_Out_Count': 47131}, {'Calendar_Year': 2023, 'Calendar_Month': 11, 'Region': 'APAC', 'Stock_Out_Count': 39048}, {'Calendar_Year': 2023, 'Calendar_Month': 12, 'Region': 'APAC', 'Stock_Out_Count': 35641}],
#         user_query = "out of stock count across months and years and regions",
#         sql_code=sql_code
#     )
#     sql_query_table = da.get_available_table_in_sql_query()
#
#     filtered_features = da.filter_features_present_in_corr_df()
# #     print(filtered_features)
#
# if __name__ == "__main__":
#     get_driver_analysis_sql()
