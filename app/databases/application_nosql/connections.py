# from app.appConfig import settings
# from motor.motor_asyncio import AsyncIOMotorClient
# from .models import Transaction
# from beanie import init_beanie
# import time
# import asyncio


# from app.logger import get_logger


# logger = get_logger(__name__)

# # class ApplicationNoSQLDatabase:
# #     def __init__(self):
# #         self.nosql_client: AsyncIOMotorClient | None = None

# #     async def init(self):
# #         host = settings.nosql_host
# #         port = settings.nosql_port
# #         username = settings.nosql_username
# #         password = settings.nosql_password
# #         db = settings.nosql_database

# #         self.nosql_client = AsyncIOMotorClient(
# #             f"mongodb://{username}:{password}@{host}:{port}/{db}?authSource=admin"
# #         )
# #         await init_beanie(database=self.nosql_client[db], document_models=[Transaction])

# #     def get(self) -> AsyncIOMotorClient:
# #         if self.nosql_client is None:
# #             raise RuntimeError("MongoDB client not initialized")
# #         return self.nosql_client

# #     def close(self):
# #         if self.nosql_client:
# #             self.nosql_client.close()





# class ApplicationNoSQLDatabase:
#     """MongoDB connection wrapper with pool management"""

#     def __init__(self):
#         self.nosql_client: AsyncIOMotorClient | None = None
#         self._initialized = False

#     async def init(self):
#         """Initialize MongoDB connection with Motor pooling"""
#         if self._initialized:
#             return

#         try:
#             host = settings.nosql_host
#             port = settings.nosql_port
#             username = settings.nosql_username
#             password = settings.nosql_password
#             db = settings.nosql_database

#             # Motor automatically handles connection pooling
#             # Default pool size: 10, maxPoolSize: 50
#             self.nosql_client = AsyncIOMotorClient(
#                 f"mongodb://{username}:{password}@{host}:{port}/{db}?authSource=admin",
#                 minPoolSize=2,
#                 maxPoolSize=5,
#                 retryWrites=True,
#                 serverSelectionTimeoutMS=10_000, # 10 seconds
#             )

#             # Test connection
#             await self.nosql_client.admin.command("ping")

#             # Initialize Beanie ODM
#             await init_beanie(
#                 database=self.nosql_client[db], document_models=[Transaction]
#             )

#             self._initialized = True
#             logger.info("MongoDB connection initialized successfully")

#         except Exception as e:
#             logger.error(
#                 "Failed to initialize MongoDB",
#                 extra={"event_type": "mongodb_init_error", "error": str(e)},
#                 exc_info=True,
#             )
#             raise

#     def get(self) -> AsyncIOMotorClient:
#         """Get MongoDB client"""
#         if self.nosql_client is None:
#             raise RuntimeError("MongoDB client not initialized. Call init() first.")
#         return self.nosql_client

#     async def close(self):
#         """Close MongoDB connection"""
#         try:
#             if self.nosql_client:
#                 self.nosql_client.close()
#                 self._initialized = False
#                 logger.info("MongoDB connection closed")
#         except Exception as e:
#             logger.error(
#                 "Error closing MongoDB connection",
#                 extra={"event_type": "mongodb_close_error", "error": str(e)},
#                 exc_info=True,
#             )

#     def get_stats(self) -> dict:
#         """Get connection pool statistics"""
#         if not self.nosql_client:
#             return {}

#         try:
#             # Motor client stats
#             options = self.nosql_client.options
#             return {
#                 "min_pool_size": options.min_pool_size or 2,
#                 "max_pool_size": options.max_pool_size or 5,
#                 "initialized": self._initialized,
#             }
#         except Exception as e:
#             logger.warning(
#                 "Failed to get MongoDB stats",
#                 extra={"error": str(e)},
#             )
#             return {}
        
#     def test_connection(self) -> bool:
#         """Test MongoDB connection"""
#         try:
#             self.nosql_client.admin.command("ping")
#             return True
#         except Exception as e:
#             logger.error(
#                 "MongoDB connection test failed",
#                 extra={
#                     "event_type": "mongodb_connection_test_failure",
#                     "error_type": type(e).__name__,
#                     "error_message": str(e),
#                 },
#                 exc_info=True,
#             )
#             return False


# class ApplicationNoSQLPoolManager:
#     """Connection pool manager for MongoDB with idle cleanup"""

#     def __init__(self, idle_ttl: int = 3600):
#         self._pool: ApplicationNoSQLDatabase | None = None
#         self._last_used: float = 0
#         self._lock = asyncio.Lock()
#         self.idle_ttl = idle_ttl
#         self._cleanup_task = None

#     def start_cleanup_task(self, interval: int = 1800) -> None:
#         """Start background cleanup task for idle connections"""
#         logger.debug("Starting NoSQL pool cleanup task")

#         if self._cleanup_task and not self._cleanup_task.done():
#             logger.warning("Cleanup task already running; skipping.")
#             return

#         async def _loop() -> None:
#             while True:
#                 await asyncio.sleep(interval)
#                 try:
#                     await self.cleanup_idle_pools()
#                 except Exception:
#                     logger.exception("Error during idle pool cleanup")

#         self._cleanup_task = asyncio.create_task(_loop())
#         logger.info(
#             "NoSQL pool cleanup task started",
#             extra={
#                 "event_type": "cleanup_task_started",
#                 "interval": interval,
#                 "idle_ttl": self.idle_ttl,
#             },
#         )

#     async def get_pool(self) -> ApplicationNoSQLDatabase:
#         """Get or create MongoDB connection pool"""
#         if self._pool and self._pool._initialized:
#             self._last_used = time.time()
#             return self._pool

#         async with self._lock:
#             # Double-check after acquiring lock
#             if self._pool and self._pool._initialized:
#                 self._last_used = time.time()
#                 return self._pool

#             # Create and initialize new pool
#             self._pool = ApplicationNoSQLDatabase()
#             await self._pool.init()

#             self._last_used = time.time()
#             logger.info(
#                 "Created new NoSQL connection pool",
#                 extra={"event_type": "pool_created"},
#             )
#             return self._pool

#     async def cleanup_idle_pools(self) -> None:
#         """Close idle connections if TTL exceeded"""
#         if not self._pool:
#             return

#         now = time.time()
#         async with self._lock:
#             if self._pool and (now - self._last_used) > self.idle_ttl:
#                 await self._pool.close()
#                 self._pool = None
#                 logger.info(
#                     "Removed idle NoSQL pool",
#                     extra={
#                         "event_type": "pool_removed",
#                         "idle_seconds": int(now - self._last_used),
#                     },
#                 )

#     async def shutdown(self) -> None:
#         """Gracefully shutdown pool and cleanup task"""
#         # Cancel cleanup task
#         if self._cleanup_task and not self._cleanup_task.done():
#             self._cleanup_task.cancel()
#             try:
#                 await self._cleanup_task
#             except asyncio.CancelledError:
#                 pass
#             logger.info("NoSQL pool cleanup task cancelled")

#         # Close connection
#         async with self._lock:
#             if self._pool:
#                 await self._pool.close()
#                 self._pool = None
#                 logger.info("NoSQL pool shut down complete")

#     def get_stats(self) -> dict:
#         """Get pool statistics"""
#         if not self._pool:
#             return {"status": "not_initialized"}

#         stats = self._pool.get_stats()
#         stats.update({
#             "pool_initialized": self._pool._initialized,
#             "idle_time": time.time() - self._last_used,
#             "idle_ttl": self.idle_ttl,
#         })
#         return stats

from app.appConfig import settings
from motor.motor_asyncio import AsyncIOMotorClient
from .models import Transaction
from beanie import init_beanie
import time
import asyncio

from app.logger import get_logger


logger = get_logger(__name__)


class ApplicationNoSQLDatabase:
    """
    Application-level MongoDB connection wrapper.

    Motor manages its own internal connection pool. The MongoDB client must
    remain alive for the application lifetime after Beanie initialization and
    should only be closed during application shutdown.
    """

    def __init__(self):
        self.nosql_client: AsyncIOMotorClient | None = None
        self._initialized = False

    async def init(self) -> None:
        """Initialize MongoDB and bind Beanie document models."""
        if self._initialized and self.nosql_client is not None:
            return

        client: AsyncIOMotorClient | None = None

        try:
            host = settings.nosql_host
            port = settings.nosql_port
            username = settings.nosql_username
            password = settings.nosql_password
            database_name = settings.nosql_database

            mongo_uri = (
                f"mongodb://{username}:{password}"
                f"@{host}:{port}/{database_name}?authSource=admin"
            )

            client = AsyncIOMotorClient(
                mongo_uri,
                minPoolSize=2,
                maxPoolSize=5,
                retryWrites=True,
                serverSelectionTimeoutMS=10_000,
            )

            # Confirm that the new client can reach MongoDB.
            await client.admin.command("ping")

            # Bind Beanie models to this application-level MongoDB client.
            await init_beanie(
                database=client[database_name],
                document_models=[Transaction],
            )

            self.nosql_client = client
            self._initialized = True

            logger.info(
                "MongoDB connection initialized successfully",
                extra={
                    "event_type": "mongodb_init_success",
                    "database": database_name,
                },
            )

        except Exception as exc:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    logger.warning(
                        "Failed to close partially initialized MongoDB client",
                        exc_info=True,
                    )

            self.nosql_client = None
            self._initialized = False

            logger.error(
                "Failed to initialize MongoDB",
                extra={
                    "event_type": "mongodb_init_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise

    def get(self) -> AsyncIOMotorClient:
        """Return the active MongoDB client."""
        if self.nosql_client is None or not self._initialized:
            raise RuntimeError(
                "MongoDB client is not initialized. Call init() first."
            )

        return self.nosql_client

    async def close(self) -> None:
        """Close MongoDB during application shutdown only."""
        try:
            if self.nosql_client is not None:
                self.nosql_client.close()

            # Clear the reference so a closed MongoClient cannot be reused.
            self.nosql_client = None
            self._initialized = False

            logger.info(
                "MongoDB connection closed",
                extra={"event_type": "mongodb_connection_closed"},
            )

        except Exception as exc:
            self.nosql_client = None
            self._initialized = False

            logger.error(
                "Error closing MongoDB connection",
                extra={
                    "event_type": "mongodb_close_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                exc_info=True,
            )

    def get_stats(self) -> dict:
        """Return basic Motor connection-pool statistics."""
        if self.nosql_client is None or not self._initialized:
            return {
                "initialized": False,
                "status": "not_initialized",
            }

        try:
            pool_options = self.nosql_client.options.pool_options

            return {
                "min_pool_size": pool_options.min_pool_size,
                "max_pool_size": pool_options.max_pool_size,
                "initialized": self._initialized,
                "status": "initialized",
            }

        except Exception as exc:
            logger.warning(
                "Failed to get MongoDB stats",
                extra={
                    "event_type": "mongodb_stats_error",
                    "error": str(exc),
                },
                exc_info=True,
            )
            return {
                "initialized": self._initialized,
                "status": "stats_unavailable",
            }

    async def test_connection(self) -> bool:
        """Test whether the current MongoDB client is usable."""
        if self.nosql_client is None or not self._initialized:
            return False

        try:
            await self.nosql_client.admin.command("ping")
            return True

        except Exception as exc:
            logger.error(
                "MongoDB connection test failed",
                extra={
                    "event_type": "mongodb_connection_test_failure",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                exc_info=True,
            )
            return False


class ApplicationNoSQLPoolManager:
    """
    Application-level MongoDB manager.

    The same MongoDB client is reused for all requests. Idle cleanup does not
    close it because Beanie document models remain bound to that client.
    """

    def __init__(self, idle_ttl: int = 3600):
        self._pool: ApplicationNoSQLDatabase | None = None
        self._last_used: float = 0.0
        self._lock = asyncio.Lock()
        self.idle_ttl = idle_ttl
        self._cleanup_task: asyncio.Task | None = None

    def start_cleanup_task(self, interval: int = 1800) -> None:
        """Start a lightweight NoSQL maintenance task."""
        logger.debug("Starting NoSQL pool maintenance task")

        if self._cleanup_task and not self._cleanup_task.done():
            logger.warning("NoSQL maintenance task already running; skipping.")
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)

                try:
                    await self.cleanup_idle_pools()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error during NoSQL pool maintenance")

        self._cleanup_task = asyncio.create_task(_loop())

        logger.info(
            "NoSQL pool maintenance task started",
            extra={
                "event_type": "cleanup_task_started",
                "interval": interval,
                "idle_ttl": self.idle_ttl,
            },
        )

    async def get_pool(self) -> ApplicationNoSQLDatabase:
        """Get or initialize the application-level MongoDB connection."""
        async with self._lock:
            if self._pool is None:
                self._pool = ApplicationNoSQLDatabase()

            if not self._pool._initialized:
                await self._pool.init()
            else:
                # Raises immediately if state is inconsistent.
                self._pool.get()

            self._last_used = time.time()

            logger.debug(
                "Using application NoSQL connection pool",
                extra={
                    "event_type": "pool_reused",
                    "initialized": self._pool._initialized,
                },
            )

            return self._pool

    async def cleanup_idle_pools(self) -> None:
        """
        Keep the application-level MongoDB client alive.

        Motor manages its own socket pool. Closing the application-level client
        while the app is running can leave Beanie bound to a closed collection
        and trigger `Cannot use MongoClient after close`.
        """
        if self._pool is None:
            return

        idle_seconds = (
            time.time() - self._last_used
            if self._last_used
            else 0.0
        )

        logger.debug(
            "Skipping MongoDB application-client idle cleanup",
            extra={
                "event_type": "nosql_idle_cleanup_skipped",
                "idle_seconds": int(idle_seconds),
                "idle_ttl": self.idle_ttl,
                "reason": (
                    "Motor manages socket pooling and Beanie requires an "
                    "application-lifetime MongoDB client"
                ),
            },
        )

    async def shutdown(self) -> None:
        """Stop maintenance and close MongoDB during application shutdown."""
        logger.info(
            "Starting NoSQL pool manager shutdown",
            extra={"event_type": "nosql_shutdown_started"},
        )

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

            logger.info(
                "NoSQL pool maintenance task cancelled",
                extra={"event_type": "cleanup_task_cancelled"},
            )

        self._cleanup_task = None

        async with self._lock:
            if self._pool is not None:
                await self._pool.close()
                self._pool = None

            self._last_used = 0.0

        logger.info(
            "NoSQL pool shut down complete",
            extra={"event_type": "nosql_shutdown_completed"},
        )

    def get_stats(self) -> dict:
        """Return NoSQL manager and Motor pool statistics."""
        if self._pool is None:
            return {
                "status": "not_initialized",
                "pool_initialized": False,
                "idle_time": 0.0,
                "idle_ttl": self.idle_ttl,
            }

        stats = self._pool.get_stats()
        stats.update(
            {
                "pool_initialized": self._pool._initialized,
                "idle_time": (
                    time.time() - self._last_used
                    if self._last_used
                    else 0.0
                ),
                "idle_ttl": self.idle_ttl,
            }
        )

        return stats
