# from qdrant_client import AsyncQdrantClient
# from app.appConfig import settings


# vector_db: AsyncQdrantClient | None = None


# class VectorClient:
#     def __init__(self):
#         self.settings = settings
#         self.vector_db: AsyncQdrantClient | None = None 
        
#     def init(self):
#         self.vector_db = AsyncQdrantClient(host=self.settings.vector_host, port=self.settings.vector_port)

#     async def close_vectordb(self):
#         if self.vector_db:
#             await self.vector_db.close()

#     def get_vector_db(self):
#         if not self.vector_db:
#             self.init()
#         return self.vector_db


from qdrant_client import AsyncQdrantClient
from app.appConfig import settings
from app.logger import get_logger
import asyncio
import time


logger = get_logger(__name__)


class VectorClient:
    """Vector database (Qdrant) connection wrapper with lifecycle management"""

    def __init__(self):
        self.vector_db: AsyncQdrantClient | None = None
        self._initialized = False

    async def init(self) -> AsyncQdrantClient:
        """
        Initialize async Qdrant client connection.

        Returns:
            AsyncQdrantClient instance

        Raises:
            RuntimeError: If connection fails
        """
        if self._initialized:
            return self.vector_db

        try:
            self.vector_db = AsyncQdrantClient(
                host=settings.vector_host,
                port=settings.vector_port,
                timeout=10,
            )

            # Test connection
            await self.vector_db.get_collections()
            self._initialized = True

            logger.info(
                "Vector database connection initialized",
                extra={
                    "event_type": "vector_db_init_success",
                    "host": settings.vector_host,
                    "port": settings.vector_port,
                },
            )
            return self.vector_db

        except Exception as e:
            logger.error(
                "Failed to initialize vector database",
                extra={
                    "event_type": "vector_db_init_error",
                    "error": str(e),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to connect to Vector DB: {str(e)}")

    async def close(self) -> None:
        """Close vector database connection"""
        try:
            if self.vector_db:
                await self.vector_db.close()
            self._initialized = False
            logger.info(
                "Vector database connection closed",
                extra={"event_type": "vector_db_closed"},
            )
        except Exception as e:
            logger.error(
                "Error closing vector database",
                extra={"event_type": "vector_db_close_error", "error": str(e)},
                exc_info=True,
            )

    def get(self) -> AsyncQdrantClient:
        """
        Get vector database client.

        Returns:
            AsyncQdrantClient

        Raises:
            RuntimeError: If not initialized
        """
        if self.vector_db is None or not self._initialized:
            raise RuntimeError("Vector database not initialized. Call init() first.")
        return self.vector_db


class VectorPoolManager:
    """Pool manager for vector database with idle cleanup"""

    def __init__(self, idle_ttl: int = 3600):
        """
        Initialize vector pool manager.

        Args:
            idle_ttl: Idle time-to-live in seconds (default: 1 hour)
        """
        self._pool: VectorClient | None = None
        self._last_used: float = 0
        self._lock = asyncio.Lock()
        self.idle_ttl = idle_ttl
        self._cleanup_task = None

    def start_cleanup_task(self, interval: int = 1800) -> None:
        """
        Start background cleanup task for idle connections.

        Args:
            interval: Cleanup check interval in seconds (default: 30 mins)
        """
        logger.debug("Starting vector pool cleanup task")

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
            "Vector pool cleanup task started",
            extra={
                "event_type": "cleanup_task_started",
                "interval": interval,
                "idle_ttl": self.idle_ttl,
            },
        )

    async def get_pool(self) -> VectorClient:
        """
        Get or create vector database pool.

        Returns:
            VectorClient instance
        """
        if self._pool and self._pool._initialized:
            self._last_used = time.time()
            return self._pool

        async with self._lock:
            # Double-check after lock
            if self._pool and self._pool._initialized:
                self._last_used = time.time()
                return self._pool

            # Create and initialize new pool
            self._pool = VectorClient()
            await self._pool.init()
            self._last_used = time.time()

            logger.info(
                "Created new vector connection pool",
                extra={"event_type": "pool_created"},
            )
            return self._pool

    async def cleanup_idle_pools(self) -> None:
        """Close idle vector DB connections if TTL exceeded"""
        if not self._pool:
            return

        now = time.time()
        async with self._lock:
            if self._pool and (now - self._last_used) > self.idle_ttl:
                await self._pool.close()
                self._pool = None
                logger.info(
                    "Removed idle vector pool",
                    extra={
                        "event_type": "pool_removed",
                        "idle_seconds": int(now - self._last_used),
                    },
                )

    async def shutdown(self) -> None:
        """Gracefully shutdown pool and cleanup task"""
        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Vector pool cleanup task cancelled")

        # Close connection
        async with self._lock:
            if self._pool:
                await self._pool.close()
                self._pool = None
                logger.info("Vector pool shut down complete")
