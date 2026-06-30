import os
import yaml
import time
import asyncio
import datetime
from sqlalchemy import text, exc
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

class UserConfig:
    def __init__(self):
        with open("app/clientConfig.yaml", "r") as f:
            self.current_config = yaml.safe_load(f)

    def setup_config_for_user(self, available_tables: list,
                              dbname: str) -> None:
        config_dict = {
            dbname: {
                "AUTO_DASHBOARD": True,
                "DATABASE": {
                    "available_tables": available_tables
                },
                "GRAPH_TYPE": "plotlycharts",
                "LLM": {
                    "GRAPH": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "INSIGHTS": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "SQL": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "SUGGESTIONS": {"BASE": "gpt", "MODEL": "gpt-4.1"}
                },
                "DATA_REFRESH": {
                    "FREQUENCY": "0 0 * * *",
                    "LAST_REFRESH_DATE": str(datetime.date.today())
                },
                "CONVERSATION_FILTERS": [],
                "PROMPT_SUGGESTIONS": []
            }
        }
        self.current_config.update(config_dict)
        self.save_config()

    def update_config_add_roles(self, db_id: int, role_list: list) -> None:
        if db_id not in self.current_config:
            self.current_config[db_id] = {}
        self.current_config[db_id]["USAGE_METADATA"]["ROLE"] = role_list
        self.save_config()

    def save_config(self):
        with open("app/clientConfig.yaml", 'w') as file:
            yaml.safe_dump(self.current_config, file, default_flow_style=False)

    def update_config_add_available_tables(self, db_id: int, table_list: list) -> None:
        self.current_config[db_id]["DATABASE"]["AVAILABLE_TABLES"] = table_list
        self.save_config()

    def get_available_tables(self, db_id: int):
        return self.current_config[db_id]["DATABASE"]["AVAILABLE_TABLES"]


# class SchemaInfoGenerator:
#     def __init__(self, llm):
#         self.llm = llm
#         self.prompt = """You are provided with table and columns present in the table.
#         Your task is to find which columns are self explanatory in by their name.
#         Also provide description of columns based on your understanding in simple English upto 6 words. Minimum words are preferred.    

#         Here is the table name
#         {table_name}

#         Here are columns for the table:
#         {columns_list}

#         [INSTRUCTIONS]
#         Provide mappings in the form of:
#         - column name, is_self_explanatory, column_description
#         - Use exact column names as provided. Double check the column names.
#         - Fill is_self_explanatory with "yes" or "no".
#         - If is_self_explanatory is "yes", set column_description to "" (empty string).
#         - If is_self_explanatory is "no", provide a short description in simple English with 7–8 words.
#         - Do not generate misleading descriptions. If you don't know the description, use "UNKNOWN".
#         - Output should strictly follow the format below.
#         - Only provide output in the given format and nothing else.

#         [Output format]
#         {output}
#         """

#     async def get_col_mappings(self, table, column_list):
#         print(table)
#         print(column_list)
#         pr = self.prompt.format(table_name=table, columns_list=column_list,
#                                 output='[{"col_name": "exact name of column", "is_self_explanatory": "yes or no", "col_description": "Maximum 7-8 words description"}]')
#         resp = await self.llm.ainvoke(pr)
#         results = resp.content
#         results = eval(results)
#         print(results)
#         return results

#     async def generate_col_requirements(self, table_info):
#         tasks = []
#         for t in table_info:
#             table = t["table"]
#             columns = [i["col_name"] for i in t["column_details"]]
#             task = asyncio.create_task(self.get_col_mappings(table, columns))
#             tasks.append(task)

#         results = await asyncio.gather(*tasks)
#         return results

# class GenerateSchemaBase:
#     def __init__(self, client: str, client_engine, relationships: list,
#                  table_details: List[TableMetadata]):
#         self.client = client
#         self.engine = client_engine
#         self.relationships = relationships
#         self.table_details = table_details
#         self.base_location = None

#     def get_schema_str(self):
#         schema = []
#         for td in self.table_details:
#             table_name = td.table
#             col_definitions = []
#             primary_keys = []
#             for col in td.column_details:
#                 col_name = col.col_name
#                 data_type = str(col.data_type).replace('COLLATE "SQL_Latin1_General_CP1_CI_AS"', "").strip()
#                 alias = col.alias
#                 display_name = f"{col_name} {data_type}"+ (f" ALIAS {alias}" if alias else "")
#                 col_definitions.append(display_name + ",\n")
#                 if col.primary_key:
#                     primary_keys.append(col_name)

#             if len(primary_keys)>0:
#                 primary_keys_string = f"Primary Key: {table_name}(" + ", ".join(primary_keys)+")\n"
#             else:
#                 primary_keys_string = "\n"

#             table_relationships = [rel for rel in self.relationships if rel["from_table"]==table_name]

#             rel_string_list = []
#             if len(table_relationships)>0:
#                 for rel in table_relationships:
#                     rel_string_list.append(f"{rel['from_table']}({rel['from_table_column']}) references {rel['to_table']}({rel['to_table_column']})")
#             rel_string = "Foreign Key: " + ", ".join(rel_string_list) if len(rel_string_list)>0 else ""+"\n"

#             col_definitions[-1] = col_definitions[-1].replace(",\n","")
#             table_schema_string = f"Table {table_name}({''.join(col_definitions)})\n"
#             table_schema_string+=primary_keys_string
#             table_schema_string+=rel_string
#             schema.append(table_schema_string.strip())

#         schema_string = "\n\n".join(schema)
#         schema_string_path = "schema_strings"
#         os.makedirs(schema_string_path, exist_ok=True)
#         with open(os.path.join(schema_string_path, f"{self.client}.txt"), "w", encoding="utf-8") as f:
#             f.write(schema_string)
#         return schema_string

# col_exceptions = ["comment", "raw_comment", "externaldatareference", "case_number",
#                   "improvement_area"]

# class UniqueCategoriesTable:
#     def __init__(self, client: str, table_details: List[TableMetadata], client_engine):
#         self.client = client
#         self.engine = client_engine
#         self.table_details = table_details

#     def get_table_categorical_mappings(self):
#         table_categorical_columns_mappings = {}
#         for td in self.table_details:
#             for cd in td.column_details:
#                 if "VARCHAR" in cd.data_type:
#                     if table_categorical_columns_mappings.get(td.table):
#                         table_categorical_columns_mappings[td.table].append(cd.col_name)
#                     else:
#                         table_categorical_columns_mappings[td.table] = [cd.col_name]
#         return table_categorical_columns_mappings

#     def get_sql_for_unique_categories_per_table(self):
#         query_results = {}
#         t_c_mappings = self.get_table_categorical_mappings()
#         for k, v in t_c_mappings.items():
#             sql_queries = []
#             for i, col in enumerate(v):
#                 if col.lower() not in col_exceptions:
#                     sql_query = f'''SELECT * FROM (SELECT TOP 100 {col} AS unique_value, '{col}' AS col_name 
#                                     FROM {k}
#                                     WHERE {col} IS NOT NULL
#                                     GROUP BY {col}
#                                     ORDER BY COUNT({col}) DESC) t{i}'''
#                     sql_queries.append(sql_query)
#             sql_query_full = " UNION ALL ".join(sql_queries)

#             with self.engine.connect() as conn:
#                 results = conn.execute(text(sql_query_full)).mappings().fetchall()
#             query_results[k] = results
#         return query_results

