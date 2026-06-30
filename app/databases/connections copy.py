# from urllib.parse import quote
# from app.appConfig import settings
# from sqlalchemy import create_engine, inspect
# from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
# from sqlalchemy.ext.asyncio import async_sessionmaker
# from motor.motor_asyncio import AsyncIOMotorClient
# from beanie import init_beanie
# from .nosql_schema import Transaction
# import redis.asyncio as aioredis
# from qdrant_client import AsyncQdrantClient
# from app.logger import get_logger
# from functools import cached_property

# logger = get_logger()


from .application_sql.connections import AppplicationPoolManager
from .application_nosql.connections import ApplicationNoSQLDatabase
from .caching.connections import CachingDatabase
from .vector.connections import VectorClient 
from .client_sql.connections import MultiDatabasePoolManager
from app.appConfig import settings

# Initialing SQL Connections
application_pool_manager = AppplicationPoolManager()

async def get_db_async():
    application_sql_db = await application_pool_manager.get_pool()
    if not application_sql_db.session_maker:
        raise RuntimeError("Engine not initialized")
    
    async with application_sql_db.session_maker() as session:
        try:
            print("$$$$$$$$$$ Getting Session $$$$$$$$$$")
            yield session
        finally:
            print("$$$$$$$$$$ Closing Session $$$$$$$$$$")
            await session.close()

# Initialing No-SQL Connections
nosql_client = ApplicationNoSQLDatabase()

# Initialing Vector Connections
vector_client = VectorClient()

# Initialing Caching Connections
caching_client = CachingDatabase()

# Client pool Manager
client_pool_manager = MultiDatabasePoolManager(max_pools=settings.max_pools, idle_ttl=settings.max_pool_idle_time)

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
    await pool.init_engine()
    return pool

# def get_internal_sql_connection_async():
#     host = settings.sql_host
#     port = settings.sql_port
#     username = settings.sql_username
#     password = quote(settings.sql_password)
#     db = settings.sql_database

#     engine = create_async_engine(
#         f"mssql+aioodbc://{username}:{password}@{host}:{port}/{db}?driver=ODBC Driver 17 for SQL Server",
#         echo=False,
#         pool_size=10,
#         max_overflow=5,
#         pool_timeout=30,
#         pool_recycle=1800,
#         pool_pre_ping=True,
#     )
#     return engine


# def initailize_internal_sql_database():
#     global internal_async_engine
#     internal_async_engine = get_internal_sql_connection_async()
#     return internal_async_engine


# async def close_internal_sql_database():
#     global internal_async_engine
#     if internal_async_engine:
#         await internal_async_engine.dispose()


# async_session_maker: async_sessionmaker | None = None


# def initialize_async_session_maker():
#     global async_session_maker
#     async_session_maker = async_sessionmaker(
#         bind=internal_async_engine, expire_on_commit=False
#     )


# def get_async_session_maker():
#     if async_session_maker is None:
#         raise RuntimeError("SQL Database connection not initialized properly")
#     return async_session_maker


# async def get_db_async():
#     async_session_maker = get_async_session_maker()
#     async with async_session_maker() as session:
#         yield session


# ################################# INTERNAL NOSQL CONNECTION ############################################

# nosql_client: AsyncIOMotorClient | None = None


# async def initialize_mongodb():
#     host = settings.nosql_host
#     port = settings.nosql_port
#     username = settings.nosql_username
#     password = settings.nosql_password
#     db = settings.nosql_database

#     global nosql_client
#     nosql_client = AsyncIOMotorClient(
#         f"mongodb://{username}:{password}@{host}:{port}/{db}?authSource=admin"
#     )
#     await init_beanie(database=nosql_client[db], document_models=[Transaction])  # type: ignore


# def get_nosql_client() -> AsyncIOMotorClient:
#     if nosql_client is None:
#         raise RuntimeError("MongoDB client not initialized")
#     return nosql_client


# def close_mongodb():
#     global nosql_client
#     if nosql_client:
#         nosql_client.close()


# ############################# CAHCING - REDIS ############################################

# redis_client: aioredis.Redis | None = None


# def initialize_redis():
#     global redis_client
#     redis_client = aioredis.Redis(
#         host=settings.caching_host,
#         port=settings.caching_port,
#         db=settings.caching_database,
#         decode_responses=False,
#     )
#     return redis_client


# def get_redis_client():
#     if redis_client is None:
#         raise RuntimeError("Redis client not initialized")
#     return redis_client


# async def close_redis():
#     global redis_client
#     if redis_client:
#         await redis_client.close()


# ######################################### VECTOR DATABASE #####################################
# vector_db: AsyncQdrantClient | None = None


# def initialize_vectordb():
#     global vector_db
#     vector_db = AsyncQdrantClient(host=settings.vector_host, port=settings.vector_port)
#     return vector_db


# async def close_vectordb():
#     global vector_db
#     if vector_db:
#         await vector_db.close()


# def get_vector_db():
#     if vector_db is None:
#         raise RuntimeError("Vector Db not initialized properly")
#     return vector_db


######################################### CLIENT SQL DATABASE #####################################


# class AioODBCPool:
#     """Async connection pool wrapper for aioodbc with health checks and monitoring"""

#     def __init__(
#         self, db_name: str = "abc", size: int = 20, connection_timeout: int = 30
#     ):
#         host = settings.client_sql_host
#         port = settings.client_sql_port
#         username = settings.client_sql_username
#         password = settings.client_sql_password
#         db = settings.client_sql_database

#         self._conn_str = (
#             f"DRIVER={{ODBC Driver 17 for SQL Server}};"
#             f"SERVER={host};DATABASE={db};PORT={port};UID={username};PWD={password};"
#             f"MARS_Connection=yes"
#         )

#         self._minsize = 1  # max(1, size // 4)
#         self._maxsize = settings.client_connection_pool_per_worker
#         self._connection_timeout = connection_timeout
#         self._pool: Optional[aioodbc.Pool] = None
#         self._initialized = False
#         self._closed = False
#         self._total_acquires = 0
#         self._total_releases = 0
#         self._failed_acquires = 0

#     async def init(self):
#         """Initialize connection pool"""
#         if self._initialized:
#             return

#         logger.info(
#             f"Initializing aioodbc connection pool with minsize={self._minsize}, maxsize={self._maxsize}"
#         )

#         try:
#             self._pool = await aioodbc.create_pool(
#                 dsn=self._conn_str,
#                 minsize=self._minsize,
#                 maxsize=self._maxsize,
#                 timeout=self._connection_timeout,
#                 autocommit=True,
#                 echo=False,
#                 pool_recycle=1800,
#             )
#             self._initialized = True
#             logger.info(
#                 f"Connection pool initialized successfully (min={self._minsize}, max={self._maxsize})"
#             )
#         except Exception as e:
#             logger.error(f"Failed to initialize connection pool: {e}")
#             raise

#     async def acquire(self, timeout: Optional[float] = None) -> aioodbc.Connection:
#         """Acquire a connection from pool with health check"""
#         if self._closed:
#             raise RuntimeError("Pool is closed")

#         if not self._initialized:
#             raise RuntimeError("Pool not initialized. Call init() first.")

#         timeout = timeout or self._connection_timeout

#         try:
#             # aioodbc.Pool.acquire() returns a context manager-like connection
#             conn = await asyncio.wait_for(
#                 self._pool.acquire(),  # type: ignore
#                 timeout=timeout,
#             )
#             self._total_acquires += 1

#             # Optional: Health check
#             try:
#                 await self._ping_connection(conn)
#             except Exception as e:
#                 logger.warning(f"Connection health check failed: {e}")
#                 # Release the bad connection and let pool handle it
#                 await self._pool.release(conn)  # type: ignore
#                 self._failed_acquires += 1
#                 raise

#             return conn

#         except asyncio.TimeoutError:
#             self._failed_acquires += 1
#             raise TimeoutError(
#                 f"Failed to acquire connection within {timeout}s. "
#                 f"Pool size: {self._pool.size}, Free: {self._pool.freesize}"  # type: ignore
#             )
#         except Exception as e:
#             self._failed_acquires += 1
#             logger.error(f"Failed to acquire connection: {e}")
#             raise

#     async def _ping_connection(self, conn: aioodbc.Connection):
#         """Ping connection to check if alive"""
#         async with conn.cursor() as cursor:
#             await cursor.execute("SELECT 1")
#             await cursor.fetchone()

#     async def release(self, conn: aioodbc.Connection):
#         """Return connection to pool"""
#         if not self._closed and self._pool:
#             try:
#                 await self._pool.release(conn)
#                 self._total_releases += 1
#             except Exception as e:
#                 logger.warning(f"Error releasing connection: {e}")

#     async def close(self):
#         """Close all connections in pool"""
#         if self._closed:
#             return

#         self._closed = True

#         if self._pool:
#             logger.info("Closing connection pool...")
#             try:
#                 self._pool.close()
#                 await self._pool.wait_closed()
#                 logger.info(
#                     f"Pool closed. Stats: {self._total_acquires} acquires, "
#                     f"{self._total_releases} releases, {self._failed_acquires} failed"
#                 )
#             except Exception as e:
#                 logger.error(f"Error closing pool: {e}")

#     async def __aenter__(self):
#         """Async context manager entry"""
#         await self.init()
#         return self

#     async def __aexit__(self, exc_type, exc_val, exc_tb):
#         """Async context manager exit"""
#         await self.close()

#     def get_stats(self) -> Dict[str, int]:
#         """Get pool statistics"""
#         if self._pool:
#             return {
#                 "minsize": self._minsize,
#                 "maxsize": self._maxsize,
#                 "size": self._pool.size,
#                 "freesize": self._pool.freesize,
#                 "total_acquires": self._total_acquires,
#                 "total_releases": self._total_releases,
#                 "failed_acquires": self._failed_acquires,
#                 "is_closed": self._closed,
#             }
#         return {
#             "minsize": self._minsize,
#             "maxsize": self._maxsize,
#             "is_closed": self._closed,
#             "total_acquires": self._total_acquires,
#             "total_releases": self._total_releases,
#             "failed_acquires": self._failed_acquires,
#         }
    

# class AioODBCPool:
#     def __init__(self):
#         host = settings.client_sql_host
#         port = settings.client_sql_port
#         username = settings.client_sql_username
#         password = quote(settings.client_sql_password)
#         db = settings.client_sql_database

#         self.connection_string = (
#             f"mssql+aioodbc://{username}:{password}"
#             f"@{host}:{port}"
#             f"/{db}"
#             f"?driver=ODBC+Driver+17+for+SQL+Server"
#         )

#     def init(self):
#         self.engine: AsyncEngine = create_async_engine(
#             self.connection_string,
#             pool_size=settings.client_connection_pool_per_worker,                    
#             max_overflow=2,                 
#             pool_timeout=30,                 
#             pool_recycle=1800,                
#             pool_pre_ping=True,              
#             echo=False,                      
#             connect_args={
#                 "timeout": 15,
#             }
#         )
    
#     async def close(self):
#         """Dispose of the engine and all connections"""
#         await self.engine.dispose()


# client_connection_pool = AioODBCPool()




# class ClientConnection:
#     def __init__(self, USERNAME: str, PASSWORD: str, HOST: str, PORT: str, DATABASE: str, DIALECT: str = "mssql", DRIVER = None):
#         self.UID = USERNAME
#         self.PWD = PASSWORD
#         self.SERVER = HOST
#         self.PORT = PORT
#         self.DATABASE = DATABASE
#         self.DIALECT = DIALECT.lower()
#         self.engine = self._create_engine()

#     def _default_driver(self):
#         return {
#             "mssql": "ODBC+Driver+17+for+SQL+Server",  # for pyodbc
#             "mysql": "pymysql",
#             "pgsql": "psycopg2",
#             "clickhouse": None  # if using sqlalchemy-clickhouse
#         }.get(self.DIALECT)

#     def _create_engine(self):
#         driver = self._default_driver()
#         if self.DIALECT == "mssql":
#             driver_str = f"driver={driver}"
#             url =  f'mssql+pyodbc://{self.UID}:{quote(self.PWD)}@{self.SERVER}:{self.PORT}/{self.DATABASE}?'+f'{driver_str}'
#         else:
#             driver_part = f"+{driver}" if driver else ""
#             url = (
#                 f"{self.DIALECT}{driver_part}://{self.UID}:{quote(self.PWD)}@"
#                 f"{self.SERVER}:{self.PORT}/{self.DATABASE}"
#             )
#         return create_engine(url, future=True)

#     def check_connectivity(self) -> bool:
#         try:
#             with self.engine.connect() as conn:
#                 return True
#         except Exception as e:
#             print(f"[Connection Error] {e!r}")
#             return False

#     @cached_property
#     def inspector(self):
#         return inspect(self.engine)

#     def get_available_tables(self) -> list:
#         return self.inspector.get_table_names()

#     def get_table_info(self, table: str) -> list:
#         return [
#             {"col_name": col["name"], "data_type": str(col["type"])}
#             for col in self.inspector.get_columns(table)
#         ]

#     def get_primary_key_constraints(self, table: str) -> list:
#         return self.inspector.get_pk_constraint(table).get("constrained_columns", [])

#     def get_foreign_key_constraints(self, table: str) -> list:
#         fks = self.inspector.get_foreign_keys(table)
#         return [col for fk in fks for col in fk.get("constrained_columns", [])]

#     def get_relationships(self, table: str) -> list:
#         relationships = []
#         for fk in self.inspector.get_foreign_keys(table):
#             print("##################### FK ############################")
#             print(fk)
#             print("##################### FK END ############################")
#             for local_col, remote_col in zip(
#                 fk.get("constrained_columns", []),
#                 fk.get("referred_columns", [])
#             ):
#                 relationships.append({
#                     "from_table": table,
#                     "to_table": fk.get("referred_table"),
#                     "from_table_column": local_col,
#                     "to_table_column": remote_col,
#                 })
#         return relationships