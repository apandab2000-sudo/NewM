from fastapi import APIRouter, Depends, HTTPException, Query, Path
from app.core.setups.config_setup import ConfigGenerationHelper
# from app.core.setups.config_setup import ConfigGenerationHelper
from app.core.setups.introductions import IntroductionHelper
from app.core.setups.metadata_setup import MetaDataSetup
from app.core.setups.schemas import SchemaGenerationHelper
from app.models import TableFetchRequest, CorrectionRequest, ConfigureFilters
# from app.databases.connections import ClientConnection
from sqlalchemy.ext.asyncio import AsyncSession
# from app.databases.connections import (
#     get_db_async,
#     nosql_client, 
#     client_pool_manager,
#     vector_client
#     # get_nosql_client,
#     # client_connection_pool,
#     # get_vector_db
# )
from app.databases.application_sql.operations import InternalSQLHelper
from app.logger import get_logger
from app.core.setups.helper import GenerateSchemaBase, UniqueCategoriesTable
from .auth import get_current_user, check_admin
import pandas as pd
import os
import yaml
import json
from app.appConfig import settings
from sqlalchemy import text
import pandas as pd
from app.core.dashboards.introductions import IntroductionTablesCreator
from app.databases.client_sql.operations import get_table_from_sql_parallel, get_table_and_status_and_columns
from app.api_models.setups import ConfigureTableColumnMetadataRequest, MetadatataTableUpdateRequest, MetadataTableResponse
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.dependencies import get_db_async, get_pool, client_pool_manager, vector_pool_manager
from app.logger import get_logger
import asyncio
from app.core.setups.vectors.vectors import VectorStoreSetupClient
import pathlib


logger = get_logger(__name__)


router = APIRouter(prefix="/iod/self-serve", tags=["Self Serve"])


@router.post('/{db_name}/setup-filters', status_code=201, deprecated=True)
async def configure_filters_for_dataset(
    db_name: str,
    payload: ConfigureFilters,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=db_name)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB CConnection not found") 
    
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
#     db_details = await i_data.create_dataset(data.db_name)

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
#         db_name=data.db_name, 
#         available_tables=[]
#     )
#     return {
#         "db_name": data.db_name,
#         "table_list": available_tables
#     }


@router.post("/{db_name}/configure-data-schema", status_code=200, dependencies=[Depends(check_admin)], deprecated=True)
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

    pool = client_pool_manager.get_pool_sync(
        db_connection_id=dataset_details.connection_id, 
        dialect=connection_details.dialect, 
        **db_config
    )
    pool.init_sync_engine()

    async_pool = await client_pool_manager.get_pool(
        db_connection_id=dataset_details.connection_id, 
        dialect=connection_details.dialect, 
        **db_config
    )

    table_details = []
    relationships = []
    for table in dataset_details.tables_to_use:
        columns_info = pool.get_columns_for_table(table=table, schema=dataset_details.db_schema)
        primary_key_info = pool.get_primary_key_constraints(table=table)
        foreign_key_info = pool.get_foreign_key_constraints(table=table)
        rels = pool.get_relationships(table=table)
        relationships.extend(rels)

        column_details = []
        for col_details in columns_info:
            col_name = col_details["column_name"]
            primary_key = col_name in primary_key_info
            foreign_key = col_name in foreign_key_info
            column_details.append({
                "table_name": col_details["table_name"],
                "column_name": col_details["column_name"],
                "data_type": col_details["data_type"],
                "primary_key": primary_key,
                "foreign_key": foreign_key,
                "col_sql_type": "none", # Placeholder
            })
        table_details.extend(column_details)

    df = pd.DataFrame(table_details)

    base_path = f"business_data/{db_name}/"
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)

    df.to_csv(base_path+"table_column_mappings.csv", index=False)
    if relationships:
        relationship_df = pd.DataFrame(relationships)
        relationship_df.to_csv(base_path+"table_relationships.csv", index=False)

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
        

@router.get("/{db_name}/setup-schema-string", status_code=200, dependencies=[Depends(check_admin)], deprecated=True)
async def configure_data_schema(
    db_name: str,
):
    base_path = f"business_data/{db_name}/"
    df = pd.read_csv(base_path+"table_column_mappings.csv")

    if not os.path.exists(base_path + "table_column_mappings.csv"):
        raise HTTPException(status_code=400, detail="Schema has not been configured yet. Please run configure-data-schema first.")
    
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



def writes_metadata_files(db_name: str, table_details: list, schema_relationships: list):
    base_location = os.path.join(f"business_data/{db_name}/metadata/")
    os.makedirs(base_location, exist_ok=True)
    for table_detail in table_details:
        df = pd.DataFrame([dict(i) for i in table_detail.column_details])
        df.to_csv(os.path.join(base_location, table_detail.table + ".csv"), index=False)

    relationship_df = pd.DataFrame(schema_relationships)
    relationship_df.to_csv(os.path.join(base_location, "schema_relations.csv"))


@router.post("/corrections_and_business_context/", status_code=200, dependencies=[Depends(check_admin)], deprecated=True)
async def generate_business_context(
    data: CorrectionRequest, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    db_details = await i_data.get_db_details_from_dbname(data.db_name)
    schema_relationships = data.relationships
    table_details = data.table_details

    # adding write data to disk as background task
    writes_metadata_files(data.db_name, table_details, schema_relationships)

    with open("app/clientConfig.yaml", "r") as f:
        current_config = yaml.safe_load(f)

    client_database_details = {
        "USERNAME": settings.client_sql_username, 
        "PASSWORD": settings.client_sql_password, 
        "HOST": settings.client_sql_host, 
        "PORT": settings.client_sql_port, 
        "DATABASE": settings.client_sql_database
    }

    # client_connection_object = ClientConnection(**client_database_details)
    client_connection_object = "ABC"

    ########################## Setting Up Schema String ####################################
    schema_object = GenerateSchemaBase(client=data.db_name, client_engine=client_connection_object.engine,
                                       relationships=schema_relationships, table_details=table_details)
    schema_str = schema_object.get_schema_str()

    base_business_context_path = f"business_data/{data.db_name}/"
    os.makedirs(base_business_context_path, exist_ok=True)

    ######################### CATEGORICAL COLUMNS - Finding UNIQUE VALUES ################################
    uct = UniqueCategoriesTable(data.db_name, table_details, client_connection_object.engine)
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
        "db_id": data.db_name,
        **results
    }


# @router.post("/iod/setup/save_business_context/", status_code=200, dependencies=[Depends(get_current_user)], deprecated=True)
# async def save_user_corrections(
#     data: SaveBusinessContext, 
#     session: AsyncSession = Depends(get_db_async)
# ):
#     i_data = InternalSQLHelper(session)
#     db_details = await i_data.get_db_details_from_dbname(data.db_name)

#     # # Validate connection_type
#     # if data.connection_type not in ["mssql", "flat_file"]:
#     #     logger.error(f"Invalid connection_type: {data.connection_type}. Must be 'mssql' or 'flat_file'.")
#     #     raise HTTPException(status_code=400, detail="Invalid connection_type. Must be 'mssql' or 'flat_file'.")

#     # base_business_context_path = os.path.join("business_data", data.db_name,
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
#     collection_details, status = await vector_client.ensure_collection(data.db_name,
#                                                                        similarity_metric,
#                                                                        vector_dimensions)
#     collection_details = await vector_client.client.get_collection(data.db_name)
#     if not collection_details:
#         logger.warning("Collection was not created successfully")
#         raise HTTPException(detail="Collection was not created successfully", status_code=400)

    
#     with open(f"business_data/{data.db_name}/business_context.json") as f:
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
#         "db_name": data.db_name,
#         "end_point_url": "http://192.168.130.182:5011",
#         "data_upsert_status_column_context": data_upsert_status
#     }


@router.post(
    "/{db_name}/configure-table-column-metadata",
    description="Configure table column metadata such as data types, primary key, foreign key, and unique values. This endpoint is used to set up the schema information for a given database connection. The metadata is stored in a CSV file for later use in generating schema strings and providing context to the LLM.",
    summary="Configure table column metadata for a database connection",
    response_description="Metadata configuration status",
    responses = {
        201: {"description": "Metadata configured successfully"},
        400: {"description": "Invalid input data or database connection"},
        404: {"description": "Database connection not found"}
    },
    status_code=201,
    dependencies=[Depends(check_admin)]
)
async def configure_tables_columns_metadata(
    data: ConfigureTableColumnMetadataRequest, 
    dbname: str = Query(..., description="The name of the dataset for which to configure table column metadata."),
    replace_existing: bool = Query(default=False, description="Whether to replace existing metadata if it exists. Default is False."),
    db_session:AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset, connection = await dataset_helper.get_dataset_and_connection_details(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    client_pool = await get_pool(dataset, connection)

    try:    
        metadata_setup_helper = MetaDataSetup(dbname, client_pool)
        await metadata_setup_helper.generate_metatdata(
            dialect=connection.dialect, 
            schema=dataset.db_schema, 
            tables_list=data.table_list,
            replace_existing=replace_existing
        )
        return {"message": "Metadata configured successfully"}
    except Exception as e:
        logger.error(f"Error generating metadata: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error generating metadata: {repr(e)}")


@router.post(
    "/{db_name}/setup-introduction-data",
    description="Set up introduction page data for given dataset. TThis will show Business Information, Formulas, and other relevant details.",
    summary="Set up introduction page data for a dataset",
    response_description="Introduction data setup status",
    responses = {
        201: {"description": "Introduction data set up successfully"},
        400: {"description": "Invalid input data or database connection"},
        404: {"description": "Dataset not found"}
    },
    status_code=201,
    dependencies=[Depends(check_admin)]
)
async def setup_introduction_page_data(
    dbname: str = Query(..., description="The name of the dataset for which to set up introduction page data."),
    replace_existing: bool = Query(default=False, description="Whether to replace existing introduction data if it exists. Default is False."),
    db_session:AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        logger.error(f"Dataset not found for dbname: {dbname}", extra={"event_type": "dataset_not_found", "dbname": dbname})
        raise HTTPException(status_code=404, detail="Dataset not found")

    introduction_helper = IntroductionHelper(dbname)
    try:
        introduction_helper.setup_introduction(replace_existing=replace_existing)
        return {"message": "Introduction data set up successfully"}
    except Exception as e:
        logger.error(f"Error setting up introduction data: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error setting up introduction data: {repr(e)}")


@router.post(
    "/{db_name}/setup-schema-strings",
    description="Set up schema strings for a given dataset. This will generate human-readable schema strings in yaml format",
    summary="Set up schema strings for a dataset",
    response_description="Schema string setup status",
    responses = {
        201: {"description": "Schema strings set up successfully"},
        400: {"description": "Invalid input data or database connection"},
        404: {"description": "Dataset not found"}
    },
    status_code=201,
)
async def setup_schema_strings(
    dbname: str = Query(..., description="The name of the dataset for which to set up schema strings."),
    replace_existing: bool = Query(default=False, description="Whether to replace existing schema strings if they exist. Default is False."),
    db_session:AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        logger.error(f"Dataset not found for dbname: {dbname}", extra={"event_type": "dataset_not_found", "dbname": dbname})
        raise HTTPException(status_code=404, detail="Dataset not found")

    schema_helper = SchemaGenerationHelper(dbname)

    try:
        schema_helper.setup_schema_string(replace_existing=replace_existing)
        return {"message": "Schema strings set up successfully"}
    except Exception as e:
        logger.error(f"Error setting up schema strings: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error setting up schema strings: {repr(e)}")


@router.post(
    "/{db_name}/full-config-file",
    description="Set up full configuration file for a given dataset",
    summary="Set up full configuration file for a dataset",
    response_description="Full configuration file setup status",
    responses = {
        201: {"description": "Full configuration file set up successfully"},
        400: {"description": "Invalid input data or database connection"},
        404: {"description": "Dataset not found"}
    },
    status_code=201,
)
async def setup_config_file_data(
    data: ConfigureTableColumnMetadataRequest, 
    dbname: str = Query(..., description="The name of the dataset for which to set up schema strings."),
    replace_existing: bool = Query(default=False, description="Whether to replace existing configuration file if it exists. Default is False."),
    db_session:AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        logger.error(f"Dataset not found for dbname: {dbname}", extra={"event_type": "dataset_not_found", "dbname": dbname})
        raise HTTPException(status_code=404, detail="Dataset not found")

    config_helper = ConfigGenerationHelper(dbname)

    try:
        config_helper.setup_client_config(available_tables=data.table_list, replace_existing=replace_existing)
        return {"message": "Full configuration file set up successfully"}
    except Exception as e:
        logger.error(f"Error setting up full configuration file: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error setting up full configuration file: {repr(e)}")
    


@router.post(
    "/{db_name}/setup-vector-store",
    description="Set up vector store for a given dataset. This will create a collection in the vector database and populate it with relevant data such as unique column values and sample questions.",
    summary="Set up vector store for a dataset",
    response_description="Vector store setup status",
    responses = {
        201: {"description": "Vector store set up successfully"},
        400: {"description": "Invalid input data or database connection"},
        404: {"description": "Dataset not found"}
    },
    status_code=201,
)
async def setup_vector_store(
    dbname: str = Query(..., description="The name of the dataset for which to set up the vector store."),
    timeout: int = Query(1800, description="Timeout for vector store setup in seconds. Default is 1800s (30 minutes)."),
    db_session:AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        logger.error(f"Dataset not found for dbname: {dbname}", extra={"event_type": "dataset_not_found", "dbname": dbname})
        raise HTTPException(status_code=404, detail="Dataset not found")

    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {dbname}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": dbname,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, dbname)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=timeout)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {dbname}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": dbname,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    try:
        table_count = await asyncio.wait_for(vector_store.insert_table_vectors(), timeout=timeout)
        column_count = await asyncio.wait_for(vector_store.insert_column_vectors(), timeout=timeout)
        column_value_count = await asyncio.wait_for(vector_store.insert_column_value_vectors(), timeout=timeout)
        sample_queries_count = await asyncio.wait_for(vector_store.insert_sample_query_vectors(), timeout=timeout)
        
        # table_count, column_count, column_value_count = await asyncio.wait_for(
        #     asyncio.gather(
        #         vector_store.insert_table_vectors(),
        #         vector_store.insert_column_vectors(),
        #         vector_store.insert_column_value_vectors(),
        #     ),
        #     timeout=timeout,
        # )

        result = {
            "success": True,
            "message": "Vector database setup completed successfully",
            "db_name": dbname,
            "statistics": {
                "table_vectors_inserted": table_count,
                "column_vectors_inserted": column_count,
                "column_value_vectors_inserted": column_value_count,
                "sample_query_vectors_inserted": sample_queries_count,
                "total_vectors_inserted": (
                    table_count + column_count + column_value_count + sample_queries_count
                ),
            },
        }

        logger.info(
            f"Vector database setup completed for: {dbname}",
            extra={
                "event_type": "vector_db_setup_success",
                "db_name": dbname,
                "statistics": result["statistics"],
            },
        )

        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Vector database setup timed out after {timeout}s for dataset: {dbname}",
            extra={
                "event_type": "vector_db_setup_timeout",
                "db_name": dbname,
                "timeout": timeout,
            },
        )
        raise HTTPException(
            status_code=408,
            detail=f"Vector database setup timed out after {timeout} seconds. Try again or increase timeout.",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during vector database setup for dataset: {dbname}: {str(e)}",
            extra={
                "event_type": "vector_db_setup_error",
                "db_name": dbname,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail=f"Vector database setup failed: {str(e)}"
        )


# @router.post(
#     "/{db_name}/configure-table-column-metadata",
#     description="Configure table column metadata such as data types, primary key, foreign key, and unique values. This endpoint is used to set up the schema information for a given database connection. The metadata is stored in a CSV file for later use in generating schema strings and providing context to the LLM.",
#     summary="Configure table column metadata for a database connection",
#     response_description="Metadata configuration status",
#     responses = {
#         201: {"description": "Metadata configured successfully"},
#         400: {"description": "Invalid input data or database connection"},
#         404: {"description": "Database connection not found"}
#     },
#     status_code=201,
#     dependencies=[Depends(check_admin)]
# )
# async def configure_tables_columns_metadata(
#     data: ConfigureTableColumnMetadataRequest, 
#     dbname: str = Query(..., description="The name of the dataset for which to configure table column metadata."),
#     replace_existing: bool = Query(default=False, description="Whether to replace existing metadata if it exists. Default is False."),
#     db_session:AsyncSession = Depends(get_db_async)
# ):    

@router.get(
    "/{db_name}/metatadata/tables-metadata",
    description="Get the list of tables for which metadata has been configured for a given dataset.",
    summary="Get list of tables with configured metadata for a dataset",
    response_description="List of tables with configured metadata",
    responses = {
        200: {"description": "List of tables retrieved successfully"},
        404: {"description": "Dataset not found or metadata not configured"}
    },
    status_code=200,
    # dependencies=[Depends(check_admin)],
    response_model=list[MetadataTableResponse]
)
async def get_metadata_tables_list(
    db_name: str = Path(..., description="The name of the dataset for which to retrieve the list of tables with configured metadata."),
):
    tables_metatdata_path = pathlib.Path(f"business_data") / db_name / "tables" / "tables.json"

    if not tables_metatdata_path.exists():
        logger.error(f"Metadata tables list not found for dataset: {db_name}", extra={"event_type": "metadata_tables_list_not_found", "db_name": db_name})
        raise HTTPException(status_code=404, detail="Metadata tables list not found for the specified dataset")

    with open(tables_metatdata_path, "r") as f:
        tables_metadata = json.load(f)

    return tables_metadata


@router.post(
    "/{db_name}/metatadata/tables-metadata",
    description="Update the list of tables for which metadata has been configured for a given dataset.",
    summary="Update list of tables with configured metadata for a dataset",
    response_description="List of tables with configured metadata",
    responses = {
        201: {"description": "List of tables retrieved successfully"},
        404: {"description": "Dataset not found or metadata not configured"}
    },
    status_code=201,
    # dependencies=[Depends(check_admin)],
)
async def create_metadata_tables_list(
    payload: list[MetadataTableResponse],
    db_name: str = Path(..., description="The name of the dataset for which to retrieve the list of tables with configured metadata."),
):
    tables_metatdata_path = pathlib.Path(f"business_data") / db_name / "tables" / "tables.json"

    if not tables_metatdata_path.exists():
        logger.error(f"Metadata tables list not found for dataset: {db_name}", extra={"event_type": "metadata_tables_list_not_found", "db_name": db_name})
        raise HTTPException(status_code=404, detail="Metadata tables list not found for the specified dataset")

    with open(tables_metatdata_path, "w") as f:
        json.dump([i.model_dump() for i in payload], f)

    # recreating table vectors in vector db as tables with metadata have been updated.
    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {db_name}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": db_name,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=300)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    # first deleteing the existing table vectors for the dataset and then inserting new ones.    
    try:
        await vector_store.delete_table_vectors()
        inserted_count = await vector_store.insert_table_vectors()
    except Exception as e:
        logger.error(
            f"Error updating table vectors in vector database for dataset: {db_name}",
            extra={
                "event_type": "vector_db_table_vector_update_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update table vectors in vector database",
        )
    
    # updating schema string if it exists
    schema_str_path = pathlib.Path("app") / "core" / "schema_strings" / f"{db_name}.yaml"
    if schema_str_path.exists():
        schema_helper = SchemaGenerationHelper(db_name)
        try:
            schema_helper.setup_schema_string(replace_existing=True)
        except Exception as e:
            logger.error(f"Error updating schema string after metadata tables list update for dataset: {db_name}: {repr(e)}")

    return {"message": "Metadata tables list updated successfully", "inserted_count": inserted_count}


@router.get(
    "/{db_name}/metatadata/{table_name}",
    description="Get the metadata details for a specific table in a given dataset.",
    summary="Get metadata details for a specific table in a dataset",
    response_description="Metadata details for the specified table",
    responses = {
        200: {"description": "Metadata details retrieved successfully"},
        404: {"description": "Dataset or table not found or metadata not configured"}
    },
    status_code=200,
    # dependencies=[Depends(check_admin)], 
    response_model=list[MetadatataTableUpdateRequest]
)
async def get_metadata_table_details(
    db_name: str = Path(..., description="The name of the dataset for which to retrieve the list of tables with configured metadata."),
    table_name: str = Path(..., description="The name of the table for which to retrieve metadata details."),
):
    columns_metatdata_path = pathlib.Path(f"business_data") / db_name / "columns" / f"{table_name}.json"

    if not columns_metatdata_path.exists():
        logger.error(f"Metadata columns list not found for dataset: {db_name}, table: {table_name}", extra={"event_type": "metadata_columns_list_not_found", "db_name": db_name, "table_name": table_name})
        raise HTTPException(status_code=404, detail="Metadata columns list not found for the specified dataset and table")

    with open(columns_metatdata_path, "r") as f:
        columns_metadata = json.load(f)

    return columns_metadata


@router.post(
    "/{db_name}/metatadata/{table_name}",
    description="Create or update the metadata details for a specific table in a given dataset.",
    summary="Create or update metadata details for a specific table in a dataset",
    response_description="Metadata details for the specified table",
    responses = {
        201: {"description": "Metadata details created successfully"},
        404: {"description": "Dataset or table not found or metadata not configured"}
    },
    status_code=201,
    # dependencies=[Depends(check_admin)]
)
async def update_metadata_table_details(
    payload: list[MetadatataTableUpdateRequest],
    db_name: str = Path(..., description="The name of the dataset for which to retrieve the list of tables with configured metadata."),
    table_name: str = Path(..., description="The name of the table for which to retrieve metadata details."),
):
    columns_metatdata_path = pathlib.Path(f"business_data") / db_name / "columns" / f"{table_name}.json"

    if not columns_metatdata_path.exists():
        logger.error(f"Metadata columns list not found for dataset: {db_name}, table: {table_name}", extra={"event_type": "metadata_columns_list_not_found", "db_name": db_name, "table_name": table_name})
        raise HTTPException(status_code=404, detail="Metadata columns list not found for the specified dataset and table")

    with open(columns_metatdata_path, "w") as f:
        json.dump([i.model_dump() for i in payload], f)

    # recreating column vectors in vector db as tables with metadata have been updated.
    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {db_name}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": db_name,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=300)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    try:
        await vector_store.delete_column_vectors(table_name)
        inserted_count = await vector_store.insert_column_vectors_for_tables(tables_list=[table_name])
    except Exception as e:
        logger.error(
            f"Error updating table vectors in vector database for dataset: {db_name}",
            extra={
                "event_type": "vector_db_table_vector_update_error",
                "db_name": db_name,
                "error": str(e),
                "tables_list": [table_name],
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update table vectors in vector database",
        )
    
    # updating schema string if it exists
    schema_str_path = pathlib.Path("app") / "core" / "schema_strings" / f"{db_name}.yaml"
    if schema_str_path.exists():
        schema_helper = SchemaGenerationHelper(db_name)
        try:
            schema_helper.setup_schema_string(replace_existing=True)
        except Exception as e:
            logger.error(f"Error updating schema string after metadata tables list update for dataset: {db_name}: {repr(e)}")

    return {"message": f"Columns Metadata  updated successfully - {table_name}", "inserted_count": inserted_count}
