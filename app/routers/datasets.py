from pydantic import Field
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.logger import get_logger
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.dependencies import get_db_async, get_pool, client_pool_manager
from app.routers.auth import get_current_user, check_admin
from app.models import DatasetCreate, TablesToUse
from datetime import datetime, timezone
from app.databases.client_sql.operations import get_table_from_sql_parallel, get_table_from_sql


logger = get_logger()


router = APIRouter(prefix="/iod/datasets", tags=["Datasets"])


@router.post("/create-dataset", status_code=201, dependencies=[Depends(check_admin)], tags=["Self Serve"])
async def store_user_database_details(
    payload: DatasetCreate, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    connection_details = await i_data.get_db_connection(payload.connection_id)
    if not connection_details:
        raise HTTPException(status_code=404, detail="Invalid Connection Details")
    
    if not payload.db_schema:
        if connection_details.dialect == "mssql":
            setattr(payload, "db_schema", "dbo")
        if connection_details.dialect == "pgsql":
            setattr(payload, "db_schema", "public")

    try:
        dataset_details = await i_data.create_dataset_self_serve(details=payload.model_dump())
        return dataset_details
    except Exception as e:
        logger.error(f"Dataset not created properly - {repr(e)}")
        raise HTTPException(status_code=400, detail="Dataset not created properly")
    

@router.get("/{db_name}", status_code=201)
async def get_dataset_details(
    db_name: str,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    try:
        dataset_details = await i_data.get_dataset_details_from_dbname(db_name)
        if not dataset_details:
            raise HTTPException(status_code=404, detail="Invalid Dataset Id")
        return dataset_details
    except Exception as e:
        logger.error(f"Dataset not retreived properly for Conection id - {db_name} - {repr(e)}")
        raise HTTPException(status_code=404, detail="Dataset not found")
    

@router.get("", status_code=201)
async def get_available_datasets(
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    try:
        dataset_details = await i_data.get_dataset_details_all()
        return_datasets = [
            {
                "id": d.id,
                "db_name": d.db_name,
            }
            for d in dataset_details
        ]
        return return_datasets
    except Exception as e:
        logger.error(f"Dataset Details not found - {repr(e)}")
        raise HTTPException(status_code=404, detail="Dataset not found")
    


@router.post("/{db_name}", status_code=201)
async def update_dataset(
    payload: DatasetCreate,
    db_name: str,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    dataset_details = await i_data.get_db_details_from_dbname(db_name)
    if not dataset_details:
        raise HTTPException(status_code=404, detail="Dataset does not exists")
    
    update_status = await i_data.update_dataset_details(db_name, payload.model_dump())
    if not update_status:
        raise HTTPException(status_code=400, detail="Dataset not updated successfully")

    updated_dataset_details = await i_data.get_dataset_details_from_dbname(db_name)
    return updated_dataset_details



@router.get("/{db_name}/all-available-tables", status_code=200, tags=["Self Serve"])
async def get_all_available_tables_analysis(
    db_name: str,
    session = Depends(get_db_async)
):  
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    dataset_details, connection_details = fectched_details

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
    
    tables_to_use = pool.get_available_tables(schema=dataset_details.db_schema)
    pool.dispose_sync()
    return {"tables_to_use": tables_to_use}


@router.put("/{db_name}/tables-to-use", status_code=200, tags=["Self Serve"])
async def configure_tables_to_use_for_analysis(
    payload: TablesToUse,
    db_name: str,
    session = Depends(get_db_async)
):  
    i_data = InternalSQLHelper(session)

    dataset_details = await i_data.get_dataset_details_from_dbname(db_name)
    if not dataset_details:
        raise HTTPException(status_code=404, detail="Dataset not found") 
    
    update_status = await i_data.update_dataset_details(db_name, payload.model_dump())
    if not update_status:
        raise HTTPException(status_code=400, detail="Dataset not updated successfully")

    updated_dataset_details = await i_data.get_dataset_details_from_dbname(db_name)
    return updated_dataset_details


@router.get("/{db_name}/tables-to-use/columns-for-filters", status_code=200, tags=["Self Serve"])
async def get_all_columns_from_tables_to_use(
    db_name: str,
    session = Depends(get_db_async)
):  
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    dataset_details, connection_details = fectched_details

    if not dataset_details.tables_to_use:
        raise HTTPException(status_code=404, detail="Configure the tables for Dataset first")
    
    pool = await get_pool(dataset_details, connection_details)

    sql_queries = []
    for tbl in dataset_details.tables_to_use:
        sql_queries.append(f"SELECT TOP 1 * FROM {tbl};")

    query_results = await get_table_from_sql_parallel(
        pool=pool, 
        db_name=db_name, 
        sql_queries=sql_queries
    )

    output = []
    for tbl, qr in zip(dataset_details.tables_to_use, query_results):
        if qr.status!="success":
            logger.warning(f"Query not exectued successfully for {tbl} - status {qr.status} - {qr.error}")
        else:
            output.append({"table": tbl, "columns": qr.columns})

    return output
    