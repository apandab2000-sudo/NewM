from .application_sql.connections import ApplicationPoolManager
from .application_nosql.connections import ApplicationNoSQLPoolManager
from .caching.connections import CachingPoolManager
from .vector.connections import VectorPoolManager
from .client_sql.connections import BaseConnectionPool, MultiDatabasePoolManager
from app.logger import get_logger

logger = get_logger(__name__)

# SQL Database Pool Manager
application_pool_manager = ApplicationPoolManager()


async def get_db_async():
    """Dependency to get a database session for application SQL database"""
    application_sql_db = await application_pool_manager.get_pool()
    
    if not application_sql_db.engine:
        application_sql_db.init_engine()

    if not application_sql_db.session_maker:
        raise RuntimeError("Engine not initialized")
    
    async with application_sql_db.session_maker() as session:
        try:
            logger.debug("Yielding SQL session", extra={"event_type": "session_start"})
            yield session
        finally:
            logger.debug("Closing SQL session", extra={"event_type": "session_end"})
            await session.close()


# NoSQL Database Pool Manager
application_nonsql_pool_manager = ApplicationNoSQLPoolManager()


async def get_nosql_client():
    """Dependency to get MongoDB client"""
    return await application_nonsql_pool_manager.get_pool()


# Caching (Redis) Pool Manager
caching_pool_manager = CachingPoolManager(idle_ttl=1800)


async def get_caching_client():
    """Dependency to get Redis caching client"""
    pool = await caching_pool_manager.get_pool()
    return pool.get()


# Vector Database Pool Manager
vector_pool_manager = VectorPoolManager(idle_ttl=3600)

async def get_vector_client():
    """Dependency to get Qdrant vector database client"""
    pool = await vector_pool_manager.get_pool()
    return pool.get()


# Client Pool Manager for external SQL databases
client_pool_manager = MultiDatabasePoolManager(idle_ttl=1800) 


async def get_pool(db_details, connection_details):
    db_config = {
        "username": connection_details.username,
        "password": connection_details.password,
        "host": connection_details.host,
        "port": connection_details.port,
        "database": connection_details.db
    }

    pool = await client_pool_manager.get_pool(
        db_connection_id=db_details.connection_id, 
        dialect=connection_details.dialect, 
        **db_config
    )
    return pool