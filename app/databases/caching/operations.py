# import zstandard as zstd
# import json
# from ..connections import caching_client
# from typing import Literal
# from app.core.prometheus_metrics import DB_REPLACE_CACHE_HITS
# from app.appConfig import settings


# compressor = zstd.ZstdCompressor(level=3)
# decompressor = zstd.ZstdDecompressor()


# async def cache_data(key: str, value, ttl: int = 3600):
#     try:
#         key = settings.caching_prefix+key
#         print(f"Caching Data - {key}")
#         json_bytes = json.dumps(value).encode("utf-8")
#         compressed = compressor.compress(json_bytes)
#         await caching_client.client.setex(key, ttl, compressed)
#         return True
#     except Exception as e:
#         print(str(e))
#         return False


# async def get_cached_data(key: str, db_name: str, endpoint: Literal["tables", "filters", "suggestions", "insights", "graphs", "autocomplete"] = "filters"):
#     try:
#         key = settings.caching_prefix+key
#         compressed = await caching_client.client.get(key)
#         if not compressed:
#             return None
#         print(f"Retreiving from Cache - {key}")
#         json_bytes = decompressor.decompress(compressed)
#         DB_REPLACE_CACHE_HITS.labels(db_name, endpoint).inc()
#         return json.loads(json_bytes.decode("utf-8"))
#     except Exception as e:
#         print(str(e))
#         return False


# async def cache_delete_key(key: str):
#     try:
#         key = settings.caching_prefix+key
#         await caching_client.client.delete(key)
#         print(f"Key deleted - {key}")
#         return True
#     except Exception as e:
#         print(str(e))
#         return False


import zstandard as zstd
import json
from typing import Any, Optional, Literal
from app.core.prometheus_metrics import DB_REPLACE_CACHE_HITS
from app.appConfig import settings
from app.logger import get_logger
from ..dependencies import get_caching_client


logger = get_logger(__name__)

# Compression settings
COMPRESSION_LEVEL = 3
DEFAULT_TTL = 3600
compressor = zstd.ZstdCompressor(level=COMPRESSION_LEVEL)
decompressor = zstd.ZstdDecompressor()


async def cache_data(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Cache data with optional compression and TTL.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time-to-live in seconds (default: 3600)
        
    Returns:
        True if caching successful
        
    Raises:
        ValueError: If key is empty
        Exception: If Redis operation fails
    """
    if not key or not isinstance(key, str):
        raise ValueError("Key must be a non-empty string")

    if ttl <= 0:
        raise ValueError("TTL must be positive")

    try:
        client = await get_caching_client()

        full_key = settings.caching_prefix + key
        json_bytes = json.dumps(value).encode("utf-8")
        compressed = compressor.compress(json_bytes)

        await client.setex(full_key, ttl, compressed)

        logger.debug(
            "Data cached successfully",
            extra={
                "event_type": "cache_set",
                "key": full_key,
                "ttl": ttl,
                "size_bytes": len(compressed),
            }
        )
        return True

    except Exception as e:
        logger.error(
            "Failed to cache data",
            extra={
                "event_type": "cache_set_error",
                "key": key,
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def get_cached_data(key: str, db_name: str, endpoint: Literal["tables", "filters", "suggestions", "insights", "graphs", "autocomplete"] = "filters") -> Optional[Any]:
    """
    Retrieve and decompress cached data.
    
    Args:
        key: Cache key
        db_name: Database name for metrics labeling
        
    Returns:
        Cached value if found, None if not found
        
    Raises:
        ValueError: If key is empty
        Exception: If Redis operation fails
    """
    if not key or not isinstance(key, str):
        raise ValueError("Key must be a non-empty string")

    try:
        client = await get_caching_client()

        full_key = settings.caching_prefix + key
        compressed = await client.get(full_key)

        if not compressed:
            logger.debug(
                "Cache miss",
                extra={
                    "event_type": "cache_miss",
                    "key": full_key,
                }
            )
            return None

        json_bytes = decompressor.decompress(compressed)
        data = json.loads(json_bytes.decode("utf-8"))

        DB_REPLACE_CACHE_HITS.labels(db_name, endpoint).inc()

        logger.debug(
            "Data retrieved from cache",
            extra={
                "event_type": "cache_hit",
                "key": full_key,
                "db_name": db_name,
                "size_bytes": len(compressed),
            }
        )
        return data

    except json.JSONDecodeError as e:
        logger.error(
            "Failed to deserialize cached data",
            extra={
                "event_type": "cache_deserialize_error",
                "key": key,
                "error": str(e),
            },
            exc_info=True,
        )
        raise

    except Exception as e:
        logger.error(
            "Failed to retrieve cached data",
            extra={
                "event_type": "cache_get_error",
                "key": key,
                "db_name": db_name,
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def cache_delete_key(key: str) -> bool:
    """
    Delete a cached key.
    
    Args:
        key: Cache key to delete
        
    Returns:
        True if key was deleted, False if key didn't exist
        
    Raises:
        ValueError: If key is empty
        Exception: If Redis operation fails
    """
    if not key or not isinstance(key, str):
        raise ValueError("Key must be a non-empty string")

    try:
        client = await get_caching_client()

        full_key = settings.caching_prefix + key
        deleted_count = await client.delete(full_key)

        if deleted_count > 0:
            logger.info(
                "Cache key deleted",
                extra={
                    "event_type": "cache_delete",
                    "key": full_key,
                }
            )
            return True
        else:
            logger.debug(
                "Cache key not found for deletion",
                extra={
                    "event_type": "cache_delete_not_found",
                    "key": full_key,
                }
            )
            return False

    except Exception as e:
        logger.error(
            "Failed to delete cache key",
            extra={
                "event_type": "cache_delete_error",
                "key": key,
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete multiple cache keys matching a pattern.
    
    Args:
        pattern: Redis pattern (e.g., "user:*")
        
    Returns:
        Number of keys deleted
        
    Raises:
        ValueError: If pattern is empty
        Exception: If Redis operation fails
    """
    if not pattern or not isinstance(pattern, str):
        raise ValueError("Pattern must be a non-empty string")

    try:
        client = await get_caching_client()

        full_pattern = settings.caching_prefix + pattern
        cursor = "0"
        deleted_count = 0

        while cursor != 0:
            cursor, keys = await client.scan(cursor, match=full_pattern, count=100)
            if keys:
                deleted_count += await client.delete(*keys)

        logger.info(
            "Cache pattern deleted",
            extra={
                "event_type": "cache_pattern_delete",
                "pattern": full_pattern,
                "deleted_count": deleted_count,
            }
        )
        return deleted_count

    except Exception as e:
        logger.error(
            "Failed to delete cache pattern",
            extra={
                "event_type": "cache_pattern_delete_error",
                "pattern": pattern,
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def cache_clear_all() -> bool:
    """
    Clear all cached data with the current prefix.
    
    Returns:
        True if successful
        
    Raises:
        Exception: If Redis operation fails
    """
    try:
        deleted_count = await cache_delete_pattern("*")
        logger.warning(
            "All cache cleared",
            extra={
                "event_type": "cache_clear_all",
                "deleted_count": deleted_count,
            }
        )
        return True

    except Exception as e:
        logger.error(
            "Failed to clear all cache",
            extra={
                "event_type": "cache_clear_all_error",
                "error": str(e),
            },
            exc_info=True,
        )
        raise


async def get_cache_size() -> dict:
    """
    Get cache statistics and memory usage.
    
    Returns:
        Dictionary with cache stats
        
    Raises:
        Exception: If Redis operation fails
    """
    try:       
        client = await get_caching_client()

        info = await client.info("memory")
        dbsize = await client.dbsize()

        return {
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "total_keys": dbsize,
            "memory_stats": info,
        }

    except Exception as e:
        logger.error(
            "Failed to get cache size",
            extra={
                "event_type": "cache_size_error",
                "error": str(e),
            },
            exc_info=True,
        )
        raise