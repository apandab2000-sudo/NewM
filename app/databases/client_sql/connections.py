from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
import duckdb
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
)
from sqlalchemy import create_engine, Engine, text, inspect
from sqlalchemy.engine import URL
import asyncio
from typing import Dict, Any, List
import time
from enum import Enum
from app.logger import get_logger
from app.appConfig import settings
from app.core.prometheus_metrics import (
    POOL_SIZE,
    POOL_OVERFLOW,
    POOL_CHECKED_IN,
    POOL_CHECKED_OUT,
)
from sqlalchemy.sql.sqltypes import (
    Integer,
    BigInteger,
    SmallInteger,
    Float,
    Numeric,
    DECIMAL,
    String,
    Text,
    Date,
    DateTime,
    Boolean,
)
from functools import cached_property


logger = get_logger(__name__)


class ConnectionHealth(Enum):
    """Enum for connection pool health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


def get_type(col_type):
    """Map SQLAlchemy column types to string representations"""
    if isinstance(col_type, (Date, DateTime)):
        return "date"
    elif isinstance(col_type, Boolean):
        return "boolean"
    elif isinstance(col_type, (String, Text)):
        return "nvarchar"
    elif isinstance(col_type, (Integer, BigInteger, SmallInteger)):
        return "integer"
    elif isinstance(col_type, (Float, Numeric, DECIMAL)):
        return "float"
    else:
        return None


class BaseConnectionPool(ABC):
    """Abstract base class for database connection pools with lifecycle management"""

    def __init__(
        self,
        db_connection_id: int,
        username: str | None,
        password: str | None,
        host: str | None,
        port: int | None,
        database: str | None,
    ):
        """
        Initialize connection pool.

        Args:
            db_connection_id: Unique tenant database identifier
            username: Database username
            password: Database password
            host: Database host
            port: Database port
            database: Database name
            async_required: Whether async engine is required

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(db_connection_id, int) or db_connection_id < 0:
            raise ValueError("db_connection_id must be non-negative integer")
        # if not host or not username or not database:
        #     raise ValueError("host, username, and database are required")

        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self.db_connection_id = db_connection_id

        self.engine: AsyncEngine | Engine | None = None
        self.session_maker: async_sessionmaker | None = None
        self._lock = asyncio.Lock()
        self._health = ConnectionHealth.HEALTHY
        self._failed_connection_attempts = 0
        self._max_failed_attempts = 3

    @abstractmethod
    def get_async_url(self) -> URL:
        """Get async connection URL for dialect"""
        ...

    @abstractmethod
    def get_sync_url(self) -> URL:
        """Get sync connection URL for dialect"""
        ...

    @abstractmethod
    def _build_connect_args(self, query_connection_timeout: int) -> dict:
        """Build dialect-specific connection arguments"""
        ...

    async def init_engine(
        self,
        pool_size: int = 5,
        max_overflow: int = 2,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ) -> None:
        """
        Initialize async database engine with connection pool.

        Args:
            pool_size: Minimum connections to maintain (default: 5)
            max_overflow: Additional connections above pool_size (default: 2)
            pool_timeout: Connection acquisition timeout in seconds (default: 30)
            pool_recycle: Recycle connections after N seconds (default: 1800)

        Raises:
            RuntimeError: If connection initialization fails
        """
        if self.engine:
            return

        async with self._lock:
            if self.engine:
                return

            try:
                self.engine = create_async_engine(
                    self.get_async_url(),
                    echo=False,
                    pool_size=pool_size,
                    max_overflow=max_overflow,
                    pool_timeout=pool_timeout,
                    pool_recycle=pool_recycle,
                    pool_pre_ping=True,
                    connect_args=self._build_connect_args(settings.pool_cleanup_cycle_time),
                )

                # Test connection
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

                self.session_maker = async_sessionmaker(
                    bind=self.engine,
                    expire_on_commit=False,
                    autoflush=False,
                    autocommit=False,
                    class_=AsyncSession,
                )

                self._health = ConnectionHealth.HEALTHY
                self._failed_connection_attempts = 0

                logger.info(
                    "Engine initialized for database",
                    extra={
                        "event_type": "engine_init_success",
                        "db_connection_id": self.db_connection_id,
                        "database": self.database,
                        "pool_size": pool_size,
                    },
                )

            except Exception as e:
                self._health = ConnectionHealth.UNHEALTHY
                self._failed_connection_attempts += 1

                logger.error(
                    "Failed to initialize engine",
                    extra={
                        "event_type": "engine_init_error",
                        "db_connection_id": self.db_connection_id,
                        "database": self.database,
                        "error": str(e),
                        "attempt": self._failed_connection_attempts,
                    },
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to initialize engine for {self.database}: {str(e)}")
            
    def init_sync_engine(
        self,
        pool_size: int = 1,
        max_overflow: int = 1,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ) -> None:
        """
        Initialize sync database engine.
        """
        if self.engine:
            return

        try:
            sync_url = self.get_sync_url()

            print("==============================================")
            print("DB CONNECTION ID:", self.db_connection_id)
            print("HOST:", self.host)
            print("PORT:", self.port)
            print("DATABASE:", self.database)
            print("USERNAME:", self.username)
            print(
                "CONNECTION STRING:",
                sync_url.render_as_string(hide_password=True),
            )
            print("==============================================")

            self.engine = create_engine(
                sync_url,
                echo=False,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=True,
            )

            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self._health = ConnectionHealth.HEALTHY

            logger.info(
                "Sync engine initialized",
                extra={
                    "event_type": "sync_engine_init_success",
                    "db_connection_id": self.db_connection_id,
                    "database": self.database,
                },
            )

        except Exception as e:
            self._health = ConnectionHealth.UNHEALTHY

            logger.error(
                "Failed to initialize sync engine",
                extra={
                    "event_type": "sync_engine_init_error",
                    "db_connection_id": self.db_connection_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise RuntimeError(
                f"Failed to initialize sync engine: {str(e)}"
            )

    # def init_sync_engine(
    #     self,
    #     pool_size: int = 1,
    #     max_overflow: int = 1,
    #     pool_timeout: int = 30,
    #     pool_recycle: int = 1800,
    # ) -> None:
    #     """
    #     Initialize sync database engine (for non-async operations).

    #     Args:
    #         pool_size: Minimum connections (default: 1)
    #         max_overflow: Additional connections (default: 1)
    #         pool_timeout: Connection timeout (default: 30)
    #         pool_recycle: Recycle after N seconds (default: 1800)

    #     Raises:
    #         RuntimeError: If connection fails
    #     """
    #     if self.engine:
    #         return

    #     try:
    #         self.engine = create_engine(
    #             self.get_sync_url(),
    #             echo=False,
    #             pool_size=pool_size,
    #             max_overflow=max_overflow,
    #             pool_timeout=pool_timeout,
    #             pool_recycle=pool_recycle,
    #             pool_pre_ping=True,
    #         )

    #         # Test connection
    #         with self.engine.connect() as conn:
    #             conn.execute(text("SELECT 1"))

    #         self._health = ConnectionHealth.HEALTHY

    #         logger.info(
    #             "Sync engine initialized",
    #             extra={
    #                 "event_type": "sync_engine_init_success",
    #                 "db_connection_id": self.db_connection_id,
    #                 "database": self.database,
    #             },
    #         )

    #     except Exception as e:
    #         self._health = ConnectionHealth.UNHEALTHY

    #         logger.error(
    #             "Failed to initialize sync engine",
    #             extra={
    #                 "event_type": "sync_engine_init_error",
    #                 "db_connection_id": self.db_connection_id,
    #                 "error": str(e),
    #             },
    #             exc_info=True,
    #         )
    #         raise RuntimeError(f"Failed to initialize sync engine: {str(e)}")

    async def dispose(self) -> None:
        """Dispose async engine and cleanup resources"""
        async with self._lock:
            try:
                if self.engine:
                    await self.engine.dispose()
                    self.engine = None
                    self.session_maker = None

                    logger.info(
                        "Async engine disposed",
                        extra={
                            "event_type": "engine_disposed",
                            "db_connection_id": self.db_connection_id,
                            "database": self.database,
                        },
                    )
            except Exception as e:
                logger.error(
                    "Error disposing engine",
                    extra={
                        "event_type": "engine_dispose_error",
                        "db_connection_id": self.db_connection_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

    async def dispose_sync(self) -> None:
        """Dispose sync engine and cleanup resources"""
        async with self._lock:
            try:
                if self.engine:
                    self.engine.dispose()
                    self.engine = None

                    logger.info(
                        "Sync engine disposed",
                        extra={
                            "event_type": "sync_engine_disposed",
                            "db_connection_id": self.db_connection_id,
                        },
                    )
            except Exception as e:
                logger.error(
                    "Error disposing sync engine",
                    extra={
                        "event_type": "sync_engine_dispose_error",
                        "error": str(e),
                    },
                    exc_info=True,
                )
                
    @asynccontextmanager
    async def get_session(self):
        session = self.session_maker()

        try:
            yield session

        except Exception as exc:
            logger.error(
                "Error during session usage",
                extra={
                    "event_type": "session_error",
                    "db_connection_id": self.db_connection_id,
                    "exception_type": type(exc).__name__,
                    "error": str(exc),
                },
                exc_info=True,
            )

            try:
                await session.rollback()
            except Exception:
                logger.warning(
                    "Session rollback failed",
                    exc_info=True,
                )

            raise

        finally:
            await session.close()


    def get_health(self) -> ConnectionHealth:
        """Get current connection pool health status"""
        return self._health

    def collect_metrics(self) -> None:
        """Collect and record pool metrics"""
        if not self.engine:
            return

        try:
            pool = self.engine.pool

            POOL_SIZE.labels(self.db_connection_id).set(pool.size())
            POOL_CHECKED_OUT.labels(self.db_connection_id).set(pool.checkedout())
            POOL_CHECKED_IN.labels(self.db_connection_id).set(pool.checkedin())
            POOL_OVERFLOW.labels(self.db_connection_id).set(pool.overflow())

            logger.debug(
                "Pool metrics collected",
                extra={
                    "event_type": "metrics_collected",
                    "db_connection_id": self.db_connection_id,
                    "pool_size": pool.size(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to collect pool metrics",
                extra={
                    "event_type": "metrics_collection_error",
                    "db_connection_id": self.db_connection_id,
                    "error": str(e),
                },
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get detailed pool statistics.

        Returns:
            Dictionary with pool stats or empty dict if no engine
        """
        if not self.engine:
            return {}

        try:
            pool = self.engine.pool
            return {
                "db_connection_id": self.db_connection_id,
                "database": self.database,
                "health": self._health.value,
                "pool_size": pool.size() if hasattr(pool, "size") else 0,
                "checked_out": pool.checkedout() if hasattr(pool, "checkedout") else 0,
                "checked_in": pool.checkedin() if hasattr(pool, "checkedin") else 0,
                "overflow": pool.overflow() if hasattr(pool, "overflow") else 0,
            }
        except Exception as e:
            logger.warning(
                "Failed to get pool stats",
                extra={
                    "event_type": "stats_error",
                    "db_connection_id": self.db_connection_id,
                    "error": str(e),
                },
            )
            return {}
        
    @cached_property
    def inspector(self):
        return inspect(self.engine)
    
    def get_available_tables(self, schema: str | None = None, db_name: str | None = None) -> list:
        """
        Fetch available tables and views from the database.
        
        Args:
            schema: Optional schema name. If not provided, uses the default schema

        Returns:
            List of available tables and views. Returns empty list on error.
        """
        if not self.inspector:
            raise RuntimeError("Inspector not initialized")
        
        try:
            available_tables = []
            available_tables.extend(self.inspector.get_table_names(schema=schema))
            available_tables.extend(self.inspector.get_view_names(schema=schema))     
            if schema:
                available_tables = [f"{schema}.{table}" for table in available_tables if not table.startswith(f"{schema}.")]
            return available_tables
       
        except Exception as e:
            logger.warning(
                "Failed to get available tables",
                extra={
                    "event_type": "available_tables_error",
                    "db_connection_id": self.db_connection_id,
                    "error": str(e),
                },
            )
            return []

    def get_available_columns(self, tables: List[str], schema: str | None = None) -> Dict[str, list]:
        """
        Fetch all columns for the specified tables.

        Args:
            tables: List of table names to fetch columns from
            schema: Optional schema name. If not provided, uses the default schema

        Returns:
            Dictionary mapping table names to their columns. Each column is a dictionary
            containing column metadata (name, type, nullable, etc.). Returns empty dict on error.
        """
        if not tables:
            logger.warning(
                "get_available_columns called with empty tables list",
                extra={
                    "event_type": "empty_tables_list",
                    "db_connection_id": self.db_connection_id,
                },
            )
            return {}

        try:
            if not self.inspector:
                raise RuntimeError("Inspector not initialized")

            available_columns = {}

            for table_name in tables:
                try:
                    columns = self.inspector.get_columns(table_name, schema=schema)
                    available_columns[table_name] = columns

                    logger.debug(
                        "Fetched columns for table",
                        extra={
                            "event_type": "columns_fetched",
                            "db_connection_id": self.db_connection_id,
                            "table_name": table_name,
                            "column_count": len(columns),
                        },
                    )
                except Exception as table_error:
                    logger.warning(
                        "Failed to get columns for table",
                        extra={
                            "event_type": "table_columns_error",
                            "db_connection_id": self.db_connection_id,
                            "table_name": table_name,
                            "error": str(table_error),
                        },
                    )
                    # Add empty list for this table instead of skipping
                    available_columns[table_name] = []

            return available_columns

        except Exception as e:
            logger.warning(
                "Failed to get available columns",
                extra={
                    "event_type": "available_columns_error",
                    "db_connection_id": self.db_connection_id,
                    "table_count": len(tables),
                    "error": str(e),
                },
            )
            return {}

    def get_primary_key_constraints(self, table: str) -> list:
        if not self.inspector:
            raise RuntimeError("Inspector not initialized")
        try:
            return self.inspector.get_pk_constraint(table).get("constrained_columns", [])
        except Exception as e:
            logger.warning(
                "Failed to get primary key constraints",
                extra={
                    "event_type": "primary_key_constraints_error",
                    "db_connection_id": self.db_connection_id,
                    "table_name": table,
                    "error": str(e),
                },
            )
            return []

    def get_foreign_key_constraints(self, table: str) -> list:
        if not self.inspector:
            raise RuntimeError("Inspector not initialized")
        try:
            fks = self.inspector.get_foreign_keys(table)
            return [col for fk in fks for col in fk.get("constrained_columns", [])]
        except Exception as e:
            logger.warning(
                "Failed to get foreign key constraints",
                extra={
                    "event_type": "foreign_key_constraints_error",
                    "db_connection_id": self.db_connection_id,
                    "table_name": table,
                    "error": str(e),
                },
            )
            return []

    def get_relationships(self, table: str) -> dict:
        if not self.inspector:
            raise RuntimeError("Inspector not initialized")
        try:
            relationships = []
            for fk in self.inspector.get_foreign_keys(table):
                print("##################### FK ############################")
                print(fk)
                print("##################### FK END ############################")
                for local_col, remote_col in zip(
                    fk.get("constrained_columns", []),
                    fk.get("referred_columns", [])
                ):
                    relationships.append({
                        "from_table": table,
                        "to_table": fk.get("referred_table"),
                        "from_table_column": local_col,
                        "to_table_column": remote_col,
                    })
            return relationships
        except Exception as e:
            logger.warning(
                "Failed to get relationships",
                extra={
                    "event_type": "relationships_error",
                    "db_connection_id": self.db_connection_id,
                    "table_name": table,
                    "error": str(e),
                },
            )
            return []


class MssqlConnectionPool(BaseConnectionPool):
    """Microsoft SQL Server connection pool implementation"""

    def get_async_url(self) -> URL:
        """Get async connection URL for MSSQL"""
        return URL.create(
            drivername="mssql+aioodbc",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"driver": "ODBC Driver 17 for SQL Server"},
        )

    def get_sync_url(self) -> URL:
        """Get sync connection URL for MSSQL"""
        return URL.create(
            drivername="mssql+pyodbc",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"driver": "ODBC Driver 17 for SQL Server"},
        )

    def _build_connect_args(self, query_connection_timeout: int = 10) -> dict:
        """Build MSSQL-specific connection arguments"""
        return {"timeout": query_connection_timeout}


class PostgresConnectionPool(BaseConnectionPool):
    """PostgreSQL connection pool implementation"""

    def get_async_url(self) -> URL:
        """Get async connection URL for PostgreSQL"""
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def get_sync_url(self) -> URL:
        """Get sync connection URL for PostgreSQL"""
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def _build_connect_args(self, query_connection_timeout: int = 10) -> dict:
        """Build PostgreSQL-specific connection arguments"""
        return {
            "server_settings": {
                "application_name": "text2sql_app",
                "statement_timeout": f"{query_connection_timeout * 1000}ms",
            }
        }


class MySQLConnectionPool(BaseConnectionPool):
    """MySQL connection pool implementation"""

    def get_async_url(self) -> URL:
        """Get async connection URL for MySQL"""
        return URL.create(
            drivername="mysql+aiomysql",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def get_sync_url(self) -> URL:
        """Get sync connection URL for MySQL"""
        return URL.create(
            drivername="mysql+pymysql",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def _build_connect_args(self, query_connection_timeout: int = 10) -> dict:
        """Build MySQL-specific connection arguments"""
        return {
            "timeout": query_connection_timeout,
            "autocommit": True,
        }


class DuckDBConnectionPool(BaseConnectionPool):
    """DuckDB connection pool implementation (placeholder)"""

    def get_async_url(self) -> URL:
        """DuckDB does not support async connections, so this is a placeholder"""
        raise NotImplementedError("DuckDB does not support async connections")

    def get_sync_url(self) -> URL | None:
        """Get sync connection URL for DuckDB"""
        return None  # DuckDB uses file-based connections, so URL is not needed

    def _build_connect_args(self, query_connection_timeout: int = 10) -> dict:
        """DuckDB does not have connection arguments, so return empty dict"""
        return {}
    
    def get_available_tables(self, schema = None, db_name: str | None = None):
        BASE_PATH = Path("client_data") / db_name  / "final"
        if not BASE_PATH.exists():
            raise RuntimeError(f"Base path {BASE_PATH} does not exist for DuckDB dataset {db_name}")
        try:
            # con = duckdb.connect(database=str(BASE_PATH / "duckdb.db"), read_only=True)
            # query = "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            # result = con.execute(query).fetchall()
            # tables = [row[0] for row in result]
            # return tables
            tables_list = []
            for parquet_file in BASE_PATH.glob("*.parquet"):
                table_name = parquet_file.stem
                if schema:
                    table_name = f"{db_name}/final/{schema}.{table_name}"
                else:
                    table_name = f"{db_name}/final/{table_name}"
                tables_list.append(table_name)
            return tables_list
        except Exception as e:
            logger.error(
                "Failed to get available tables for DuckDB",
                extra={
                    "event_type": "duckdb_available_tables_error",
                    "db_connection_id": self.db_connection_id,
                    "database": self.database,
                    "error": str(e),
                },
                exc_info=True,
            )
            return []
    
    def init_sync_engine(
        self,
        pool_size: int = 1,
        max_overflow: int = 1,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ) -> None:
        return # DuckDB does not require engine initialization in the traditional sense
    
    async def dispose_sync(self): # DuckDB doesn't have a connection pool to dispose, but we can implement any necessary cleanup here if needed
        if self.engine:
            self.engine = None
            logger.info(
                "DuckDB cleanup completed",
                extra={
                    "event_type": "duckdb_cleanup",
                    "db_connection_id": self.db_connection_id,
                    "database": self.database,
                },
            )
        

class ConnectionPoolFactory:
    """Factory for creating database-specific connection pools"""

    POOL_MAP = {
        "mssql": MssqlConnectionPool,
        "postgresql": PostgresConnectionPool,
        "mysql": MySQLConnectionPool,
        "duckdb": DuckDBConnectionPool,  # Placeholder for future DuckDB implementation
    }

    @classmethod
    def create(cls, dialect: str, db_connection_id: int, **kwargs) -> BaseConnectionPool:
        """
        Create database-specific connection pool.

        Args:
            dialect: Database dialect (mssql, postgres, mysql)
            db_connection_id: Tenant database ID
            **kwargs: Connection parameters (username, password, host, port, database)

        Returns:
            BaseConnectionPool instance

        Raises:
            ValueError: If dialect is unsupported
        """
        if not dialect:
            raise ValueError("dialect cannot be empty")

        pool_cls = cls.POOL_MAP.get(dialect.lower())
        if not pool_cls:
            raise ValueError(f"Unsupported dialect: {dialect}. Supported: {list(cls.POOL_MAP.keys())}")

        return pool_cls(db_connection_id, **kwargs)


class MultiDatabasePoolManager:
    """Manager for multiple tenant database connection pools with LRU eviction"""

    def __init__(self, max_pools: int = 5, idle_ttl: int = 3600):
        """
        Initialize multi-database pool manager.

        Args:
            max_pools: Maximum pools to maintain (default: 5)
            idle_ttl: Idle time-to-live in seconds (default: 1 hour)
        """
        self._pools: Dict[int, BaseConnectionPool] = {}
        self._sync_pools: Dict[int, BaseConnectionPool] = {}
        self._last_used: Dict[int, float] = {}
        self._lock = asyncio.Lock()
        self.max_pools = max_pools
        self.idle_ttl = idle_ttl
        self._cleanup_task = None
        self._metrics_task = None

    def start_cleanup_task(self, interval: int = 3600) -> None:
        """
        Start background cleanup task for idle connections.

        Args:
            interval: Cleanup check interval in seconds (default: 1 hour)
        """
        logger.debug("Starting pool cleanup task")

        if self._cleanup_task and not self._cleanup_task.done():
            logger.warning("Cleanup task already running; skipping.")
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.cleanup_idle_pools()
                except Exception:
                    logger.exception("Error during idle pool cleanup")

        self._cleanup_task = asyncio.create_task(_loop())
        logger.info(
            "Pool cleanup task started",
            extra={
                "event_type": "cleanup_task_started",
                "interval": interval,
                "idle_ttl": self.idle_ttl,
                "max_pools": self.max_pools,
            },
        )

    def start_metrics_task(self, interval: int = 30) -> None:
        """
        Start background metrics collection task.

        Args:
            interval: Metrics collection interval in seconds (default: 30)
        """
        logger.debug("Starting metrics collection task")

        if self._metrics_task and not self._metrics_task.done():
            logger.warning("Metrics task already running; skipping.")
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._collect_all_metrics()
                except Exception:
                    logger.exception("Error collecting pool metrics")

        self._metrics_task = asyncio.create_task(_loop())
        logger.info(
            "Metrics collection task started",
            extra={"event_type": "metrics_task_started", "interval": interval},
        )

    async def _collect_all_metrics(self) -> None:
        """Collect metrics from all active pools"""
        for db_id, pool in list(self._pools.items()):
            try:
                pool.collect_metrics()
            except Exception as e:
                logger.warning(
                    "Failed to collect metrics for pool",
                    extra={
                        "event_type": "metrics_collection_error",
                        "db_connection_id": db_id,
                        "error": str(e),
                    },
                )

    async def get_pool(self, db_connection_id: int, dialect: str, **db_kwargs) -> BaseConnectionPool:
        """
        Get or create database connection pool for tenant.

        Args:
            db_connection_id: Tenant database identifier
            dialect: Database dialect (mssql, postgres, mysql)
            **db_kwargs: Connection parameters (username, password, host, port, database)

        Returns:
            BaseConnectionPool instance

        Raises:
            ValueError: If parameters invalid
            RuntimeError: If pool creation fails
        """
        if not isinstance(db_connection_id, int) or db_connection_id < 0:
            raise ValueError("db_connection_id must be non-negative integer")

        # Check existing pool
        pool = self._pools.get(db_connection_id)
        if pool:
            self._last_used[db_connection_id] = time.time()
            logger.debug(
                "Reusing existing pool",
                extra={
                    "event_type": "pool_reused",
                    "db_connection_id": db_connection_id,
                },
            )
            return pool

        async with self._lock:
            # Double-check after acquiring lock
            pool = self._pools.get(db_connection_id)
            if pool:
                self._last_used[db_connection_id] = time.time()
                return pool

            # Evict LRU pool if at capacity
            if len(self._pools) >= self.max_pools:
                await self._evict_if_needed()

            # Create new pool
            try:
                pool = ConnectionPoolFactory.create(dialect=dialect, db_connection_id=db_connection_id, **db_kwargs)

                await pool.init_engine(
                    pool_size=settings.pool_size,
                    max_overflow=settings.max_overflow,
                    pool_timeout=settings.pool_timeout,
                    pool_recycle=settings.pool_recycle,
                )

                self._pools[db_connection_id] = pool
                self._last_used[db_connection_id] = time.time()

                logger.info(
                    "Created new pool",
                    extra={
                        "event_type": "pool_created",
                        "db_connection_id": db_connection_id,
                        "dialect": dialect,
                        "database": db_kwargs.get("database"),
                        "active_pools": len(self._pools),
                    },
                )
                return pool

            except Exception as e:
                logger.error(
                    "Failed to create pool",
                    extra={
                        "event_type": "pool_creation_error",
                        "db_connection_id": db_connection_id,
                        "dialect": dialect,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to create pool for db_connection_id={db_connection_id}: {str(e)}")
    
    def get_pool_sync(self, db_connection_id: int, dialect: str, **db_kwargs) -> BaseConnectionPool:
        """
        Get or create sync database connection pool.

        Args:
            db_connection_id: Tenant database identifier
            dialect: Database dialect (mssql, postgres, mysql)
            **db_kwargs: Connection parameters

        Returns:
            BaseConnectionPool with sync engine

        Raises:
            ValueError: If parameters invalid
        """
        if not isinstance(db_connection_id, int) or db_connection_id < 0:
            raise ValueError("db_connection_id must be non-negative integer")

        pool = self._sync_pools.get(db_connection_id)
        if pool:
            logger.debug(
                "Reusing existing sync pool",
                extra={"event_type": "sync_pool_reused", "db_connection_id": db_connection_id},
            )
            return pool

        try:
            pool = ConnectionPoolFactory.create(dialect=dialect, db_connection_id=db_connection_id, **db_kwargs)
            pool.init_sync_engine()
            self._sync_pools[db_connection_id] = pool

            logger.info(
                "Created new sync pool",
                extra={
                    "event_type": "sync_pool_created",
                    "db_connection_id": db_connection_id,
                    "dialect": dialect,
                },
            )
            return pool

        except Exception as e:
            logger.error(
                "Failed to create sync pool",
                extra={
                    "event_type": "sync_pool_creation_error",
                    "db_connection_id": db_connection_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to create sync pool: {str(e)}")

    async def _evict_if_needed(self) -> None:
        """Evict least-recently-used pool if at max capacity"""
        if len(self._pools) < self.max_pools:
            return

        if not self._last_used:
            logger.warning(
                "Cannot evict: no pools tracked",
                extra={"event_type": "eviction_failed"},
            )
            return

        # Find least recently used
        oldest_key = min(self._last_used, key=self._last_used.get)
        old_pool = self._pools.pop(oldest_key)
        self._last_used.pop(oldest_key, None)

        try:
            await old_pool.dispose()
            logger.info(
                "Evicted LRU pool",
                extra={
                    "event_type": "pool_evicted",
                    "db_connection_id": oldest_key,
                    "reason": "max_capacity_reached",
                    "active_pools": len(self._pools),
                },
            )
        except Exception as e:
            logger.error(
                "Error disposing evicted pool",
                extra={
                    "event_type": "eviction_error",
                    "db_connection_id": oldest_key,
                    "error": str(e),
                },
                exc_info=True,
            )

    async def cleanup_idle_pools(self) -> None:
        """Close idle connections from both async and sync pools"""
        logger.debug("Checking pools for idle cleanup")

        now = time.time()
        async with self._lock:
            # Find idle async pools
            to_remove = [key for key, ts in self._last_used.items() if now - ts > self.idle_ttl]

            for key in to_remove:
                pool = self._pools.pop(key, None)
                self._last_used.pop(key, None)

                if pool:
                    try:
                        await pool.dispose()
                        logger.info(
                            "Removed idle async pool",
                            extra={
                                "event_type": "idle_pool_removed",
                                "db_connection_id": key,
                                "idle_seconds": int(now - (self._last_used.get(key, now))),
                                "active_pools": len(self._pools),
                            },
                        )
                    except Exception as e:
                        logger.error(
                            "Error disposing idle pool",
                            extra={
                                "event_type": "idle_cleanup_error",
                                "db_connection_id": key,
                                "error": str(e),
                            },
                            exc_info=True,
                        )

            # Cleanup idle sync pools
            sync_to_remove = [key for key in self._sync_pools.keys() if key not in self._pools]

            for key in sync_to_remove:
                sync_pool = self._sync_pools.pop(key, None)
                if sync_pool:
                    try:
                        await sync_pool.dispose_sync()
                        logger.info(
                            "Removed idle sync pool",
                            extra={
                                "event_type": "idle_sync_pool_removed",
                                "db_connection_id": key,
                            },
                        )
                    except Exception as e:
                        logger.error(
                            "Error disposing idle sync pool",
                            extra={
                                "event_type": "idle_sync_cleanup_error",
                                "db_connection_id": key,
                                "error": str(e),
                            },
                            exc_info=True,
                        )

    def get_all_pools_stats(self) -> Dict[int, Dict[str, Any]]:
        """
        Get statistics for all active pools.

        Returns:
            Dictionary mapping db_connection_id to pool stats
        """
        stats = {}
        for db_id, pool in self._pools.items():
            try:
                stats[db_id] = pool.get_stats()
            except Exception as e:
                logger.warning(
                    "Failed to get stats for pool",
                    extra={
                        "event_type": "stats_error",
                        "db_connection_id": db_id,
                        "error": str(e),
                    },
                )
                stats[db_id] = {"error": str(e)}

        return stats

    def get_pool_health(self) -> Dict[str, Any]:
        """
        Get overall pool manager health.

        Returns:
            Dictionary with health information
        """
        healthy_count = sum(1 for p in self._pools.values() if p.get_health() == ConnectionHealth.HEALTHY)
        degraded_count = sum(1 for p in self._pools.values() if p.get_health() == ConnectionHealth.DEGRADED)
        unhealthy_count = sum(
            1 for p in self._pools.values() if p.get_health() == ConnectionHealth.UNHEALTHY
        )

        return {
            "total_pools": len(self._pools),
            "max_pools": self.max_pools,
            "healthy_pools": healthy_count,
            "degraded_pools": degraded_count,
            "unhealthy_pools": unhealthy_count,
            "overall_health": "healthy" if unhealthy_count == 0 else "degraded" if degraded_count > 0 else "unhealthy",
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown all pools and cleanup tasks"""
        logger.info("Starting pool manager shutdown")

        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Cleanup task cancelled")

        # Cancel metrics task
        if self._metrics_task and not self._metrics_task.done():
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass
            logger.info("Metrics task cancelled")

        # Dispose all pools
        async with self._lock:
            for db_id, pool in list(self._pools.items()):
                try:
                    await pool.dispose()
                    logger.debug(
                        "Pool disposed",
                        extra={"event_type": "pool_disposed", "db_connection_id": db_id},
                    )
                except Exception as e:
                    logger.error(
                        "Error disposing pool during shutdown",
                        extra={
                            "event_type": "shutdown_error",
                            "db_connection_id": db_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            # Dispose sync pools
            for db_id, sync_pool in list(self._sync_pools.items()):
                try:
                    await sync_pool.dispose_sync()
                except Exception as e:
                    logger.error(
                        "Error disposing sync pool during shutdown",
                        extra={
                            "event_type": "sync_shutdown_error",
                            "db_connection_id": db_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            self._pools.clear()
            self._sync_pools.clear()
            self._last_used.clear()

        logger.info("Pool manager shutdown complete")

    async def close_sync_pool(self, connection_id: int) -> None:
        """Close a specific sync pool by connection ID"""
        async with self._lock:
            pool = self._sync_pools.pop(connection_id, None)
            if pool:
                try:
                    await pool.dispose_sync()
                    logger.info(
                        "Sync pool closed",
                        extra={
                            "event_type": "sync_pool_closed",
                            "db_connection_id": connection_id,
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Error disposing sync pool",
                        extra={
                            "event_type": "sync_pool_close_error",
                            "db_connection_id": connection_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "Attempted to close non-existent sync pool",
                    extra={
                        "event_type": "sync_pool_not_found",
                        "db_connection_id": connection_id,
                    },
                )

    async def close_async_pool(self, connection_id: int) -> None:
        """Close a specific async pool by connection ID"""
        async with self._lock:
            pool = self._pools.pop(connection_id, None)
            self._last_used.pop(connection_id, None)
            if pool:
                try:
                    await pool.dispose()
                    logger.info(
                        "Async pool closed",
                        extra={
                            "event_type": "async_pool_closed",
                            "db_connection_id": connection_id,
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Error disposing async pool",
                        extra={
                            "event_type": "async_pool_close_error",
                            "db_connection_id": connection_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "Attempted to close non-existent async pool",
                    extra={
                        "event_type": "async_pool_not_found",
                        "db_connection_id": connection_id,
                    },
                )


    # def start_cleanup_task(self, interval: int = 3600) -> None:
    #     logger.debug("Starting pool cleanup task")
    #     if getattr(self, "_cleanup_task", None) and not self._cleanup_task.done():
    #         logger.warning("Cleanup task already running; skipping.")
    #         return

    #     async def _loop() -> None:
    #         while True:
    #             await asyncio.sleep(interval)
    #             try:
    #                 await self.cleanup_idle_pools()
    #             except Exception:
    #                 logger.exception("Error during idle pool cleanup")

    #     self._cleanup_task = asyncio.create_task(_loop())
    #     logger.info(f"Pool cleanup task started (interval={interval}s, idle_ttl={self.idle_ttl}s)")

    # def start_cleanup_task(self, interval: int = 3600) -> None:
    #     """
    #     Start background cleanup task for idle connections.

    #     Args:
    #         interval: Cleanup check interval in seconds (default: 1 hour)
    #     """
    #     logger.debug("Starting pool cleanup task")

    #     if self._cleanup_task and not self._cleanup_task.done():
    #         logger.warning("Cleanup task already running; skipping.")
    #         return

    #     async def _loop() -> None:
    #         while True:
    #             await asyncio.sleep(interval)
    #             try:
    #                 await self.cleanup_idle_pools()
    #             except Exception:
    #                 logger.exception("Error during idle pool cleanup")

    #     self._cleanup_task = asyncio.create_task(_loop())
    #     logger.info(
    #         "Pool cleanup task started",
    #         extra={
    #             "event_type": "cleanup_task_started",
    #             "interval": interval,
    #             "idle_ttl": self.idle_ttl,
    #             "max_pools": self.max_pools,
    #         },
    #     )


    # async def get_pool(self, db_connection_id: int, dialect: str, **db_kwargs,) -> BaseConnectionPool:
    #     pool = self._pools.get(db_connection_id)
    #     if pool:
    #         self._last_used[db_connection_id] = time.time()
    #         return pool

    #     async with self._lock:
    #         pool = self._pools.get(db_connection_id)
    #         if pool:
    #             self._last_used[db_connection_id] = time.time()
    #             return pool

    #         # Removing th oldest pool if new pool is required beyong max pool limit 
    #         await self._evict_if_needed()

    #         # create new pool
    #         pool = ConnectionPoolFactory.create(
    #             dialect=dialect, 
    #             db_connection_id=db_connection_id, 
    #             **db_kwargs
    #         )
    #         await pool.init_engine(
    #             pool_size=settings.pool_size,
    #             max_overflow=settings.max_overflow,
    #             pool_timeout=settings.pool_timeout,
    #             pool_recycle=settings.pool_recycle
    #         )

    #         self._pools[db_connection_id] = pool
    #         self._last_used[db_connection_id] = time.time()
    #         logger.info(f"Created new pool for db_connection_id={db_connection_id} (dialect={dialect})")
    #         return pool
        
    # def get_pool_sync(self, db_connection_id: int, dialect: str, **db_kwargs,) -> BaseConnectionPool:
    #     pool = self._sync_pools.get(db_connection_id)
    #     if pool:
    #         # self._last_used[db_connection_id] = time.time()
    #         return pool
        
    #     pool = ConnectionPoolFactory.create(dialect=dialect, db_connection_id=db_connection_id, **db_kwargs)
    #     pool.init_sync_engine()
    #     self._sync_pools[db_connection_id] = pool

    #     self._sync_pools[db_connection_id] = pool
    #     logger.info(f"Created new sync pool for db_connection_id={db_connection_id} (dialect={dialect})")
    #     return pool
    
    # async def _evict_if_needed(self):
    #     if len(self._pools) < self.max_pools:
    #         return

    #     # find least recently used
    #     oldest_key = min(self._last_used, key=self._last_used.get)

    #     old_pool = self._pools.pop(oldest_key)
    #     self._last_used.pop(oldest_key, None)
    #     await old_pool.dispose()
    #     logger.info(f"Evicted LRU pool for db_connection_id={oldest_key}")

    # async def cleanup_idle_pools(self):
    #     logger.debug(f"Checking for cleanup")
    #     now = time.time()
    #     async with self._lock:
    #         to_remove = [key for key, ts in self._last_used.items() if now - ts > self.idle_ttl]

    #         for key in to_remove:
    #             pool = self._pools.pop(key, None)
    #             self._last_used.pop(key, None)
    #             if pool:
    #                 await pool.dispose()
    #                 logger.info(f"Removed idle pool for db_connection_id={key} (idle > {self.idle_ttl})")


    # async def shutdown(self) -> None:
    #     task = getattr(self, "_cleanup_task", None)
    #     if task and not task.done():
    #         task.cancel()
    #         try:
    #             await task
    #         except asyncio.CancelledError:
    #             pass
    #         logger.info("Pool cleanup task cancelled.")

    #     async with self._lock:
    #         for pool in self._pools.values():
    #             await pool.dispose()

    #         self._pools.clear()
    #         self._last_used.clear()
    #         logger.info("All pools shut down.")

    # async def record_metrics_task(self, interval: int = 30):
    #     async def _loop():
    #         while True:
    #             await asyncio.sleep(interval)
    #             for pool in self._pools.values():
    #                 try:
    #                     pool.collect_metrics()
    #                 except Exception:
    #                     logger.exception("Error collecting pool metrics")

    #     asyncio.create_task(_loop())

    # def get_pool_stats(self):
    #     stats = []
    #     for conn_id, pool in self._pools.items():
    #         stats.append(
    #             {
    #                 "db_connection_id": conn_id, 
    #                 "pool_stats": pool.get_stats()
    #             }
    #         )

        