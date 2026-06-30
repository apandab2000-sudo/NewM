from fastapi import APIRouter, Depends, HTTPException
from app.models import DBInitRequest, TableFetchRequest, CorrectionRequest, SaveBusinessContext, ConfigureFilters
# from app.databases.connections import ClientConnection
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.connections import (
    get_db_async,
    nosql_client, 
    client_pool_manager,
    vector_client
    # get_nosql_client,
    # client_connection_pool,
    # get_vector_db
)
from app.databases.internal_sql_operations import InternalSQLHelper
from app.logger import get_logger
from app.core.setups.helper import UserConfig, SchemaInfoGenerator, GenerateSchemaBase, UniqueCategoriesTable
from .auth import get_current_user, check_admin
import pandas as pd
import os
import yaml
from app.databases.vector_operations import VectorStore
import json
from app.appConfig import settings
from sqlalchemy import text
import pandas as pd
from app.core.dashboards.introductions import IntroductionTablesCreator
from app.databases.client_sql.operations import get_table_from_sql_parallel, get_table_and_status_and_columns
import asyncio
from app.core.helper import make_json_safe


logger = get_logger()


router = APIRouter(prefix="/iod/self-serve", tags=["Self Serve"])


@router.post('/{db_name}/setup-filters', status_code=201)
async def configure_filters_for_dataset(
    db_name: str,
    payload: ConfigureFilters,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=db_name)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    dataset_details, connection_details = fectched_details

    if not dataset_details.tables_to_use:
        raise HTTPException(status_code=404, detail="Configure the tables for Dataset first")
    
    db_config = {
        "username": connection_details.username,
        "password": connection_details.password,
        "host": connection_details.host,
        "port": connection_details.port,
        "database": connection_details.db
    }

    pool = client_pool_manager.get_pool_sync(
        db_connection_id=dataset_details.connection_id, 
        dialect=connection_details.dialect, 
        **db_config
    )
    pool.init_sync_engine()

    try:
        with open("clientConfig.yaml", "r") as f:
            client_config = yaml.safe_load(f)
    except Exception as e:
        client_config = {}
        print(f"CLient config read error - {repr(e)}")
    
    if not client_config:
        client_config = {}

    if not client_config.get(db_name):
        client_config[db_name] = {}

    if not client_config[db_name].get("CONVERSATION_FILTERS"):
        client_config[db_name]["CONVERSATION_FILTERS"] = {}

    if len(payload.table_column_filters)==1:
        client_config[db_name]["CONVERSATION_FILTERS"] = {
            "table_name": payload.table_column_filters[0].table, 
            "columns": [c.model_dump() for c in payload.table_column_filters[0].columns],
            "filters_table": str(dataset_details.db_name)+"_filters" 
        }        

        with open("clientConfig.yaml", 'w') as file:
            yaml.safe_dump(client_config, file, default_flow_style=False)
       
        columns_list = []
        order_by_list = []
        cols_for_indexing = []
        for tcf in payload.table_column_filters:
            for col in tcf.columns:
                columns_list.append(col.column_name)
                if col.order_by:
                    order_by_list.append(f"{col.column_name} {col.order_by}")
                if col.indexed:
                    cols_for_indexing.append(col.column_name)
        
        columns_list = list(map(lambda x: f"CAST ({x} as VARCHAR(100)) AS {x}", columns_list))
        
        columns_list_str = ", ".join(columns_list)
        print(columns_list_str)
        order_by_list_str = ", ".join(order_by_list) if order_by_list else None
        print(order_by_list_str)
        filters_table_name = f"{dataset_details.db_name}_filters"
        
        base_sql_query = f"SELECT DISTINCT {columns_list_str} INTO {dataset_details.db_schema}.{filters_table_name} FROM {dataset_details.db_schema}.{payload.table_column_filters[0].table};" 
        
        index_queries = []
        for col in cols_for_indexing:
            index_queries.append(f"CREATE INDEX IX_{filters_table_name}_{col} on {dataset_details.db_schema}.{filters_table_name} ({col});")
        

    filters_creation_status = False
    with pool.engine.begin() as connection:
        try:
            connection.execute(text(base_sql_query))
            filters_creation_status = True
        except Exception as e:
            logger.error(f"Filters tables not executed properly - {repr(e)}")

    if filters_creation_status and index_queries:
        for query in index_queries:
            with pool.engine.begin() as connection:
                try:
                    connection.execute(text(query))
                except Exception as e:
                    logger.error(f"index query not executed properly - {repr(e)}")
    else:
        logger.warning("Filters tbale not created or no index queries specified")
        
    await pool.dispose_sync()
    return {
        "qsql_query": base_sql_query,
        "index_queries": index_queries
    }



# @router.post("/sql/create_database", status_code=201, dependencies=[Depends(check_admin)])
# async def store_user_database_details(
#     data: DBInitRequest, 
#     session:AsyncSession = Depends(get_db_async)
# ):
#     i_data = InternalSQLHelper(session)
#     db_details = await i_data.create_dataset(data.dbname)

#     if not db_details:
#         raise HTTPException(detail="Project does not exists", status_code=400)

#     client_database_details = {
#         "USERNAME": settings.client_sql_username, 
#         "PASSWORD": settings.client_sql_password, 
#         "HOST": settings.client_sql_host, 
#         "PORT": settings.client_sql_port, 
#         "DATABASE": settings.client_sql_database
#     }

#     client_connection_object = ClientConnection(**client_database_details)
#     check_connectivity = client_connection_object.check_connectivity()
#     if not check_connectivity:
#         raise HTTPException(status_code=400, detail="Connection details Invalid")

#     available_tables = client_connection_object.get_available_tables()

#     if len(available_tables)==0:
#         raise HTTPException(status_code=400, detail="No Tables found in the database")

#     config_object = UserConfig()
#     config_object.setup_config_for_user(
#         dbname=data.dbname, 
#         available_tables=[]
#     )
#     return {
#         "dbname": data.dbname,
#         "table_list": available_tables
#     }


@router.post("/{db_name}/configure-data-schema", status_code=200, dependencies=[Depends(check_admin)])
async def configure_data_schema(
    db_name: str,
    data: TableFetchRequest, 
    session:AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=db_name)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    dataset_details, connection_details = fectched_details

    if not dataset_details.tables_to_use:
        raise HTTPException(status_code=404, detail="Configure the tables for Dataset first")

    db_config = {
        "username": connection_details.username,
        "password": connection_details.password,
        "host": connection_details.host,
        "port": connection_details.port,
        "database": connection_details.db
    }

    # pool = client_pool_manager.get_pool_sync(
    #     db_connection_id=dataset_details.connection_id, 
    #     dialect=connection_details.dialect, 
    #     **db_config
    # )
    # pool.init_sync_engine()

    async_pool = await client_pool_manager.get_pool(
        db_connection_id=dataset_details.connection_id, 
        dialect=connection_details.dialect, 
        **db_config
    )

    # table_details = []
    # relationships = []
    # for table in dataset_details.tables_to_use:
    #     columns_info = pool.get_columns_for_table(table=table, schema=dataset_details.db_schema)
    #     primary_key_info = pool.get_primary_key_constraints(table=table)
    #     foreign_key_info = pool.get_foreign_key_constraints(table=table)
    #     rels = pool.get_relationships(table=table)
    #     relationships.extend(rels)

    #     column_details = []
    #     for col_details in columns_info:
    #         col_name = col_details["column_name"]
    #         primary_key = col_name in primary_key_info
    #         foreign_key = col_name in foreign_key_info
    #         column_details.append({
    #             "table_name": col_details["table_name"],
    #             "column_name": col_details["column_name"],
    #             "data_type": col_details["data_type"],
    #             "primary_key": primary_key,
    #             "foreign_key": foreign_key
    #         })
    #     table_details.extend(column_details)

    # df = pd.DataFrame(table_details)

    # base_path = f"business_data/{db_name}/"
    # if not os.path.exists(base_path):
    #     os.makedirs(base_path, exist_ok=True)

    # df.to_csv(base_path+"table_column_mappings.csv", index=False)
    # if relationships:
    #     relationship_df = pd.DataFrame(relationships)
    #     relationship_df.to_csv(base_path+"table_relationships.csv", index=False)

    itc = IntroductionTablesCreator()

    sql_queries = []
    for table in dataset_details.tables_to_use: 
        sql_query = itc.get_table_profiling_query_full(table, dataset_details.db_schema, connection_details.dialect)
        if sql_query:
            sql_queries.append(sql_query)

    query_results = await get_table_from_sql_parallel(async_pool, db_name, sql_queries, row_limit=None, query_timeout=60)

    results = []
    for qr in query_results:
        table_json, table_status, table_columns = get_table_and_status_and_columns(qr)
        
        print(qr.status)
        print(qr.error)

        if table_status == "success":
            results.append(table_json)
    # grouped_df = itc.get_sqls_based_on_datatypes()
    # # grouped_df.to_csv(base_path+"table_mapping_sqls.csv", index=False)
    
    # final_data = await itc.map_stats_with_columns()
    # # print(final_data.head())
    # # final_data.to_csv(base_path+"table_mapping_sql3434.csv", index=False)
    # if final_data.shape[0]>0:
    #     df = df.merge(final_data, on=["table_name", "column_name"], how="left")
    

    # non_json_cols = ["table_name","column_name","data_type","primary_key","foreign_key","col_sql_type"]
    # for col in df.columns:
    #     if col not in non_json_cols:
    #         df[col] = df[col].apply(lambda x: json.dumps(x) if x else pd.NA)
            
    # df.to_csv(base_path+"table_column_mappings.csv", index=False)
    
    # await pool.dispose_sync()

    # json_safe = make_json_safe(df.to_dict(orient="records"))
    
    return {
        "db_name": db_name,
        "query_results": results 
    }


def load_json(x):
    try:
        return json.loads(x)
    except Exception as e:
        return pd.NA
        

@router.get("/{db_name}/setup-schema-string", status_code=200, dependencies=[Depends(check_admin)])
async def configure_data_schema(
    db_name: str,
):
    base_path = f"business_data/{db_name}/"
    df = pd.read_csv(base_path+"table_column_mappings.csv")
    
    non_json_cols = ["table_name","column_name","data_type","primary_key","foreign_key","col_sql_type"]
    for col in df.columns:
        if col not in non_json_cols:
            df[col] = df[col].apply(lambda x: load_json(x))

    table_stats = []
    for tbl in df["table_name"].unique():
        column_stats = []
        temp = df[df["table_name"]==tbl]
        for i_, row in temp.iterrows():
            if row["col_sql_type"] == "top_n":
                col_stat = f"{row['column_name']} {row['data_type']} - sample_value ({', '.join(row['unique_values'])})"
            elif row["col_sql_type"] in ("min_max", "min_max_avg"):
                col_stat = f"{row['column_name']} {row['data_type']} - range ({', '.join(row['range'])})"
            else:
                col_stat = f"{row['column_name']} {row['data_type']}"
            column_stats.append(col_stat)

        column_stat_string = ",\n".join(column_stats)
        table_stat = f"Table - {tbl} ({column_stat_string})"
        primary_key_string = f"\nPrimary Key - {temp['primary_key'].unique()[0]}" if temp['primary_key'].nunique()==1 else ""  
        table_stat = table_stat+primary_key_string
        table_stats.append(table_stat)

    schema_str = "\n\n".join(table_stats)
    
    schema_string_path = "app/core/schema_strings"
    with open(os.path.join(schema_string_path, f"{db_name}.txt"), "w", encoding="utf-8") as f:
        f.write(schema_str)

    return {"schema_string": schema_str}

    # os.makedirs(base_business_context_path, exist_ok=True)

# @router.get("/generate-schema-strings", status_code=200, dependencies=[Depends(check_admin)])
# async def setup_schema_strings(session: AsyncSession = Depends(get_db_async)):



def writes_metadata_files(dbname: str, table_details: list, schema_relationships: list):
    base_location = os.path.join(f"business_data/{dbname}/metadata/")
    os.makedirs(base_location, exist_ok=True)
    for table_detail in table_details:
        df = pd.DataFrame([dict(i) for i in table_detail.column_details])
        df.to_csv(os.path.join(base_location, table_detail.table + ".csv"), index=False)

    relationship_df = pd.DataFrame(schema_relationships)
    relationship_df.to_csv(os.path.join(base_location, "schema_relations.csv"))


@router.post("/corrections_and_business_context/", status_code=200, dependencies=[Depends(check_admin)])
async def generate_business_context(
    data: CorrectionRequest, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    db_details = await i_data.get_db_details_from_dbname(data.dbname)
    schema_relationships = data.relationships
    table_details = data.table_details

    # adding write data to disk as background task
    writes_metadata_files(data.dbname, table_details, schema_relationships)

    with open("app/clientConfig.yaml", "r") as f:
        current_config = yaml.safe_load(f)

    client_database_details = {
        "USERNAME": settings.client_sql_username, 
        "PASSWORD": settings.client_sql_password, 
        "HOST": settings.client_sql_host, 
        "PORT": settings.client_sql_port, 
        "DATABASE": settings.client_sql_database
    }

    client_connection_object = ClientConnection(**client_database_details)

    ########################## Setting Up Schema String ####################################
    schema_object = GenerateSchemaBase(client=data.dbname, client_engine=client_connection_object.engine,
                                       relationships=schema_relationships, table_details=table_details)
    schema_str = schema_object.get_schema_str()

    base_business_context_path = f"business_data/{data.dbname}/"
    os.makedirs(base_business_context_path, exist_ok=True)

    ######################### CATEGORICAL COLUMNS - Finding UNIQUE VALUES ################################
    uct = UniqueCategoriesTable(data.dbname, table_details, client_connection_object.engine)
    table_query_results = uct.get_sql_for_unique_categories_per_table()
    unique_value_col_table_mappings = {k:pd.DataFrame(v).groupby("col_name")["unique_value"].apply(list).reset_index().to_dict(orient="records")
                 for k, v in table_query_results.items()}

    if not os.path.exists(os.path.join(base_business_context_path, "business_context.json")):
        results = {}
        results["unique_value_col_table_mappings"] = unique_value_col_table_mappings
        with open(os.path.join(base_business_context_path, "business_context.json"), "w") as f:
            json.dump(results, f)
    else:
        with open(os.path.join(base_business_context_path, "business_context.json"), "r") as f:
            results = json.load(f)
    
    return {
        "db_id": data.dbname,
        **results
    }


# @router.post("/iod/setup/save_business_context/", status_code=200, dependencies=[Depends(get_current_user)])
# async def save_user_corrections(
#     data: SaveBusinessContext, 
#     session: AsyncSession = Depends(get_db_async)
# ):
#     i_data = InternalSQLHelper(session)
#     db_details = await i_data.get_db_details_from_dbname(data.dbname)

#     # # Validate connection_type
#     # if data.connection_type not in ["mssql", "flat_file"]:
#     #     logger.error(f"Invalid connection_type: {data.connection_type}. Must be 'mssql' or 'flat_file'.")
#     #     raise HTTPException(status_code=400, detail="Invalid connection_type. Must be 'mssql' or 'flat_file'.")

#     # base_business_context_path = os.path.join("business_data", data.dbname,
#     #                                              "business_context.json")

#     # business_context = data.model_dump()
    
#     # with open(base_business_context_path, "r") as f:
#     #     existing_business_context = json.load(f)

#     # for k in business_context.keys():
#     #     existing_business_context[k] = business_context[k]

#     # with open(base_business_context_path, "w") as f:
#     #     json.dump(existing_business_context, f)

#     ############################# WRITING DATA TO VECTOR DB #################################
#     vector_client = vector_client
#     vector_client = VectorStore(vector_client)
#     similarity_metric = "cosine"
#     vector_dimensions = 384
#     collection_details, status = await vector_client.ensure_collection(data.dbname,
#                                                                        similarity_metric,
#                                                                        vector_dimensions)
#     collection_details = await vector_client.client.get_collection(data.dbname)
#     if not collection_details:
#         logger.warning("Collection was not created successfully")
#         raise HTTPException(detail="Collection was not created successfully", status_code=400)

    
#     with open(f"business_data/{data.dbname}/business_context.json") as f:
#         existing_business_context = json.load(f)
    
#     sample_questions = existing_business_context["sample_questions"]
#     ######## WRITING SAMPLE QUESTIONS ##############
#     if len(sample_questions)>0:
#         print(len(sample_questions))
#         data_points = [dict(i) for i in sample_questions]
#         data_upsert_status = await vector_client.upsert_data(data_points)

#         print(data_upsert_status)

#     ######## WRITING COLUMN UNIQUE VALUES ##############
#     if existing_business_context.get("unique_value_col_table_mappings"):
#         unique_value_col_table_mappings = existing_business_context.get("unique_value_col_table_mappings")
#         col_data = []
#         for k, v in unique_value_col_table_mappings.items():
#             col_data.extend(v)
#         data_points = []
#         for i in col_data:
#             for v in i["unique_value"]:
#                 data_points.append({
#                     "unique_value": v,
#                     "col_name": i["col_name"]
#                 })
#         data_upsert_status = await vector_client.upsert_data_column_context(data_points)
#     else:
#         data_upsert_status = False
#         print(" ############# NO JSON DATA FOUND ################")

#     return {
#         "dbname": data.dbname,
#         "end_point_url": "http://192.168.130.182:5011",
#         "data_upsert_status_column_context": data_upsert_status
#     }
