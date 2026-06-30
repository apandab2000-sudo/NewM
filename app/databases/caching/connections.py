# import redis.asyncio as aioredis
# from app.appConfig import settings

# class CachingDatabase:
#     def __init__(self):
#         self.settings = settings
#         self.client: aioredis.Redis | None = None

#     def init(self):
#         self.client = aioredis.Redis(
#             host=self.settings.caching_host,
#             port=self.settings.caching_port,
#             db=self.settings.caching_database,
#             decode_responses=False,
#         )
#         return self.client
    
#     async def close(self):
#         if self.client:
#             await self.client.close()



import redis.asyncio as aioredis
from app.appConfig import settings
# from logger import get_logger
import asyncio
import time
from app.logger import get_logger

logger = get_logger(__name__)

# Default compression settings
DEFAULT_COMPRESSION_LEVEL = 3
DEFAULT_POOL_SIZE = 5
DEFAULT_POOL_TIMEOUT = 30


class CachingDatabase:
    """Redis connection wrapper with connection pooling and lifecycle management"""

    def __init__(self):
        self.client: aioredis.Redis | None = None
        self._initialized = False
        self._pool = None

    async def init(self) -> aioredis.Redis:
        """
        Initialize Redis connection with connection pooling.
        
        Returns:
            Redis client instance
            
        Raises:
            RuntimeError: If connection fails
        """
        if self._initialized:
            return self.client

        try:
            # Create connection pool with proper configuration
            self.client = aioredis.Redis(
                host=settings.caching_host,
                port=settings.caching_port,
                db=settings.caching_database,
                decode_responses=False,
            )

            # Test connection with ping
            await self.client.ping()
            self._initialized = True

            logger.info(
                "Redis cache connection initialized",
                extra={
                    "event_type": "redis_init_success",
                    "host": settings.caching_host,
                    "port": settings.caching_port,
                    "db": settings.caching_database,
                }
            )
            return self.client

        except Exception as e:
            logger.error(
                "Failed to initialize Redis connection",
                extra={
                    "event_type": "redis_init_error",
                    "host": settings.caching_host,
                    "port": settings.caching_port,
                    "db": settings.caching_database,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to connect to Redis: {str(e)}")

    async def close(self) -> None:
        """Close Redis connection and cleanup pool"""
        try:
            if self.client:
                await self.client.close()
            self._initialized = False
            logger.info(
                "Redis connection closed",
                extra={"event_type": "redis_closed"}
            )
        except Exception as e:
            logger.error(
                "Error closing Redis connection",
                extra={
                    "event_type": "redis_close_error",
                    "error": str(e),
                },
                exc_info=True,
            )

    def get(self) -> aioredis.Redis:
        """
        Get Redis client instance.
        
        Returns:
            Redis client
            
        Raises:
            RuntimeError: If client not initialized
        """
        if self.client is None or not self._initialized:
            raise RuntimeError("Redis client not initialized. Call init() first.")
        return self.client

    # @asynccontextmanager
    # async def pipeline(self):
    #     """Async context manager for pipeline operations"""
    #     pipe = self.client.pipeline()
    #     try:
    #         yield pipe
    #         await pipe.execute()
    #     finally:
    #         await pipe.reset()

    async def get_stats(self) -> dict:
        """
        Get connection pool statistics.
        
        Returns:
            Dictionary with pool stats
        """
        try:
            if not self.client or not self._initialized:
                return {"status": "not_initialized"}

            info = await self.client.info("stats")
            return {
                "status": "connected",
                "initialized": self._initialized,
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "total_net_input_bytes": info.get("total_net_input_bytes", 0),
                "total_net_output_bytes": info.get("total_net_output_bytes", 0),
            }
        except Exception as e:
            logger.warning(
                "Failed to get Redis stats",
                extra={"error": str(e)}
            )
            return {"status": "error", "error": str(e)}


class CachingPoolManager:
    """Connection pool manager for Redis with idle cleanup"""

    def __init__(self, idle_ttl: int = 1800):
        """
        Initialize caching pool manager.
        
        Args:
            idle_ttl: Idle time-to-live in seconds before cleanup (default: 30 minutes)
        """
        self._pool: CachingDatabase | None = None
        self._last_used: float = 0
        self._lock = asyncio.Lock()
        self.idle_ttl = idle_ttl
        self._cleanup_task = None

    def start_cleanup_task(self, interval: int = 1800) -> None: # 30 minutes
        """
        Start background cleanup task for idle connections.
        
        Args:
            interval: Cleanup check interval in seconds (default: 30 minutes)
        """
        logger.debug("Starting caching pool cleanup task")

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
            "Caching pool cleanup task started",
            extra={
                "event_type": "cleanup_task_started",
                "interval": interval,
                "idle_ttl": self.idle_ttl,
            }
        )

    async def get_pool(self) -> CachingDatabase:
        """
        Get or create Redis connection pool.
        
        Returns:
            CachingDatabase instance
        """
        if self._pool and self._pool._initialized:
            self._last_used = time.time()
            return self._pool

        async with self._lock:
            # Double-check after acquiring lock
            if self._pool and self._pool._initialized:
                self._last_used = time.time()
                return self._pool

            # Create and initialize new pool
            self._pool = CachingDatabase()
            await self._pool.init()

            self._last_used = time.time()
            logger.info(
                "Created new caching connection pool",
                extra={"event_type": "pool_created"}
            )
            return self._pool

    async def cleanup_idle_pools(self) -> None:
        """Close idle Redis connections if TTL exceeded"""
        if not self._pool:
            return

        now = time.time()
        async with self._lock:
            if self._pool and (now - self._last_used) > self.idle_ttl:
                await self._pool.close()
                self._pool = None
                logger.info(
                    "Removed idle caching pool",
                    extra={
                        "event_type": "pool_removed",
                        "idle_seconds": int(now - self._last_used),
                    }
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
            logger.info("Caching pool cleanup task cancelled")

        # Close connection
        async with self._lock:
            if self._pool:
                await self._pool.close()
                self._pool = None
                logger.info("Caching pool shut down complete")

    async def get_stats(self) -> dict:
        """Get pool statistics"""
        if not self._pool:
            return {"status": "not_initialized"}

        stats = await self._pool.get_stats()
        stats.update({
            "pool_initialized": self._pool._initialized,
            "idle_time": time.time() - self._last_used,
            "idle_ttl": self.idle_ttl,
        })
        return stats

