from app.databases.client_sql.operations import get_table_from_sql, get_table_and_status_and_columns, get_table_from_sql_parallel
from app.logger import get_logger
from pathlib import Path
import json


logger = get_logger(__name__)


# tools = [
#     {   
#         "type": "function",
#         "name": "get_column_metadata_for_table",
#         "description": (
#             "Returns column names and their SQL data types for a given table. "
#             "ALWAYS call this first for any table/column pair before deciding "
#             "which investigation tool to use. Use the data type to route: "
#             "varchar/nvarchar/char → use get_distinct_values or check_value_existence; "
#             "int/decimal/float/money → use get_value_range; "
#             "date/datetime/datetimeoffset → use get_value_range."
#         ),
#         "strict": True,
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "table_name": {
#                     "type": "string",
#                     "description": "Fully qualified table name, e.g. 'dbo.Sales' or 'Sales'"
#                 }
#             },
#             "required": ["table_name"],
#             "additionalProperties": False
#         }
#     },
#     {
#         "type": "function",
#         "name": "get_distinct_values_for_column_of_table",
#         "description": (
#             "Fetches up to 100 distinct values from a categorical column "
#             "(varchar, nvarchar, char). Use this when a text filter value "
#             "doesn't exist in the column, to find valid alternatives to "
#             "suggest to the user. Do NOT call on numeric or date columns."
#         ),
#         "strict": True,
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "table_name": {
#                     "type": "string",
#                     "description": "Fully qualified table name, e.g. 'dbo.Sales'"
#                 },
#                 "column_name": {
#                     "type": "string",
#                     "description": "Column to get distinct values from"
#                 }
#             },
#             "required": ["table_name", "column_name"],
#             "additionalProperties": False
#         }
#     },
#     {
#         "type": "function",
#         "name": "check_value_existence_in_column",
#         "description": (
#             "Checks whether a specific value exists (using LIKE fuzzy match) "
#             "in a text column. Returns true or false. Call this first for "
#             "text/categorical filters before fetching all distinct values. "
#             "If this returns false, the value is definitely wrong — then call "
#             "get_distinct_values_for_column_of_table to find alternatives."
#         ),
#         "strict": True,
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "table_name": {
#                     "type": "string",
#                     "description": "Fully qualified table name, e.g. 'dbo.Sales'"
#                 },
#                 "column_name": {
#                     "type": "string",
#                     "description": "Column to check for value existence"
#                 },
#                 "value": {
#                     "type": "string",
#                     "description": "Value to check for existence"
#                 }
#             },
#             "required": ["table_name", "column_name", "value"],
#             "additionalProperties": False
#         }
#     },
#     {
#         "type": "function",
#         "name": "get_value_range_for_column",
#         "description": (
#             "Returns the MIN and MAX values for a numeric or date column. "
#             "Use this to verify whether the user's filter value or date range "
#             "falls within the actual data range. If the user's range doesn't "
#             "overlap with MIN–MAX, that filter is the problem."
#         ),
#         "strict": True,
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "table_name": {
#                     "type": "string",
#                     "description": "Fully qualified table name, e.g. 'dbo.Sales'"
#                 },
#                 "column_name": {
#                     "type": "string",
#                     "description": "Numeric or date column to get range for"
#                 }
#             },
#             "required": ["table_name", "column_name"],
#             "additionalProperties": False
#         }
#     }
# ]



tools = [
    {
        "type": "function",
        "function": {
            "name": "get_column_metadata_for_table",
            "description": (
                "Returns column names and their SQL data types for a given table. "
                "ALWAYS call this first for any table/column pair before deciding "
                "which investigation tool to use. Use the data type to route: "
                "varchar/nvarchar/char → use get_distinct_values_for_column_of_table "
                "or check_value_existence_in_column; "
                "int/decimal/float/money → use get_value_range_for_column; "
                "date/datetime/datetimeoffset → use get_value_range_for_column."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name, e.g. 'dbo.Sales' or 'Sales'"
                    }
                },
                "required": ["table_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_distinct_values_for_column_of_table",
            "description": (
                "Fetches up to 100 distinct values from a categorical column "
                "(varchar, nvarchar, char). Use this when a text filter value "
                "doesn't exist in the column, to find valid alternatives to "
                "suggest to the user. Do NOT call on numeric or date columns."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name, e.g. 'dbo.Sales'"
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Column to get distinct values from"
                    }
                },
                "required": ["table_name", "column_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_value_existence_in_column",
            "description": (
                "Checks whether a specific value exists (using LIKE fuzzy match) "
                "in a text column. Returns true or false. Call this first for "
                "text/categorical filters before fetching all distinct values. "
                "If this returns false, the value is likely invalid; then call "
                "get_distinct_values_for_column_of_table to find alternatives."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name, e.g. 'dbo.Sales'"
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Column to check for value existence"
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to check for existence"
                    }
                },
                "required": ["table_name", "column_name", "value"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_value_range_for_column",
            "description": (
                "Returns the MIN and MAX values for a numeric or date column. "
                "Use this to verify whether the user's filter value or date range "
                "falls within the actual data range. If the user's range doesn't "
                "overlap with MIN and MAX, that filter is likely causing zero rows."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name, e.g. 'dbo.Sales'"
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Numeric or date column to get range for"
                    }
                },
                "required": ["table_name", "column_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_similar_values_for_column",
            "description": (
                "Fetches up to 10 values from a text column that are similar to a given value, using a LIKE fuzzy match. "
                "Use this when a text filter value doesn't exist in the column, to find valid alternatives to suggest to the user. "
                "Do NOT call on numeric or date columns."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name, e.g. 'dbo.Sales'"
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Column to get similar values from"
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to find similar entries for"
                    }
                },
                "required": ["table_name", "column_name", "value"],
                "additionalProperties": False
            }
        }
    }
]



async def get_column_metadata_for_table(
    dbname: str,
    table_name: str
) -> dict:
    base_path = Path("business_data") / dbname / "columns"

    if not table_name.lower().startswith("dbo."):
        table_name_for_path = f"dbo.{table_name}"
    else:
        table_name_for_path = table_name

    file_path = None
    for file in base_path.glob("*.json"):
        if file.stem.lower() == table_name_for_path.lower():
            file_path = file
            break
    
    if not file_path or not file_path.exists():
        logger.error(f"Column metadata file not found for table {table_name}: {file_path}")
        return {
            "status": "error",
            "message": "Column metadata not found.",
            "metadata": {
                "table_name": table_name,
                "columns": []
            }
        }
    
    try:
        with open(file_path, "r") as f:
            metadata = json.load(f)
        metadata = [
            {
                "column_name": col["name"],
                "data_type": col["type"]
            }
            for col in metadata
        ]
        return {
            "status": "success",
            "message": "Column metadata retrieved successfully",
            "metadata": {
                "table_name": table_name,
                "columns": metadata
            }
        }
    except Exception as e:
        logger.error(f"Error reading column metadata for table {table_name} from file {file_path}: {e}")
        return {
            "status": "error",
            "message": "Error finding column metadata",
            "metadata": {
                "table_name": table_name,
                "columns": []
            }
        }
        

async def get_distinct_values_for_column_of_table(
    dbname: str,
    client_pool, 
    dialect: str,
    table_name: str, 
    column_name: str
) -> dict:
    
    if dialect == "mssql":
        sql = f"""SELECT
                    DISTINCT {column_name}
                FROM
                    {table_name}
                order by {column_name}
                OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY;"""
    
    else:
        logger.error(f"Dialect {dialect} not supported for distinct value retrieval")
        return {
            "status": "error",
            "message": f"Dialect {dialect} not supported for distinct value retrieval",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "distinct_values": []
            }
        }
        
    try:
        query_results = await get_table_from_sql(client_pool, dbname, sql)
        table_json, table_staus, _ = get_table_and_status_and_columns(query_results)
        if table_staus != "success":
            logger.error(f"Error fetching distinct values for {column_name} in {table_name}: {table_json}")
            return {
                "status": "error",
                "message": "Error fetching distinct values",
                "response": {
                    "table_name": table_name,
                    "column_name": column_name,
                    "distinct_values": []
                }
            }
        return {
            "status": "success",
            "message": "Distinct values found successfully",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "distinct_values": [row[column_name] for row in table_json]
            }
        }
    except Exception as e:
        logger.error(f"Error fetching distinct values for {column_name} in {table_name}: {e}")
        return {
            "status": "error",
            "message": "Error fetching distinct values",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "distinct_values": []
            }
        }


async def check_value_existence_in_column(
    dbname: str,
    client_pool, 
    dialect: str,
    table_name: str, 
    column_name: str,
    value: str
) -> dict:
    if dialect == "mssql":
        sql = f"""SELECT CASE 
                WHEN EXISTS (SELECT 1 FROM {table_name} WHERE {column_name} COLLATE SQL_Latin1_General_CP1_CI_AS LIKE '%{value}%') 
                THEN 1 
                ELSE 0 
            END AS does_exist;"""
    else:
        logger.error(f"Dialect {dialect} not supported for existence check")
        return {
            "status": "error",
            "message": f"Dialect {dialect} not supported for existence check",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "exists": False
            }
        }

    try:
        query_results = await get_table_from_sql(client_pool, dbname, sql)
        table_json, table_staus, _ = get_table_and_status_and_columns(query_results)
        if table_staus != "success":
            logger.error(f"Error executing existence check query: {table_json}")
            return {
                "status": "error",
                "message": "Error executing existence check query",
                "response": {
                    "table_name": table_name,
                    "column_name": column_name,
                    "value": value,
                    "exists": False
                }
            }
        logger.info(f"Existence check for value '{value}' in column '{column_name}' of table '{table_name}' completed successfully: {table_json}")
        return {
            "status": "success",
            "message": "Value existence check completed",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "exists": table_json[0]["does_exist"] == 1
            }
        }
    except Exception as e:
        logger.error(f"Error checking value existence for {column_name} in {table_name}: {e}")
        return {
            "status": "error",
            "message": "Error checking value existence",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "exists": False
            }
        }



async def get_value_range_for_column(
    dbname: str,
    client_pool, 
    dialect: str,
    table_name: str, 
    column_name: str
) -> list:
    if dialect == "mssql":
        sql = f"""SELECT MIN({column_name}) AS min_value, MAX({column_name}) AS max_value FROM {table_name};"""
    else:
        logger.error(f"Dialect {dialect} not supported for value range retrieval")
        return {
            "status": "error",
            "message": f"Dialect {dialect} not supported for value range retrieval",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "min_value": None,
                "max_value": None
            }
        }

    try:
        query_results = await get_table_from_sql(client_pool, dbname, sql)
        table_json, table_staus, _ = get_table_and_status_and_columns(query_results)
        if table_staus != "success":
            logger.error(f"Error executing value range query: {table_json}")
            return {
                "status": "error",
                "message": "Error executing value range query",
                "response": {
                    "table_name": table_name,
                    "column_name": column_name,
                    "min_value": None,
                    "max_value": None
                }
            }
        logger.info(f"Value range retrieval for column '{column_name}' in table '{table_name}' completed successfully: {table_json}")
        return {
            "status": "success",
            "message": "Value range retrieved successfully",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "min_value": table_json[0]["min_value"],
                "max_value": table_json[0]["max_value"]
            }
        }
    except Exception as e:
        logger.error(f"Error retrieving value range for {column_name} in {table_name}: {e}")
        return {
            "status": "error",
            "message": "Error retrieving value range",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "min_value": None,
                "max_value": None
            }
        }


async def get_similar_values_for_column(
    dbname: str,
    client_pool, 
    dialect: str,
    table_name: str, 
    column_name: str,
    value: str
) -> list:
    if dialect == "mssql":
        sql = f"""SELECT TOP 10 {column_name} FROM {table_name} WHERE {column_name} COLLATE SQL_Latin1_General_CP1_CI_AS LIKE '%{value}%';"""
    
    else:
        logger.error(f"Dialect {dialect} not supported for similar value retrieval")
        return {
            "status": "error",
            "message": f"Dialect {dialect} not supported for similar value retrieval",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "similar_values": []
            }
        }

    try:
        query_results = await get_table_from_sql(client_pool, dbname, sql)
        table_json, table_staus, _ = get_table_and_status_and_columns(query_results)
        if table_staus != "success":
            logger.error(f"Error executing similar value retrieval query: {table_json}")
            return {
                "status": "error",
                "message": "Error executing similar value retrieval query",
                "response": {
                    "table_name": table_name,
                    "column_name": column_name,
                    "value": value,
                    "similar_values": []
                }
            }
        logger.info(f"Similar value retrieval for value '{value}' in column '{column_name}' of table '{table_name}' completed successfully: {table_json}")
        return {
            "status": "success",
            "message": "Similar values retrieved successfully",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "similar_values": table_json
            }
        }
    except Exception as e:
        logger.error(f"Error retrieving similar values for {column_name} in {table_name}: {e}")
        return {
            "status": "error",
            "message": "Error retrieving similar values",
            "response": {
                "table_name": table_name,
                "column_name": column_name,
                "value": value,
                "similar_values": []
            }
        }