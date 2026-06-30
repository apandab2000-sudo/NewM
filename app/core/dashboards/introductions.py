import numpy as np
import pandas as pd
import json
# from app.databases.connections import AioODBCPool
# from app.core.table_from_sql import get_table_from_sql_parallel
from app.databases.client_sql.operations import get_table_from_sql_parallel, get_table_and_status_and_columns
from app.databases.client_sql.connections import BaseConnectionPool


identity_columns = [
    "externaldatareference",
    "case_number",
    "comment_id",
    "comment",
    "raw_comment"
]

datetime_columns = [
    "fiscal_year",
    "fiscal_quarter",
    "fiscal_month",
    "response_date",
    "open_date",
    "close_date",
    "return_date",
    "calendar_month",
    "calendar_week", 
    "fiscal_half"
]

num_cols = [
    "rating"
]


IDENTITY_COLUMNS = [
    "externaldatareference",
    "case_number",
    "id",
    "comment_id"
]

DATE_COLUMNS = [
    "year",
    "fiscal_year",
    "fiscal_quarter",
    "fiscal_month",
    "response_date",
    "open_date",
    "close_date",
    "return_date",
    "calendar_month",
    "calendar_week", 
    "fiscal_half"
]

COLS_TO_IGNORE = [
    'improvement_area',
    'theme_subtheme_list',
    'comment',
    'raw_comment'
]




MSSQL_PROFILING_QUERY_FULL = """WITH PKColumns AS
(
    SELECT
        ic.object_id,
        ic.column_id,
        1 AS is_primary_key
    FROM sys.key_constraints kc
    JOIN sys.index_columns ic
        ON kc.parent_object_id = ic.object_id
        AND kc.unique_index_id = ic.index_id
    WHERE kc.type = 'PK'
),

FKColumns AS
(
    SELECT
        fkc.parent_object_id AS object_id,
        fkc.parent_column_id AS column_id,

        OBJECT_SCHEMA_NAME(pt.object_id)+'.'+pt.name AS parent_table,
        pc.name AS parent_column,

        OBJECT_SCHEMA_NAME(rt.object_id)+'.'+rt.name AS referenced_table,
        rc.name AS referenced_column
    FROM sys.foreign_key_columns fkc
    JOIN sys.tables pt
        ON pt.object_id = fkc.parent_object_id
    JOIN sys.columns pc
        ON pc.object_id = fkc.parent_object_id
        AND pc.column_id = fkc.parent_column_id
    JOIN sys.tables rt
        ON rt.object_id = fkc.referenced_object_id
    JOIN sys.columns rc
        ON rc.object_id = fkc.referenced_object_id
        AND rc.column_id = fkc.referenced_column_id
),

StatsData AS
(
    SELECT
        OBJECT_SCHEMA_NAME(s.object_id)+'.'+OBJECT_NAME(s.object_id) AS table_name,
        c.name AS column_name,
        t.name AS data_type,

        CAST(ISNULL(pk.is_primary_key,0) AS BIT) AS is_primary_key,

        CAST(
			(
			    SELECT
			        fk.parent_table,
			        fk.parent_column,
			        fk.referenced_table,
			        fk.referenced_column
			    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
			)
		AS NVARCHAR(4000)) AS foreign_key,

        CONVERT(NVARCHAR(200), h.range_high_key) AS RawValue,
		CONVERT(NVARCHAR(200), h.range_high_key) AS Value,
        h.equal_rows

    FROM sys.stats s

    JOIN sys.stats_columns sc
        ON s.object_id=sc.object_id
        AND s.stats_id=sc.stats_id

    JOIN sys.columns c
        ON sc.object_id=c.object_id
        AND sc.column_id=c.column_id

    JOIN sys.types t
        ON c.user_type_id=t.user_type_id

    CROSS APPLY sys.dm_db_stats_histogram(s.object_id,s.stats_id) h

    LEFT JOIN PKColumns pk
        ON pk.object_id = c.object_id
        AND pk.column_id = c.column_id

    LEFT JOIN FKColumns fk
        ON fk.object_id = c.object_id
        AND fk.column_id = c.column_id

    WHERE s.object_id = OBJECT_ID('{schema}.{table_name}')
),

ColumnStats AS
(
SELECT
    table_name,
    column_name,
    data_type,
    is_primary_key,
    foreign_key,

    MIN(CASE 
        WHEN data_type IN ('int','bigint','smallint','tinyint',
                           'float','real','decimal','numeric',
                           'date','datetime','datetime2','smalldatetime')
        THEN RawValue END) AS min_value,

    MAX(CASE 
        WHEN data_type IN ('int','bigint','smallint','tinyint',
                           'float','real','decimal','numeric',
                           'date','datetime','datetime2','smalldatetime')
        THEN RawValue END) AS max_value,

    COUNT(Value) AS distinct_values,
    SUM(equal_rows) AS total_rows

FROM StatsData
GROUP BY table_name, column_name, data_type, is_primary_key, foreign_key
),

CardinalityClass AS
(
SELECT
    *,
    CASE
        WHEN distinct_values >= 100
             OR (distinct_values*1.0/NULLIF(total_rows,0)) >= 0.3
        THEN 1
        ELSE 0
    END AS is_high_cardinality

FROM ColumnStats
),

TopValues AS
(
SELECT
    column_name,
    data_type,
    Value,

    CAST(equal_rows*100.0/
        SUM(equal_rows) OVER(PARTITION BY column_name)
    AS DECIMAL(10,2)) AS DistributionPercent,

    ROW_NUMBER() OVER
    (
        PARTITION BY column_name
        ORDER BY equal_rows DESC
    ) rn

FROM StatsData
),

DistributionJSON AS
(
SELECT
    t1.column_name,

    JSON_QUERY(
		(
		    SELECT
		        t2.Value AS value,
		        t2.DistributionPercent AS pct
		    FROM TopValues t2
		    WHERE t2.column_name = t1.column_name
		    AND t2.data_type IN ('varchar','nvarchar','nchar','object')
        	AND t2.Value <> '' 
        	AND t2.Value IS NOT NULL
            AND rn<=100
            AND t2.column_name NOT IN {cols_to_ignore}
		    FOR JSON PATH
		)
	) AS distribution_mappings

FROM TopValues t1
GROUP BY t1.column_name
),

UniqueValuesJSON AS
(
SELECT
    t1.column_name,
    
    JSON_QUERY(
        (
		    SELECT
		        t2.Value AS value
		    FROM TopValues t2
		    WHERE t2.column_name = t1.column_name
		    AND t2.data_type IN ('varchar','nvarchar','nchar','object')
        	AND t2.Value <> '' 
        	AND t2.Value IS NOT NULL
            AND rn<=100
            AND t2.column_name NOT IN {cols_to_ignore}
		    FOR JSON PATH
		)
    ) as unique_values

FROM TopValues t1
GROUP BY t1.column_name
)

SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.is_primary_key, 
    c.foreign_key,
    c.min_value,
    c.max_value,
    u.unique_values,
    
    CASE
        WHEN c.is_high_cardinality = 1 AND c.data_type in ('varchar','nvarchar','nchar','object')
        THEN c.distinct_values
    END AS num_unqiue_values,

    CASE
        WHEN c.is_high_cardinality = 0
        THEN d.distribution_mappings
    END AS distribution_mappings

FROM CardinalityClass c

JOIN DistributionJSON d
ON c.column_name=d.column_name

JOIN UniqueValuesJSON u
ON c.column_name=u.column_name"""





class IntroductionTablesCreator:
    def get_table_profiling_query_full(self, table_name: str, schema: str, dialect: str = "mssql"):
        query = None
        if dialect == "mssql":
            query = MSSQL_PROFILING_QUERY_FULL.format(
                cols_to_ignore = tuple(COLS_TO_IGNORE),
                schema = schema, 
                table_name = table_name
            )       
        return query    


    # # @staticmethod
    # # def prepare_sqls(x):
    # #     if x["column_name"].lower() in COLS_TO_IGNORE:
    # #         return None

    # #     if x["column_name"].lower() in IDENTITY_COLUMNS or x["column_name"].lower().startswith("id_") or x["column_name"].lower().endswith("_id"):
    # #         return f"SELECT '{x['column_name']}' as column_name, COUNT(DISTINCT {x['column_name']}) FROM {x['table_name']}"

    # #     if x["column_type"]=="nvarchar":
    # #         return f"SELECT '{x['column_name']}' as column_name, TOP 10 {x['column_name']}, COUNT({x['column_name']}) as cnt FROM {x['table_name']} WHERE {x['column_name']} IS NOT NULL GROUP BY {x['column_name']} ORDER BY COUNT({x['column_name']}) DESC"

    # #     if x["column_name"].lower() in DATE_COLUMNS or x["column_type"] in ("date", "integer", "float"):
    # #         return f"SELECT '{x['column_name']}' as column_name, MIN({x['column_name']}) AS Min, MAX({x['column_name']}) AS Max FROM {x['table_name']}"

    # #     return None

    # # def get_col_sql_type(self, x):
    # #     if x["column_name"].lower() in COLS_TO_IGNORE:
    # #         return None
        
    # #     if x["column_name"].lower() in IDENTITY_COLUMNS or x["column_name"].lower().startswith("id_") or x["column_name"].lower().endswith("_id"):
    # #         return "distinct"

    # #     if x["data_type"]=="nvarchar":
    # #         return "top_n"

    # #     if x["column_name"].lower() in DATE_COLUMNS or x["data_type"] in ("date"):
    # #         return "min_max"
        
    # #     if x["data_type"] in ("integer", "float"):
    # #         return "min_max"

    # # #     return None
        
    
    # # def get_sql_top_n(self, row):
    # #     sql_col_part = []
    # #     for c in row["column_name"]:
    # #         sql_col_part.append(
    # #             f"('{c}', CAST({c} AS NVARCHAR(255)))"
    # #         )

    # #     return f"""WITH column_values AS (
    # #                     SELECT v.column_name, v.value
    # #                     FROM {row['table_name']} t
    # #                     CROSS APPLY (VALUES
    # #                         {', '.join(sql_col_part)}
    # #                     ) v(column_name, value)
    # #                 )
    # #                 SELECT 
    # #                     column_name, 
    # #                     value,
    # #                     round((cnt*100.0)/(SUM(cnt) OVER(PARTITION BY column_name)),2) as pct_distribution 
    # #                 FROM (
    # #                     SELECT
    # #                         column_name,
    # #                         value,
    # #                         COUNT(*) cnt,
    # #                         ROW_NUMBER() OVER (
    # #                             PARTITION BY column_name
    # #                             ORDER BY COUNT(*) DESC
    # #                         ) rn
    # #                     FROM column_values
    # #                     WHERE value <> ''
    # #                     GROUP BY column_name, value
    # #                 ) x
    # #                 WHERE rn <= 10
    # #                 ORDER BY column_name, cnt DESC;"""
    
    # # def get_sql_min_max(self, row):
    # #     sql_col_part = []
    # #     for c in row["column_name"]:
    # #         sql_col_part.append(
    # #             f"('{c}', CAST({c} AS NVARCHAR(255)))"
    # #         )

    # #     return f"""WITH column_values AS (
    # #                     SELECT v.column_name, v.value
    # #                     FROM {row['table_name']} t
    # #                     CROSS APPLY (VALUES
    # #                         {', '.join(sql_col_part)}
    # #                     ) v(column_name, value)
    # #                 )
    # #                 SELECT
    # #                     column_name,
    # #                     MIN(value) AS min_value,
    # #                     MAX(value) AS max_value
    # #                 FROM column_values
    # #                 GROUP BY column_name;"""
    

    # # def get_sql_min_max_avg(self, row):
    # #     sql_col_part = []
    # #     for c in row["column_name"]:
    # #         sql_col_part.append(
    # #             f"('{c}', CAST({c} AS NVARCHAR(255)))"
    # #         )

    # #     return f"""WITH column_values AS (
    # #                     SELECT v.column_name, v.value
    # #                     FROM {row['table_name']} t
    # #                     CROSS APPLY (VALUES
    # #                         {', '.join(sql_col_part)}
    # #                     ) v(column_name, value)
    # #                 )
    # #                 SELECT
    # #                     column_name,
    # #                     MIN(value) AS min_value,
    # #                     MAX(value) AS max_value,
    # #                     AVG(value) AS avg_value
    # #                 FROM column_values
    # #                 GROUP BY column_name;"""
    
    # # def get_sql_distinct(self, row):
    # #     sql_col_part = []
    # #     for c in row["column_name"]:
    # #         sql_col_part.append(
    # #             f"('{c}', CAST({c} AS NVARCHAR(255)))"
    # #         )

    # #     return f"""WITH column_values AS (
    # #                     SELECT v.column_name, v.value
    # #                     FROM {row['table_name']} t
    # #                     CROSS APPLY (VALUES
    # #                         {', '.join(sql_col_part)}
    # #                     ) v(column_name, value)
    # #                 )
    # #                 SELECT
    # #                     column_name,
    # #                     COUNt(DISTINCT value) AS unique_external_ref
    # #                 FROM column_values
    # #                 GROUP BY column_name;"""
    
    
    # def get_sqls_based_on_datatypes(self):
    #     self.df["col_sql_type"] = self.df.apply(self.get_col_sql_type, axis=1)
        
    #     self.grouped_df = self.df.groupby(["table_name", "col_sql_type"])["column_name"].apply(list).reset_index()        

    #     def get_sql_based_on_type(row):
    #         if row["col_sql_type"] == "top_n":
    #             return self.get_sql_top_n(row)

    #         if row["col_sql_type"] == "distinct":
    #             return self.get_sql_distinct(row)

    #         if row["col_sql_type"] == "min_max":
    #             return self.get_sql_min_max(row)

    #         if row["col_sql_type"] == "min_max_avg":
    #             return self.get_sql_min_max_avg(row)

    #     self.grouped_df["sql_query"] = self.grouped_df.apply(get_sql_based_on_type, axis=1)
    #     return self.grouped_df
    
    # async def map_stats_with_columns(self):
    #     sqls = self.grouped_df["sql_query"].tolist()
    #     query_results = await get_table_from_sql_parallel(
    #         pool=self.pool, 
    #         db_name=self.db_name, 
    #         sql_queries=sqls, 
    #         row_limit=None, 
    #         query_timeout=120
    #     )

    #     full_df = pd.DataFrame()
    #     for res, (_, row) in zip(query_results, self.grouped_df.iterrows()):
    #         table_json, table_status, table_columns = get_table_and_status_and_columns(res)
    #         temp_df = pd.DataFrame(table_json)
    #         if table_status=="success":
    #             if row["col_sql_type"] == "min_max":
    #                 temp_df["numeric_stats"] = temp_df.apply(lambda x: {"min": x["min_value"], "max": x["max_value"]}, axis=1)
    #                 temp_df["range"] = temp_df.apply(lambda x: (x["min_value"], x["max_value"]), axis=1)
    #                 temp_df["table_name"] = row["table_name"]
    #                 temp_df.drop(["min_value", "max_value"], inplace=True, axis=1)
    #                 # temp_df["numeric_stats"] = temp_df["numeric_stats"].apply(lambda x: json.dumps(x))
    #                 # temp_df["range"] = temp_df["range"].apply(lambda x: json.dumps(x))
    #             if row["col_sql_type"] == "min_max_avg":
    #                 temp_df["numeric_stats"] = temp_df.apply(lambda x: {"min": x["min_value"], "max": x["max_value"], "avg": x["avg_value"]}, axis=1)
    #                 temp_df["range"] = temp_df.apply(lambda x: (x["min_value"], x["max_value"]), axis=1)
    #                 temp_df["table_name"] = row["table_name"]
    #                 temp_df.drop(["min_value", "max_value", "avg_value"], inplace=True, axis=1)
    #                 # temp_df["numeric_stats"] = temp_df["numeric_stats"].apply(lambda x: json.dumps(x))
    #                 # temp_df["range"] = temp_df["range"].apply(lambda x: json.dumps(x))
    #             if row["col_sql_type"] == "top_n":
    #                 temp_df["categorical_stats"] = temp_df.apply(lambda x: {x["value"]: x["pct_distribution"]}, axis=1)                
    #                 temp_df = temp_df.groupby("column_name")["categorical_stats"].apply(list).reset_index()
    #                 temp_df["unique_values"] = temp_df["categorical_stats"].apply(lambda x: [list(i.keys())[0] for i in x])
    #                 temp_df["table_name"] = row["table_name"]
    #                 # temp_df_grouped["categorical_stats"] = temp_df_grouped["categorical_stats"].apply(lambda x: json.dumps(x))
    #                 # temp_df_grouped["unique_values"] = temp_df_grouped["unique_values"].apply(lambda x: json.dumps(x))
    #             if row["col_sql_type"] == "distinct":
    #                 temp_df["table_name"] = row["table_name"]
                
    #             full_df = pd.concat([full_df, temp_df])

    #     print("#"*50)
    #     print(full_df.head())
    #     # if full_df.shape[0]>0:
    #     #     self.grouped_df = self.grouped_df.merge(full_df, on=["table_name", "column_name"], how="left")
    #     return full_df


    # def prepare_sqls_to_be_executed_on_dataabase(self):
    #     sql_queries = {}

    #     for tbl in self.df["table_name"].unique():
    #         sql_queries[tbl] = {"min_max": [], "distinct": [], "top_n": [], "min_max_avg": []}

    #     for _, row in self.df.iterrows():
    #         if type(row["sql_query"])==str:
    #             if "distinct" in row["sql_query"].lower():
    #                 sql_queries[row["table_name"]]["distinct"].append(row["sql_query"])
    #             if "avg" in row["sql_query"].lower():
    #                 sql_queries[row["table_name"]]["min_max_avg"].append(row["sql_query"])
    #             if "min" in row["sql_query"].lower():
    #                 sql_queries[row["table_name"]]["min_max"].append(row["sql_query"])
    #             if "desc" in row["sql_query"].lower():
    #                 sql_queries[row["table_name"]]["top_n"].append(row["sql_query"])
        
    #     return sql_queries





# async def get_column_stats(db_name: str, client_pool: BaseConnectionPool, table_name: str, table_columns: dict):
#     columns = table_columns.values()
#     sql_list = []

#     for c in columns:
#         if c.lower() in identity_columns:
#             sql = f"SELECT COUNT(DISTINCT {c}) FROM {table_name};"
#         elif c.lower() in datetime_columns:
#             sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max FROM {table_name};"
#         elif c.lower() in num_cols:
#             sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max, ROUND(AVG({c}), 2) as Mean FROM {table_name};"
#         else:
#             sql = f"SELECT TOP 3 {c}, COUNT({c}) as cnt FROM {table_name} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY COUNT({c}) DESC;"
#         sql_list.append(sql)

#     results = await get_table_from_sql_parallel(client_pool, db_name, sql_list)

#     col_results = []
#     for c, r in zip(columns, results):
#         if c.lower() in identity_columns:
#             numeric_stats = None
#             categorical_stats = None
#             unique_external_ref = {"unique count": f"{r.rows[0][0]:,}"}

#         elif c.lower() in datetime_columns:
#             numeric_stats = {
#                 "min": str(r.rows[0][0]),
#                 "max": str(r.rows[0][1])
#             }
#             categorical_stats = None
#             unique_external_ref = None

#         elif c.lower() in num_cols:
#             numeric_stats = {
#                 "min": r.rows[0][0],
#                 "max": r.rows[0][1],
#                 "mean": r.rows[0][2]
#             }
#             categorical_stats = None
#             unique_external_ref = None

#         else:
#             numeric_stats = None
#             categorical_stats = {str(k[0]): f"{k[1]:,}" for k in r.rows}
#             unique_external_ref = None

#         col_results.append(
#             {
#                 "column_name": c,
#                 "description": None,
#                 "numeric_stats": numeric_stats,
#                 "categorical_stats": categorical_stats,
#                 "unique_external_ref": unique_external_ref,
#                 "comment_stats": None
#             }
#         )
#     return col_results


# async def get_updated_metadata(db_name: str, client_pool: BaseConnectionPool, table_name: str, table_columns: dict, introduction_meta, update_categorical=False):
#     columns = table_columns.values()
#     sql_list = []

#     for c in columns:
#         if c.lower() in identity_columns:
#             sql = f"SELECT COUNT(DISTINCT {c}) FROM {table_name};"
#         elif c.lower() in datetime_columns:
#             sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max FROM {table_name};"
#         elif c.lower() in num_cols:
#             sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max, ROUND(AVG({c}), 2) as Mean FROM {table_name};"
#         else:
#             if update_categorical:
#                 sql = f"SELECT TOP 3 {c}, COUNT({c}) as cnt FROM {table_name} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY COUNT({c}) DESC;"
#             else: 
#                 sql = "SELECT 1"
        
#         sql_list.append(sql)

#     results = await get_table_from_sql_parallel(client_pool, db_name, sql_list)

#     columns_details = [i for i in introduction_meta["columns_metadata"] if i["table_name"]==table_name][0]["columns"]

#     col_results = []
#     for c, r in zip(columns, results):
#         if c.lower() in identity_columns:
#             numeric_stats = None
#             categorical_stats = None
#             unique_external_ref = {"unique count": f"{r.rows[0][0]:,}"}

#         elif c.lower() in datetime_columns:
#             numeric_stats = {
#                 "min": str(r.rows[0][0]),
#                 "max": str(r.rows[0][1])
#             }
#             categorical_stats = None
#             unique_external_ref = None

#         elif c.lower() in num_cols:
#             numeric_stats = {
#                 "min": r.rows[0][0],
#                 "max": r.rows[0][1],
#                 "mean": r.rows[0][2]
#             }
#             categorical_stats = None
#             unique_external_ref = None
#         else:
#             if update_categorical:
#                 numeric_stats = None
#                 categorical_stats = {str(k[0]): f"{k[1]:,}" for k in r.rows}
#                 unique_external_ref = None
#             else:
#                 # try:
#                 numeric_stats = None
#                 categorical_stats = [s for s in columns_details if s["column_name"]==c][0]["categorical_stats"]
#                 unique_external_ref = None


# ##############################################
#                 # except Exception as e:
#                 #     numeric_stats = None
#                 #     categorical_stats = None
#                 #     unique_external_ref = None
#                 #     print(f"Categorical stats not generated properly for {columns_details} - {repr(e)}")
                
#         col_results.append(
#             {
#                 "column_name": c,
#                 "description": None,
#                 "numeric_stats": numeric_stats,
#                 "categorical_stats": categorical_stats,
#                 "unique_external_ref": unique_external_ref,
#                 "comment_stats": None
#             }
#         )
#     return col_results




async def get_column_stats(db_name: str, client_pool: BaseConnectionPool, table_name: str, table_columns: dict):
    columns = table_columns.values()
    sql_list = []

    for c in columns:
        if c.lower() in identity_columns:
            sql = f"SELECT COUNT(DISTINCT {c}) FROM {table_name};"
        elif c.lower() in datetime_columns:
            sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max FROM {table_name};"
        elif c.lower() in num_cols:
            sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max, ROUND(AVG({c}), 2) as Mean FROM {table_name};"
        else:
            sql = f"SELECT TOP 3 {c}, COUNT({c}) as cnt FROM {table_name} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY COUNT({c}) DESC;"
        sql_list.append(sql)

    results = await get_table_from_sql_parallel(client_pool, db_name, sql_list)

    col_results = []
    for c, r in zip(columns, results):
        if c.lower() in identity_columns:
            numeric_stats = None
            categorical_stats = None
            unique_external_ref = {"unique count": f"{r.rows[0][0]:,}"}

        elif c.lower() in datetime_columns:
            numeric_stats = {
                "min": str(r.rows[0][0]),
                "max": str(r.rows[0][1])
            }
            categorical_stats = None
            unique_external_ref = None

        elif c.lower() in num_cols:
            numeric_stats = {
                "min": r.rows[0][0],
                "max": r.rows[0][1],
                "mean": r.rows[0][2]
            }
            categorical_stats = None
            unique_external_ref = None

        else:
            numeric_stats = None
            categorical_stats = {str(k[0]): f"{k[1]:,}" for k in r.rows}
            unique_external_ref = None

        col_results.append(
            {
                "column_name": c,
                "description": None,
                "numeric_stats": numeric_stats,
                "categorical_stats": categorical_stats,
                "unique_external_ref": unique_external_ref,
                "comment_stats": None
            }
        )
    return col_results


async def get_updated_metadata(db_name: str, client_pool: BaseConnectionPool, table_name: str, table_columns: dict, introduction_meta, update_categorical=False):
    columns = table_columns.values()
    sql_list = []

    for c in columns:
        if c.lower() in identity_columns:
            sql = f"SELECT COUNT(DISTINCT {c}) FROM {table_name};"
        elif c.lower() in datetime_columns:
            sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max FROM {table_name};"
        elif c.lower() in num_cols:
            sql = f"SELECT MIN({c}) AS Min, MAX({c}) AS Max, ROUND(AVG({c}), 2) as Mean FROM {table_name};"
        else:
            if update_categorical:
                sql = f"SELECT TOP 3 {c}, COUNT({c}) as cnt FROM {table_name} WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY COUNT({c}) DESC;"
            else: 
                sql = "SELECT 1"
        
        sql_list.append(sql)

    results = await get_table_from_sql_parallel(client_pool, db_name, sql_list)
############################
    # SAFE LOOKUP: Get table metadata, or None if not found
    table_meta_list = introduction_meta.get("columns_metadata", [])
    table_info = next((i for i in table_meta_list if i["table_name"] == table_name), None)
    
    # If table isn't in metadata, columns_details becomes an empty list
    columns_details = table_info.get("columns", []) if table_info else []
######################
    # columns_details = [i for i in introduction_meta["columns_metadata"] if i["table_name"]==table_name][0]["columns"]

    col_results = []
    for c, r in zip(columns, results):
        if c.lower() in identity_columns:
            numeric_stats = None
            categorical_stats = None
            unique_external_ref = {"unique count": f"{r.rows[0][0]:,}"}

        elif c.lower() in datetime_columns:
            numeric_stats = {
                "min": str(r.rows[0][0]),
                "max": str(r.rows[0][1])
            }
            categorical_stats = None
            unique_external_ref = None

        elif c.lower() in num_cols:
            numeric_stats = {
                "min": r.rows[0][0],
                "max": r.rows[0][1],
                "mean": r.rows[0][2]
            }
            categorical_stats = None
            unique_external_ref = None
        else:
            if update_categorical:
                numeric_stats = None
                categorical_stats = {str(k[0]): f"{k[1]:,}" for k in r.rows}
                unique_external_ref = None
            else:
                # # try:
                # numeric_stats = None
                # categorical_stats = [s for s in columns_details if s["column_name"]==c][0]["categorical_stats"]
                # unique_external_ref = None
                # SAFE LOOKUP: Find the specific column in the metadata list
 ############################               
                numeric_stats = None
                unique_external_ref = None
                matching_col = next((s for s in columns_details if s["column_name"] == c), None)
                
                if matching_col:
                    categorical_stats = matching_col.get("categorical_stats")
                else:
                    # Column exists in DB but not in Metadata JSON
                    categorical_stats = None 


##############################################
                # except Exception as e:
                #     numeric_stats = None
                #     categorical_stats = None
                #     unique_external_ref = None
                #     print(f"Categorical stats not generated properly for {columns_details} - {repr(e)}")
                
        col_results.append(
            {
                "column_name": c,
                "description": None,
                "numeric_stats": numeric_stats,
                "categorical_stats": categorical_stats,
                "unique_external_ref": unique_external_ref,
                "comment_stats": None
            }
        )
    return col_results


