import yaml
from functools import lru_cache
from app.databases.client_sql.operations import get_table_from_sql
from app.databases.client_sql.connections import BaseConnectionPool
from app.logger import get_logger
from app.models import ConversationFilter
from typing import List, Optional
import json
import pandas as pd
from app.appConfig import settings
from app.core.helper import make_json_safe, bson_to_json_safe, correct_columns_name
from app.databases.caching.operations import cache_data, get_cached_data


logger = get_logger(__name__)


# @lru_cache(maxsize=10)
def load_config(dbname: str):
    with open("app/clientConfig.yaml", "r") as f:
        config = yaml.safe_load(f)
    return config.get(dbname, {}).get("CONVERSATION_FILTERS", [])


class ChatFilters:
    def __init__(self, dbname: str, client_pool: BaseConnectionPool):
        self.dbname = dbname
        self.client_pool = client_pool

    def get_caching_key(self, filters: Optional[List[ConversationFilter]] = None) -> str:
        if filters:
            payload: dict = {f.col_name: f.selected_values for f in filters}
            payload = dict(sorted(payload.items()))  # sorting the keys
            payload = {
                k: sorted(v) for k, v in sorted(payload.items()) if v
            }  # sorting the values
            base = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            return base
        else:
            return "base"
        
    def generate_sql_query(self, filters, selected_filters=[]):
        queries = []
        order_columns = {}

        # Map selected filters
        selected_map = {
            f.col_name: f.selected_values for f in selected_filters if f.selected_values
        }
        values_list_map = {
            k: ", ".join(f"'{v}'" for v in vlist) for k, vlist in selected_map.items()
        }

        # order info
        for table in filters:
            for col_def in table["columns"]:
                for col_name, props in col_def.items():
                    if "order" in props:
                        order_columns[col_name] = props["order"]

        for table in filters:
            table_name = table["table_name"]
            regular_cols = []
            json_cols = []

            for col_def in table["columns"]:
                for col_name, props in col_def.items():
                    if props.get("is_json", False):
                        json_cols.append(col_name)
                    else:
                        regular_cols.append(col_name)

            # Build WHERE clauses for selected filters
            where_clauses = []
            for col, values in values_list_map.items():
                if col in regular_cols:
                    where_clauses.append(f"{col} IN ({values})")
                elif col in json_cols:
                    where_clauses.append(
                        f"EXISTS (SELECT 1 FROM OPENJSON({col}) AS j WHERE j.value IN ({values}))"
                    )
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Regular columns: generate DISTINCT per column
            for col in regular_cols:
                query = f"""
                    SELECT '{col}' AS SourceColumn, CAST({col} AS VARCHAR(MAX)) AS UniqueValue
                    FROM {table_name}
                    {where_sql}
                    GROUP BY {col}
                    HAVING {col} IS NOT NULL
                """
                queries.append(query.strip())

            # JSON columns: parse once per column
            for col in json_cols:
                query = f"""
                    SELECT '{col}' AS SourceColumn, j.value AS UniqueValue
                    FROM {table_name}
                    CROSS APPLY OPENJSON({col}) AS j
                    {where_sql}
                    GROUP BY j.value
                """
                queries.append(query.strip())

        # --- FIX STARTS HERE ---
        # Ensure order_column_keys is never empty to prevent SQL syntax errors (IN ())
        if order_columns:
            order_column_keys = ", ".join(f"'{k}'" for k in order_columns.keys())
        else:
            # Dummy value that will never match a real column, ensuring valid SQL syntax
            order_column_keys = "'__NO_MATCH__'"
        # --- FIX ENDS HERE ---

        # Combine queries
        final_query = (
            "SELECT SourceColumn, UniqueValue FROM (\n"
            + "\nUNION ALL\n".join(queries)
            + "\n) AS combined\n"
            + f"""ORDER BY SourceColumn,
            CASE WHEN SourceColumn IN ({order_column_keys}) THEN NULL ELSE UniqueValue END ASC,
            CASE WHEN SourceColumn IN ({order_column_keys}) THEN UniqueValue ELSE NULL END DESC"""
        )
        print(final_query)
        return final_query

    async def get_filters(self, use_cache: bool = True):
        available_filters = load_config(self.dbname)

        if not available_filters:
            logger.warning(f"No filter configuration found for database {self.dbname}", extra={"event_type": "filter_config_missing", "dbname": self.dbname})
            return []
        
        sequence_mapping = {}
        selected_filters = []
        for table in available_filters:
            for col in table["columns"]:
                for col_name, props in col.items():
                    sequence_mapping[col_name] = props.get("id", float("inf"))
                    if "default" in props and props["default"] != "":
                        selected_filters.append(
                            ConversationFilter(
                                col_name=col_name,
                                alias="",
                                selected_values=[props["default"]],
                            )
                        )

        caching_key_filters = self.get_caching_key(selected_filters)
        caching_key_prefix = settings.caching_prefix + f"filters__{self.dbname}__"
        caching_key = caching_key_prefix + caching_key_filters
        
        if use_cache: 
            table_json = await get_cached_data(caching_key, self.dbname, endpoint="filters")
            table_json = bson_to_json_safe(table_json)
            if table_json:
                table_df = pd.DataFrame(json.loads(table_json))
        else:
            table_json = None

        if not table_json:
            sql_query = self.generate_sql_query(available_filters, selected_filters)
            table_results = await get_table_from_sql(self.client_pool, self.dbname, sql_query, row_limit=None)
            table_df = pd.DataFrame(table_results.rows, columns=table_results.columns)
            table_json = table_df.to_json(orient="records")
            table_status = table_results.status
            if table_status == "success":
                table_json = make_json_safe(table_json)
                is_cached = await cache_data(caching_key, table_json, settings.filters_caching_ttl)
                if not is_cached:
                    logger.warning("Filters not cached properly")

        unique_values_dict = (
            table_df.groupby("SourceColumn")["UniqueValue"].apply(list).to_dict()
        )
        filters_info = [
            {
                "col_name": column_name,
                "alias": next(
                    (
                        col[column_name]["alias"]
                        for table in available_filters
                        for col in table["columns"]
                        if column_name in col
                        and "alias" in col[column_name]
                        and col[column_name]["alias"] != ""
                    ),
                    correct_columns_name(column_name),
                ),
                "possible_values": unique_values,
                "selected_values": [
                    col[column_name]["default"]
                    for table in available_filters
                    for col in table["columns"]
                    if column_name in col
                    and "default" in col[column_name]
                    and col[column_name]["default"] != ""
                ]
                or [],
                # [table['columns'][column_name] for table in available_filters
                # if column_name in table['columns'] and table['columns'][column_name]] or []
            }
            for column_name, unique_values in unique_values_dict.items()
        ]
        filters_info.sort(
            key=lambda x: sequence_mapping.get(x["col_name"], float("inf"))
        )
        return filters_info

    async def update_filters_with_selection(self, selected_filters: Optional[List[ConversationFilter]] = None, use_cache: bool = True):
        available_filters = load_config(self.dbname)

        alias_lookup = {
            col_name.lower(): props.get("alias")
            for table in available_filters
            for col in table["columns"]
            for col_name, props in col.items()
        }

        caching_key_filters = self.get_caching_key(selected_filters)
        caching_key_prefix = settings.caching_prefix + f"filters__{self.dbname}__"
        caching_key = caching_key_prefix + caching_key_filters

        if use_cache:
            table_json = await get_cached_data(caching_key, self.dbname, endpoint="filters")
            table_json = bson_to_json_safe(table_json)
            if table_json:
                table_df = pd.DataFrame(json.loads(table_json))  # type: ignore
        else:
            table_json = None

        if not table_json:
            sql_query = self.generate_sql_query(available_filters, selected_filters)
            table_results = await get_table_from_sql(self.client_pool, self.dbname, sql_query, row_limit=None)
            table_df = pd.DataFrame(table_results.rows, columns=table_results.columns)
            table_json = table_df.to_json(orient="records")
            table_status = table_results.status
            if table_status == "success":
                table_json = make_json_safe(table_json)
                is_cached = await cache_data(caching_key, table_json, settings.filters_caching_ttl)
                if not is_cached:
                    logger.warning("Filters not cached properly")

        unique_values_dict = (
            table_df.groupby("SourceColumn")["UniqueValue"].apply(list).to_dict()
        )

        sequence_mapping = {}
        for table in available_filters:
            for col in table["columns"]:
                for col_name, props in col.items():
                    sequence_mapping[col_name] = props.get("id", float("inf"))

        selected_dict = {}
        if selected_filters:
            for f in selected_filters:
                selected_dict[f.col_name] = f.selected_values

        filters_info = [
            {
                "col_name": column_name,
                "alias": alias_lookup.get(column_name.lower())
                if alias_lookup.get(column_name.lower())
                else correct_columns_name(column_name),
                "possible_values": unique_values,
                "selected_values": [
                    f.selected_values
                    for f in selected_filters
                    if f.col_name.lower() == column_name.lower()
                ]
                or [],
            }
            for column_name, unique_values in unique_values_dict.items()
        ]
        filters_info.sort(key=lambda x: sequence_mapping.get(x["col_name"], float("inf")))
        return filters_info
