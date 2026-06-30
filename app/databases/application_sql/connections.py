from app.appConfig import settings
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from app.logger import get_logger
import time


logger = get_logger(__name__)


class ApplicationDatabase:
    def __init__(self, async_required: bool = True) -> None:
        self.async_required = async_required
        self.engine: AsyncEngine | None = None
        self.session_maker: async_sessionmaker[AsyncSession] | None = None

    def get_url(self) -> URL:
        return URL.create(
            drivername="mssql+aioodbc",
            username=settings.sql_username,
            password=settings.sql_password,
            host=settings.sql_host,
            port=settings.sql_port,
            database=settings.sql_database,
            query={
                "driver": "ODBC Driver 17 for SQL Server",
            },
        )
    
    def get_sync_url(self) -> URL:
        return URL.create(
            drivername="mssql+pyodbc",
            username=settings.sql_username,
            password=settings.sql_password,
            host=settings.sql_host,
            port=settings.sql_port,
            database=settings.sql_database,
            query={
                "driver": "ODBC Driver 17 for SQL Server",
            },
        )

    def init_engine(self) -> None:
        if self.engine:
            return

        self.engine = create_async_engine(
            self.get_url(),
            echo=False,
            pool_size=settings.sql_pool_size,
            max_overflow=settings.sql_max_overflow,
            pool_timeout=settings.sql_pool_timeout,
            pool_recycle=settings.sql_pool_recycle,
            pool_pre_ping=True,
            connect_args={"timeout": 30}
        )

        self.session_maker = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    async def dispose(self) -> None:
        if self.engine:
            await self.engine.dispose()

    def get_stats(self) -> dict:
        if not self.engine:
            return {}

        pool = self.engine.pool
        stats = {
            "pool_size": pool.size(),
            "checked_in_connections": pool.checkedin(),
            "checked_out_connections": pool.checkedout(),
            "overflow_connections": pool.overflow(),
            "current_overflow": pool.overflow() - pool.size(),
        }
        return stats


class ApplicationPoolManager:
    def __init__(self, idle_ttl: int = 3600):
        self._pool: ApplicationDatabase | None = None
        self._last_used: float = 0
        self._lock = asyncio.Lock()

        self.idle_ttl = idle_ttl

    def start_cleanup_task(self, interval: int = 1800) -> None:
        logger.debug("Starting pool cleanup task")
        if getattr(self, "_cleanup_task", None) and not self._cleanup_task.done():
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
        logger.info(f"Pool cleanup task started (interval={interval}s, idle_ttl={self.idle_ttl}s, last_used={self._last_used})")

    async def get_pool(self) -> ApplicationDatabase:
        if self._pool:
            self._last_used = time.time()
            return self._pool

        async with self._lock:
            if self._pool:
                self._last_used = time.time()
                return self._pool

            # create new pool
            self._pool = ApplicationDatabase() 
            
            self._pool.init_engine()

            self._last_used = time.time()
            logger.info(f"Created new Application pool")
            return self._pool

    async def cleanup_idle_pools(self):
        if self._pool:
            logger.debug(f"Checking for cleanup")
            now = time.time()
            async with self._lock:
                if (now - self._last_used) > self.idle_ttl:
                    await self._pool.dispose()
                    self._pool = None
                    logger.info(f"Removed idle Application pool (idle > {self.idle_ttl})")

    async def shutdown(self) -> None:
        task = getattr(self, "_cleanup_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Pool cleanup task cancelled for Application SQL.")

        async with self._lock:
            if self._pool:
                await self._pool.dispose()
            logger.info("Application pool shut down complete")










