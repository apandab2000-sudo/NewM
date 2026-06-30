
from app.core.setups.config_setup import ConfigGenerationHelper
# from app.core.setups.config_setup import ConfigGenerationHelper
from app.core.setups.introductions import IntroductionHelper
from app.core.setups.metadata_setup import MetaDataSetup
from app.core.setups.schemas import SchemaGenerationHelper
from app.models import TableFetchRequest, CorrectionRequest, ConfigureFilters
# from app.databases.connections import ClientConnection
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
from app.databases.dependencies import get_db_async, get_pool, client_pool_manager, vector_pool_manager
from app.logger import get_logger
import asyncio
from app.core.setups.vectors.vectors import VectorStoreSetupClient


from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
import pathlib
from app.logger import get_logger
from typing import Optional, List, Literal
from app.databases.application_sql.services.db_connections import DataBaseConnectionHelper
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.application_sql.services.users import UsersHelper
from app.api_models.self_serve import (
    AiModelMappings, 
    FlatFileDatabaseSetupRequest, 
    SqlDatabaseSetupRequest,
    TablesToUseUpdate
)
import aiofiles
from datetime import datetime, timezone
from app.core.setups.flat_file_processor.processor import process_uploaded_file
from app.api_models.users import UserName


logger = get_logger(__name__)


router = APIRouter(prefix="/iod/setup", tags=["Setups"])


FILES_UNDER_PROCESSING = {}


@router.post(
    '/sql/create_database', 
    summary="Create a new database in the application SQL server. It uses client existing Connection",
    description="This endpoint creates a new database in the application SQL server using an existing client connection. The request should include the name of the new database to be created. The endpoint checks if the database already exists and returns an appropriate response.",
    response_description="A message indicating whether the database was created successfully or if it already exists.",
    status_code=201
)
async def create_database_sql(
    payload: SqlDatabaseSetupRequest,
    session: AsyncSession = Depends(get_db_async)
):
    user_helper = UsersHelper(session)
    dataset_helper = DatasetHelper(session)
    db_connection_helper = DataBaseConnectionHelper(session)

    # Check if user exists
    user = await user_helper.get_user_details_from_email(payload.email_id)
    if not user:
        logger.warning(f"User with email {payload.email_id} not found", extra={"email": payload.email_id})
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if dataset with the same name already exists for the user
    existing_dataset = await dataset_helper.get_dataset_by_name(payload.db_name)
    if existing_dataset:
        logger.warning(f"Dataset with name {payload.db_name} already exists for user {payload.email_id}", extra={"email": payload.email_id, "db_name": payload.db_name})
        raise HTTPException(status_code=400, detail="Dataset with the same name already exists")
    
    # check if database connection exists
    db_connection = await db_connection_helper.get_db_connection_by_uid_host_port(
        username=payload.database_details.username,
        host=payload.database_details.host,
        port=payload.database_details.port
    )

    if not db_connection:
        logger.info(f"No existing database connection found for user {payload.email_id} with host {payload.database_details.host} and port {payload.database_details.port}. Creating new connection.", extra={"email": payload.email_id, "host": payload.database_details.host, "port": payload.database_details.port})
        # creating new database connection
        conn_details = {
            "name": payload.database_details.name,
            "description": payload.database_details.description,
            "dialect": payload.database_details.dialect,
            "username": payload.database_details.username,
            "password": payload.database_details.password,
            "host": payload.database_details.host,
            "port": payload.database_details.port,
            "db": payload.database_details.db
        }

        # check if credentials provided are valid by trying to fetch tables from the database
        connection_kwargs = {
            "username": payload.database_details.username,
            "password": payload.database_details.password,
            "host": payload.database_details.host,
            "port": payload.database_details.port,
            "database": payload.database_details.db,
        }
        
        pool = client_pool_manager.get_pool_sync(
            db_connection_id=0, 
            dialect=payload.database_details.dialect, 
            **connection_kwargs
        )

        if not pool:
            logger.error(f"Failed to create database connection for user {payload.email_id}", extra={"email": payload.email_id})
            raise HTTPException(status_code=400, detail="Failed to create database connection")

        db_connection = await db_connection_helper.create_db_connection(conn_details=conn_details, user_id=user.id)
        tables_to_use = pool.get_available_tables(schema=payload.db_schema)
        await client_pool_manager.close_sync_pool(0)

    else:
        logger.info(f"Existing database connection found for user {payload.email_id} with host {payload.database_details.host} and port {payload.database_details.port}. Using existing connection.", extra={"email": payload.email_id, "host": payload.database_details.host, "port": payload.database_details.port})
        connection_kwargs = {
            "username": db_connection.username,
            "password": db_connection.password,
            "host": db_connection.host,
            "port": db_connection.port,
            "database": db_connection.db,
        }
        
        pool = client_pool_manager.get_pool_sync(
            db_connection_id=db_connection.id, 
            dialect=db_connection.dialect, 
            **connection_kwargs
        )

        if not pool:
            logger.error(f"Failed to connect using existing database connection for user {payload.email_id}", extra={"email": payload.email_id})
            raise HTTPException(status_code=400, detail="Failed to connect using existing database connection")

        tables_to_use = pool.get_available_tables(schema=payload.db_schema)
        await client_pool_manager.close_sync_pool(db_connection.id)
    

    # create new dataset
    dataset_details = {
        "db_name": payload.db_name,
        "db_schema": payload.db_schema,
        "ai_provider": payload.ai_provider,
        "ai_model_mappings": payload.ai_model_mappings.model_dump() if payload.ai_model_mappings else None,
        "graph_type": payload.graph_type,
        "connection_id": db_connection.id,
        "is_self_serve": True,
        "created_by": user.id
    }
    
    try:
        new_dataset = await dataset_helper.create_dataset(dataset_details)
        if not new_dataset:
            raise HTTPException(status_code=400, detail="Failed to create dataset")
    except Exception as e:
        logger.error(f"Error creating database connection or dataset for user {payload.email_id} - {repr(e)}", extra={"email": payload.email_id})
        raise HTTPException(status_code=400, detail="Failed to create database connection or dataset")   
    
    return {
        "message": "Database and dataset created successfully", 
        "client_connection_id": db_connection.id,
        "db_id": new_dataset.id,
        "table_list": tables_to_use
    }



@router.post(
    "/flat_file/create_database",
    summary="Create a new dataset in the application using a flat file upload",
    description="This endpoint creates a new dataset in the application by uploading a flat file (CSV or Excel). The request should include the file, the name of the dataset, and optional AI model mappings and graph type. The endpoint processes the file, creates a new dataset, and returns a message indicating success along with the dataset ID.",
    status_code=201,
    response_description="A message indicating that the dataset was created successfully along with the dataset ID."
)
async def create_database_flat_file(
    background_tasks: BackgroundTasks,
    user_name: str = Form(..., description="Username of the person doing the setup"),
    db_name: str = Form(..., description="Name ofgiven to the dataset in the application"),
    ai_provider: Optional[Literal["azure", "openai", "anthropic"]] = Form("openai", description="AI provider to use for this dataset"),
    ai_model_mappings: Optional[str] = Form(None, description="Optional JSON string mapping of AI tasks to specific models for this dataset"),
    graph_type: Optional[Literal["plotlycharts", "echarts"]] = Form("plotlycharts", description="Graph type to use for this dataset"),
    mode: Literal["new", "append", "replace"] = Form("new", description="Mode of dataset creation. 'new' will create a new dataset, while 'append' will add to an existing dataset with the same name, and 'replace' will replace the existing dataset with the new one."),
    is_continued: Optional[bool] = Form(False, description="Flag to indicate if this is a continued upload for an existing dataset. If true, the endpoint will check if the dataset exists and append or replace data based on the mode. If false, it will create a new dataset and return an error if a dataset with the same name already exists."),
    zip_files: UploadFile = File(..., description="The flat file to be uploaded (CSV or Excel)"),
    session: AsyncSession = Depends(get_db_async)
):
    
    payload = FlatFileDatabaseSetupRequest(
        user_name=user_name,
        db_name=db_name,
        ai_provider=ai_provider,
        ai_model_mappings=AiModelMappings.model_validate_json(ai_model_mappings) if ai_model_mappings else None,
        graph_type=graph_type,
        mode=mode,
        is_continued=is_continued
    )

    if not zip_files.filename.lower().endswith(('.zip', '.7zip', '.archive')):
        logger.warning(f"Unsupported file type uploaded by user {payload.email_id}: {zip_files.filename}", extra={"email": payload.email_id, "filename": zip_files.filename})
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a CSV, Excel, or ZIP file.")
    
    user_helper = UsersHelper(session)
    dataset_helper = DatasetHelper(session)

    # Check if user exists
    user = await user_helper.get_user_details_from_email(payload.email_id)
    if not user:
        logger.warning(f"User with email {payload.email_id} not found", extra={"email": payload.email_id})
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if dataset with the same name already exists for the user
    existing_dataset = await dataset_helper.get_dataset_by_name(payload.db_name)
    if existing_dataset:
        logger.warning(f"Dataset with name {payload.db_name} already exists for user {payload.email_id}", extra={"email": payload.email_id, "db_name": payload.db_name})

    if existing_dataset and not payload.mode in ["append", "replace"]:
        raise HTTPException(status_code=400, detail="Dataset with the same name already exists. Use 'append' or 'replace' mode to modify the existing dataset.")

    BASE_PATH = pathlib.Path(settings.file_upload_path) / payload.db_name / datetime.now(tz=timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    file_location = BASE_PATH / zip_files.filename

    async with aiofiles.open(file_location, "wb") as out_file:
        while chunk := await zip_files.read(1024 * 1024):
            await out_file.write(chunk)

    try:
        unsupported_files = process_uploaded_file(file_location, payload.db_name, payload.mode)
    except Exception as e:
        logger.error(f"Error processing uploaded file for dataset {payload.db_name} - {repr(e)}", extra={"db_name": payload.db_name})
        raise HTTPException(status_code=500, detail="Error processing uploaded file")
    
    if not existing_dataset: 
        logger.info(f"Creating new dataset for user {payload.email_id} with name {payload.db_name}", extra={"email": payload.email_id, "db_name": payload.db_name})
        dataset_details = {
            "db_name": payload.db_name,
            "db_schema": None,  # Schema is not applicable for flat file datasets
            "ai_provider": payload.ai_provider,
            "ai_model_mappings": payload.ai_model_mappings.model_dump() if payload.ai_model_mappings else None,
            "graph_type": payload.graph_type,
            "is_self_serve": True,
            "connection_id": 11, # hardcoded
            "created_by": user.id
        }
        
        try:
            new_dataset = await dataset_helper.create_dataset(dataset_details)
            if not new_dataset:
                raise HTTPException(status_code=400, detail="Failed to create dataset")
        except Exception as e:
            logger.error(f"Error creating database connection or dataset for user {payload.email_id} - {repr(e)}", extra={"email": payload.email_id})
            raise HTTPException(status_code=400, detail="Failed to create database connection or dataset")   
    else:
        logger.info(f"Using existing dataset for user {payload.email_id} with name {payload.db_name} and applying mode {payload.mode}", extra={"email": payload.email_id, "db_name": payload.db_name, "mode": payload.mode})
        new_dataset = existing_dataset
    
    return {
        "message": "File uploaded and dataset created successfully. Data processing is underway and will be completed shortly.",
        "db_name": payload.db_name,
        "client_connection_id": 11,
        "db_id": new_dataset.id,
        "unsupported_files": unsupported_files
    }


@router.get(
    "/tables-to-use",
    summary="Get list of tables to use for a dataset based on the provided database name",
    description="This endpoint retrieves a list of tables that can be used for a dataset based on the provided database name. It checks if a dataset with the given name exists and returns the list of tables associated with that dataset.",
    status_code=200,
    response_description="A list of tables that can be used for the dataset."
)
async def get_tables_to_use(
    user_name: str = Query(..., description="Username of the person requesting the tables"),
    db_name: str = Query(..., description="Name of the dataset to retrieve tables for"),
    session: AsyncSession = Depends(get_db_async),
):
    user_model = UserName(user_name=user_name)
    
    dataset_helper = DatasetHelper(session)

    # Check if dataset exists
    dataset, connection_details = await dataset_helper.get_dataset_and_connection_details(db_name)
    if not dataset:
        logger.warning(f"Dataset with name {db_name} not found", extra={"db_name": db_name})
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    if not connection_details:
        logger.warning(f"No connection details found for dataset {db_name}", extra={"db_name": db_name})
        raise HTTPException(status_code=404, detail="Connection details not found for the dataset")
    
    db_config = {
        "username": connection_details.username,
        "password": connection_details.password,
        "host": connection_details.host,
        "port": connection_details.port,
        "database": connection_details.db
    }

    pool = client_pool_manager.get_pool_sync(
        db_connection_id=0, 
        dialect=connection_details.dialect, 
        **db_config
    )

    if not pool:
        logger.error(f"Failed to connect to database for dataset {db_name}", extra={"db_name": db_name})
        raise HTTPException(status_code=400, detail="Failed to connect to database")
    
    tables_to_use = pool.get_available_tables(schema=dataset.db_schema, db_name=dataset.db_name)
    await client_pool_manager.close_sync_pool(0)

    with open("app/clientConfig.yaml", "r") as f:
        client_config = yaml.safe_load(f)

    tables_in_use = client_config.get(db_name, {}).get("DATABASE", {}).get("available_tables", [])

    return {
        "message": "Tables retrieved successfully",
        "available_tables": tables_to_use,
        "tables_in_use": tables_in_use
    }


@router.post(
    "/tables-to-use",
    summary="Create or Update list of tables to use for an existing dataset based on the provided database name",
    description="This endpoint creates or updates the list of tables that can be used for an existing dataset based on the provided database name. It checks if a dataset with the given name exists and updates the list of tables associated with that dataset.",
    status_code=200,
    response_description="A message indicating that the list of tables to use has been updated successfully."
)
async def create_or_update_tables_to_use(
    payload: TablesToUseUpdate,
    session: AsyncSession = Depends(get_db_async),
):
    users_helper = UsersHelper(session)
    dataset_helper = DatasetHelper(session)

    # Check if user exists
    user = await users_helper.get_user_details_from_email(payload.email_id)
    if not user:
        logger.warning(f"User with email {payload.email_id} not found", extra={"email": payload.email_id})
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if dataset exists
    dataset = await dataset_helper.get_dataset_by_name(payload.db_name)
    if not dataset:
        logger.warning(f"Dataset with name {payload.db_name} not found", extra={"db_name": payload.db_name})
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    config_helper = ConfigGenerationHelper(payload.db_name)
    
    try:
        config_helper.setup_client_config(available_tables=payload.tables_in_use, replace_existing=payload.replace_existing)
        
        update_status = await dataset_helper.update_dataset(payload.db_name, {"tables_to_use": payload.tables_in_use})
        if not update_status:
            raise HTTPException(status_code=400, detail="Dataset not updated successfully")

        return {
            "message": "Full configuration file set up successfully and tables to use recorded",
            "db_name": payload.db_name,
            "tables_in_use": payload.tables_in_use
        }
    except Exception as e:
        logger.error(f"Error setting up full configuration file: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error setting up full configuration file: {repr(e)}")
    
