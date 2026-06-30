from app.databases.client_sql.connections import BaseConnectionPool 
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from app.databases.client_sql.operations import get_table_and_status_and_columns, get_table_from_sql_parallel, get_table_from_sql
import json
from app.logger import get_logger
from app.databases.dependencies import client_pool_manager, get_pool


logger = get_logger(__name__)


class ProdilingQueryLoader(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get(self, version: str):
        pass


class MSSQLProfilingQueryLoader(ProdilingQueryLoader):
    
    query_path = Path("app/core/setups/profiling_queries/mssql")

    def get(self, version: str = "2016"):
        version_path = self.query_path / f"{version}.sql"
        if not version_path.exists():
            raise ValueError(f"Unsupported MSSQL version: {version}")

        with open(version_path, "r") as f:
            return f.read()
        
class LoadQuery:
    query_mapping = {
        "mssql": MSSQLProfilingQueryLoader(),
        # "postgresql": PostgreSQLProfilingQueryLoader(),
    }

    def get_query(self, dialect: str, version: str):
        loader = self.query_mapping.get(dialect.lower())
        if not loader:
            raise ValueError(f"Unsupported database dialect: {dialect}")
        return loader.get(version)


# generate columns to ignore which check if column starts  or ends with _id, _keyword, _uuid, _guid, _timestamp, _date, _time or contains created, updated, modified and also add common columns to ignore like created_at, updated_at, created_on, updated_on, createddate, modifieddate
def get_columns_to_ignore():
    ignore_suffixes = ["_id", "_keyword", "_uuid", "_guid", "_timestamp", "_date", "_time"]
    ignore_contains = ["created", "updated", "modified"]
    common_ignore_columns = ["created_at", "updated_at", "created_on", "updated_on", "createddate", "modifieddate"]

    columns_to_ignore = set(common_ignore_columns)

    # Add suffix-based columns to ignore
    for suffix in ignore_suffixes:
        columns_to_ignore.add(f"%{suffix}")
    
    # Add contains-based columns to ignore
    for substring in ignore_contains:
        columns_to_ignore.add(f"%{substring}%")

    return list(columns_to_ignore)
    

COLS_TO_IGNORE = [
    'improvement_area',
    'theme_subtheme_list',
    'comment',
    'raw_comment'
]

BASE_SQL = """
SELECT TOP 100 DISTINCT {column_name} as unique_values from {table_name}"""


class MetaDataSetup:

    metadata_path = Path("business_data")

    def __init__(self, dbname: str, client_pool: BaseConnectionPool):
        self.dbname = dbname
        self.client_pool = client_pool

    def _load_sql_query(self, dialect: str, version: str):
        query_loader = LoadQuery()
        return query_loader.get_query(dialect, version)
    
    def get_columns_from_a_table(self, table_name: str, schema_name: str):
        return self.client_pool.get_columns_for_table(table_name, schema_name)
    
    def get_sql_query(self, table_name: str, dialect: str, version: str):
        sql_query = self._load_sql_query(dialect, version)
        return sql_query.format(
            cols_to_ignore = tuple(COLS_TO_IGNORE),
            table_name = table_name
        )

    def write_results_to_file(self, results: List[dict], output_file: str):
        output_path = self.metadata_path / self.dbname / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=4)

    async def generate_metatdata(self, dialect: str, schema: str, tables_list: List[str], version: str = "2016", replace_existing: bool = False) -> None:
        """
        Generate metadata for the specified tables and write results to files.
        Args:
            dialect: Database dialect (e.g., 'mssql', 'postgresql')
            version: Database version (e.g., '2016' for MSSQL)
            schema: Database schema name
            tables_list: List of table names to generate metadata for
            replace_existing: Whether to replace existing metadata if it exists. Default is False.
            
        Returns:
            None
        """

        if (self.metadata_path / self.dbname / "tables/tables.json").exists() and not replace_existing:
            logger.info(f"Metadata file tables.json already exists for {self.dbname}. Skipping generation as replace_existing is set to False.")
            return
        
        sql_queries = []
        
        for table_name in tables_list:
            sql_queries.append(self.get_sql_query(table_name, dialect, version))

        print(sql_queries[0])
        
        query_results = await get_table_from_sql_parallel(
            self.client_pool, 
            self.dbname, 
            sql_queries, 
            row_limit=None, 
            query_timeout=60
        )

        table_results = []
        for table, qr in zip(tables_list, query_results):
            table_json, table_status, table_columns = get_table_and_status_and_columns(qr)
            
            if table_status == "success":
                table_json_new = []

                relationships = []
                columns = []

                for col in table_json:
                    columns.append(col["name"])
                    col["foreign_key"] = json.loads(col["foreign_key"]) if col["foreign_key"] else None
                    if col["foreign_key"]:
                        relationships.append(col["foreign_key"])
                    col["unique_values"] = json.loads(col["unique_values"]) if col["unique_values"] else None
                    col["distribution_mappings"] = json.loads(col["distribution_mappings"]) if col["distribution_mappings"] else None
                    col["description"] = None
                    col["synonyms"] = []
                    table_json_new.append(col)

                new_rel = []
                for rel in relationships:
                    rel_dict = {}
                    for k, v in rel.items():
                        rel_dict[k] = v if isinstance(v, str) else v
                    new_rel.append(rel_dict)

                # Below step is for Oracle databases
                # for columns where unique values are not populated and their data type is varchar we will genrate distinct values useing BASE_SQL. also it will only be generated where num_uniue_valeues are None or less than 500
                # for col in table_json_new:
                #     if col["unique_values"] is None and col["type"].lower() == "varchar":
                #         if col["num_unique_values"] is None:
                #             unique_values_query = BASE_SQL.format(column_name=col["name"], table_name=table)
                #         elif col["num_unique_values"] < 500:
                #             unique_values_query = BASE_SQL.format(column_name=col["name"], table_name=table)                        
                #         else:
                #             continue
                        
                #         try:
                #             unique_values_result = await get_table_from_sql(
                #                 self.client_pool, 
                #                 self.dbname, 
                #                 unique_values_query, 
                #                 query_timeout=60
                #             )
                #             un_table_json, _, un_tbale_status = get_table_and_status_and_columns(unique_values_result)
                #             if un_tbale_status == "success":
                #                 col["unique_values"] = [row["unique_values"] for row in un_table_json]
                #             else:
                #                 logger.error(f"Failed to get unique values for column {col['name']} in table {table}: {un_tbale_status}", extra={"event_type": "metadata_generation_error", "table": table, "column": col["name"], "status": un_tbale_status})
                #         except Exception as e:
                #             logger.error(f"Exception occurred while getting unique values for column {col['name']} in table {table}: {str(e)}", extra={"event_type": "metadata_generation_exception", "table": table, "column": col["name"], "error": str(e)})    
                        
                
                table_results.append({
                    "name": table,
                    "description": None,
                    "columns": columns,
                    "relationships": new_rel
                })
                self.write_results_to_file(table_json_new, f"columns/{table}.json")
            else:
                logger.error(f"Failed to get metadata for table {table}: {table_status}", extra={"event_type": "metadata_generation_error", "table": table, "status": table_status})

        self.write_results_to_file(table_results, f"tables/tables.json")
        

class MetaDataSetupDuckDB(MetaDataSetup):

    async def generate_metatdata(self, dialect: str, schema: str, tables_list: List[str], version: str = "2016", replace_existing: bool = False) -> None:
        # For DuckDB we will get the metadata from the system tables and write to file without making any sql queries
        table_results = []
        for table in tables_list:
            columns = self.get_columns_from_a_table(table, schema)
            table_results.append({
                "name": table,
                "description": None,
                "columns": columns,
                "relationships": []
            })
            self.write_results_to_file(columns, f"columns/{table}.json")
        
        self.write_results_to_file(table_results, f"tables/tables.json")



async def generate_metadata_for_tables(
    dataset_details,
    connection_details,
    version: str = "2016", 
    replace_existing: bool = False
):
    if connection_details.dialect.lower() not in ["duckdb"]:
        pool = await get_pool(dataset_details, connection_details)
        metadata_setup = MetaDataSetup(dataset_details.db_name, pool)
        
        await metadata_setup.generate_metatdata(
            dialect=connection_details.dialect, 
            schema=dataset_details.schema, 
            tables_list=dataset_details.tables_list,
            version=version,
            replace_existing=replace_existing
        )
        await client_pool_manager.close_async_pool(connection_details.id)

    else:
        pass
