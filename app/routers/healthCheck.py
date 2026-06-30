# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select
# from app.databases.connections import (
#     nosql_client,
#     caching_client,
#     vector_client,
#     client_pool_manager,
#     get_db_async,
# )
# from app.logger import get_logger

# logger = get_logger()




# @router.get("/internal/sql")
# async def internal_sql_database_healthcheck(
#     session: AsyncSession = Depends(get_db_async),
# ):
#     try:
#         await session.execute(select(1))
#         return {"status": "SQL Healthcheck successful!"}
#     except Exception as e:
#         logger.error("Internal SQL Connection failed")
#         raise HTTPException(status_code=400, detail=f"SQL Connection Failed - {repr(e)}")


# @router.get("/internal/nosql")
# async def internal_nosql_database_healthcheck():
#     try:
#         await nosql_client.server_info()  # type: ignore
#         return {"status": "NoSQL Healthcheck successful!"}
#     except Exception as e:
#         print(repr(e))
#         logger.error(f"Internal NoSQL Connection failed - {repr(e)}")
#         raise HTTPException(status_code=400, detail="NoSQL Connection Failed")


# @router.get("/internal/caching")
# async def internal_caching_database_healthcheck():
#     try:
#         caching_client.ping()
#         return {"status": "Caching Healthcheck successful!"}
#     except Exception as e:
#         logger.error(f"Internal NoSQL Connection failed - {repr(e)}")
#         raise HTTPException(status_code=400, detail="Caching Connection Failed")


# @router.get("/internal/vector")
# async def internal_vector_database_healthcheck():
#     try:
#         await vector_client.get_collections()
#         return {"status": "Vector Database Healthcheck successful!"}
#     except Exception as e:
#         logger.error(f"Internal Vector Connection failed - {repr(e)}")
#         raise HTTPException(status_code=400, detail="Vector Database Connection Failed")


# @router.get("/client/sql/poolstats")
# async def client_sql_database_stats():
#     client_pool_manager
#     try:
#         health_stats = client_pool_manager.get_pool_stats()
#         return {"stats": health_stats}
#     except Exception as e:
#         logger.error(f"Client SQl Database Connection failed - {repr(e)}")
#         raise HTTPException(status_code=400, detail="Client SQl Database Connection Failed")


from fastapi import APIRouter, Response, HTTPException, Depends
from sqlalchemy import text
from app.databases.dependencies import (
    get_db_async, 
    application_pool_manager,
    get_caching_client,
    caching_pool_manager,
    get_vector_client,
    application_nonsql_pool_manager,
    get_nosql_client,
    client_pool_manager
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.logger import get_logger


router = APIRouter(prefix="/egai/healthcheck", tags=["HealthCheck"])


logger = get_logger(__name__)


@router.get(
    "", 
    summary="Health Check Endpoint", 
    description="Simple endpoint to check if the application is running. Returns 200 OK if healthy.",
    response_description="Health status",
    responses={200: {"description": "Application is healthy"}}
)
def health_check():
    return Response(content="OK", media_type="text/plain")


@router.get(
    "/application/sql", 
    summary="Application SQL Database health check",
    description="Checks connectivity to the application SQL database. Returns 200 OK if the database connection is healthy.",
    response_description="Database connection status",
    responses={
        200: {"description": "Database connection is healthy"},
        400: {"description": "Database connection failed"},
    }
)
async def application_sql_db_health_check(session: AsyncSession = Depends(get_db_async)):
    try:
        await session.execute(text("SELECT 1"))
        return Response(content="OK", media_type="text/plain")
    except Exception as e:
        logger.error(
            "Application SQL database health check failed",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Database connection failed")


@router.get(
    "/application/sql/pool-stats",
    summary="Application SQL Database Pool Stats",
    description="Returns statistics about the application SQL database connection pool.",
    response_description="Database connection pool statistics",
    responses={
        200: {"description": "Database connection pool statistics retrieved successfully"},
        400: {"description": "Failed to retrieve database connection pool statistics"},
    },
    status_code=200
)
async def application_sql_db_pool_stats():
    try:
        application_pool = await application_pool_manager.get_pool()
        if not application_pool:
            raise HTTPException(status_code=400, detail="No active database connection pool")
        pool_stats = application_pool.get_stats()
        return pool_stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve application SQL database pool statistics",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Failed to retrieve database connection pool's statistics")


@router.get(
    "/application/cache",
    summary="Application Cache health check",
    description="Checks connectivity to the application cache. Returns 200 OK if the cache connection is healthy.",
    response_description="Cache connection status",
    responses={
        200: {"description": "Cache connection is healthy"},
        400: {"description": "Cache connection failed"},
    }
)
async def application_cache_health_check():
    try:
        caching_client = await get_caching_client()
        await caching_client.ping()
        return Response(content="OK", media_type="text/plain")
    except Exception as e:
        logger.error(
            "Application cache health check failed",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Cache connection failed")


@router.get(
    "/application/cache/stats",
    summary="Application Cache Stats",
    description="Returns statistics about the application cache.",
    response_description="Application cache statistics",
    responses={
        200: {"description": "Application cache statistics retrieved successfully"},
        400: {"description": "Failed to retrieve application cache statistics"},
    },
    status_code=200,
)
async def application_cache_stats():
    try:
        pool = await caching_pool_manager.get_pool()
        stats = await pool.get_stats()
        return stats
    except Exception as e:
        logger.error(
            "Failed to retrieve application cache statistics",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Failed to retrieve application cache statistics")


@router.get(
    "/application/vector-db",
    summary="Application Vector Database health check",
    description="Checks connectivity to the application vector database. Returns 200 OK if the vector database connection is healthy.",
    response_description="Vector database connection status",
    responses={
        200: {"description": "Vector database connection is healthy"},
        400: {"description": "Vector database connection failed"},
    },
    status_code=200
)
async def application_vector_db_health_check():
    try:
        vector_client = await get_vector_client()
        await vector_client.get_collections()
        return Response(content="OK", media_type="text/plain")
    except Exception as e:
        logger.error(
            "Application vector database health check failed",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Vector database connection failed")
    

@router.get(
    "/application/nonsql-db",
    summary="Application Non-SQL Database health check",
    description="Checks connectivity to the application non-SQL database. Returns 200 OK if the non-SQL database connection is healthy.",
    response_description="Non-SQL database connection status",
    responses={
        200: {"description": "Non-SQL database connection is healthy"},
        400: {"description": "Non-SQL database connection failed"},
    },
    status_code=200
)
async def application_nonsql_db_health_check():
    try:
        nosql_client = await get_nosql_client()
        nosql_client.test_connection()
        return Response(content="OK", media_type="text/plain")
    except Exception as e:
        logger.error(
            "Application non-SQL database health check failed",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Non-SQL database connection failed")
    

@router.get(
    "/application/nonsql-db/stats",
    summary="Application Non-SQL Database Stats",
    description="Returns statistics about the application non-SQL database connection pool.",
    response_description="Non-SQL database connection pool statistics",
    responses={
        200: {"description": "Non-SQL database connection pool statistics retrieved successfully"},
        400: {"description": "Failed to retrieve non-SQL database connection pool statistics"},
    },
    status_code=200,
)
async def application_nonsql_db_stats():
    try:
        stats = application_nonsql_pool_manager.get_stats()
        return stats
    except Exception as e:
        logger.error(
            "Failed to retrieve application non-SQL database pool statistics",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Failed to retrieve non-SQL database connection pool's statistics")


@router.get(
    "/client/sql",
    summary="Client SQL Database health check",
    description="Checks connectivity to the client SQL database. Returns 200 OK if the database connection is healthy.",
    response_description="Client database connection status",
    responses={
        200: {"description": "Client database connection is healthy"},
        400: {"description": "Client database connection failed"},
    },
    status_code=200
)
def client_sql_db_health_check():
    try:
        health_stats = client_pool_manager.get_pool_health()
        return health_stats
    except Exception as e:
        logger.error(
            "Client SQL database health check failed",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Client SQL database connection failed")


@router.get(
    "/client/sql/pool-stats",
    summary="Client SQL Database Pool Stats",
    description="Returns statistics about the client SQL database connection pool.",
    response_description="Client database connection pool statistics",
    responses={
        200: {"description": "Client database connection pool statistics retrieved successfully"},
        400: {"description": "Failed to retrieve client database connection pool statistics"},
    },
    status_code=200
)
def client_sql_db_pool_stats():
    try:
        pool_stats = client_pool_manager.get_all_pools_stats()
        if not pool_stats:
            raise HTTPException(status_code=400, detail="No active client database connection pool")
        return pool_stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve client SQL database pool statistics",
            extra={
                "event_type": "health_check_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Failed to retrieve client database connection pool's statistics")