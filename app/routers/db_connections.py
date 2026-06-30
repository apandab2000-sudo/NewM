from pydantic import Field
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.logger import get_logger
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.dependencies import get_db_async
from app.routers.auth import check_admin
from app.models import DbConnectionCreate
# from app.databases.client_sql.connections import pool_manager

logger = get_logger()

router = APIRouter(prefix="/iod/db-connections", tags=["Database Connections"])


@router.get("", status_code=201)
async def get_available_database_connections(
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    try:
        db_conn_details = await i_data.get_db_connections_all()
        return_db_conns = [
            {
                "id": d.id,
                "name": d.name
            }
            for d in db_conn_details
        ]
        return return_db_conns
    except Exception as e:
        logger.error(f"Dataabse Connection Details not found - {repr(e)}")
        raise HTTPException(status_code=404, detail="Dataabse Connections not found")


@router.post("", status_code=201, tags=["Self Serve"])
async def create_database_connection(
    payload: DbConnectionCreate,
    session: AsyncSession = Depends(get_db_async),
    creator = Depends(check_admin)
):
    i_data = InternalSQLHelper(session)
    try:
        db_conn_details = await i_data.create_db_connection(conn_details=payload.model_dump(), user_id=creator.id)
        return db_conn_details
    except Exception as e:
        logger.error(f"Db Connection not created properly - {repr(e)}")
        raise HTTPException(status_code=400, detail="Db Connection not created properly")
    

@router.get("/{db_conn_id}", status_code=201, dependencies=[Depends(check_admin)])
async def get_database_connection_details(
    db_conn_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    try:
        db_conn_details = await i_data.get_db_connection(db_conn_id)
        if not db_conn_details:
            raise HTTPException(status_code=404, detail="Invalid Connection Id")
        setattr(db_conn_details, "password", "*****")
        return db_conn_details
    except Exception as e:
        logger.error(f"Dataabse Connection Details not retreived properly for Conection id - {db_conn_id} - {repr(e)}")
        raise HTTPException(status_code=404, detail="Dataabse Connection not found")
    


@router.put("/{db_conn_id}", status_code=201, dependencies=[Depends(check_admin)])
async def update_database_connection(
    payload: DbConnectionCreate,
    db_conn_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    db_conn_details = await i_data.get_db_connection(db_conn_id)
    if not db_conn_details:
        raise HTTPException(status_code=404, detail="Dataabse Connection does not exists")
    
    update_status = await i_data.update_db_connection(db_conn_id, payload.model_dump())
    if not update_status:
        raise HTTPException(status_code=400, detail="Dataabse Connection not updated successfully")

    updated_db_conn_details = await i_data.get_db_connection(db_conn_id)
    setattr(updated_db_conn_details, "password", "*****")
    return updated_db_conn_details


# @router.get("/pool-factory/stats", status_code=200, dependencies=[Depends(check_admin)])
# async def get_pool_factory_stats():
#     return pool_manager._last_used




