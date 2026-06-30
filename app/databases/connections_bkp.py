from urllib.parse import quote
from sqlalchemy import create_engine, inspect
from app.logger import get_logger
from functools import cached_property

logger = get_logger()


from .application_sql.connections import ApplicationPoolManager
from .application_nosql.connections import ApplicationNoSQLDatabase
from .caching.connections import CachingDatabase
from .vector.connections import VectorClient 
from .client_sql.connections import MultiDatabasePoolManager
from app.appConfig import settings

# Initialing SQL Connections
application_pool_manager = ApplicationPoolManager()

async def get_db_async():
    application_sql_db = await application_pool_manager.get_pool()
    if not application_sql_db.session_maker:
        raise RuntimeError("Engine not initialized")
    
    async with application_sql_db.session_maker() as session:
        try:
            yield session
        finally:
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


class ClientConnection:
    def __init__(self, USERNAME: str, PASSWORD: str, HOST: str, PORT: str, DATABASE: str, DIALECT: str = "mssql", DRIVER = None):
        self.UID = USERNAME
        self.PWD = PASSWORD
        self.SERVER = HOST
        self.PORT = PORT
        self.DATABASE = DATABASE
        self.DIALECT = DIALECT.lower()
        self.engine = self._create_engine()

    def _default_driver(self):
        return {
            "mssql": "ODBC+Driver+17+for+SQL+Server",  # for pyodbc
            "mysql": "pymysql",
            "pgsql": "psycopg2",
            "clickhouse": None  # if using sqlalchemy-clickhouse
        }.get(self.DIALECT)

    def _create_engine(self):
        driver = self._default_driver()
        if self.DIALECT == "mssql":
            driver_str = f"driver={driver}"
            url =  f'mssql+pyodbc://{self.UID}:{quote(self.PWD)}@{self.SERVER}:{self.PORT}/{self.DATABASE}?'+f'{driver_str}'
        else:
            driver_part = f"+{driver}" if driver else ""
            url = (
                f"{self.DIALECT}{driver_part}://{self.UID}:{quote(self.PWD)}@"
                f"{self.SERVER}:{self.PORT}/{self.DATABASE}"
            )
        return create_engine(url, future=True)

    def check_connectivity(self) -> bool:
        try:
            with self.engine.connect() as conn:
                return True
        except Exception as e:
            logger.error(f"Connection Error: {e!r}")
            return False

    @cached_property
    def inspector(self):
        return inspect(self.engine)

    def get_available_tables(self) -> list:
        return self.inspector.get_table_names()

    def get_table_info(self, table: str) -> list:
        return [
            {"col_name": col["name"], "data_type": str(col["type"])}
            for col in self.inspector.get_columns(table)
        ]

    def get_primary_key_constraints(self, table: str) -> list:
        return self.inspector.get_pk_constraint(table).get("constrained_columns", [])

    def get_foreign_key_constraints(self, table: str) -> list:
        fks = self.inspector.get_foreign_keys(table)
        return [col for fk in fks for col in fk.get("constrained_columns", [])]

    def get_relationships(self, table: str) -> list:
        relationships = []
        for fk in self.inspector.get_foreign_keys(table):
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