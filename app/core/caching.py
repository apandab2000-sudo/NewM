import zstandard as zstd
import json

compressor = zstd.ZstdCompressor(level=3)
decompressor = zstd.ZstdDecompressor()


async def cache_data(redis_client, key: str, value, ttl: int):
    try:
        print("############# CACHING DATA ########################")
        json_bytes = json.dumps(value).encode("utf-8")
        compressed = compressor.compress(json_bytes)
        await redis_client.setex(key, ttl, compressed)
        return True
    except Exception as e:
        print(str(e))
        return False


async def get_cached_data(redis_client, key: str):
    compressed = await redis_client.get(key)
    if not compressed:
        return None
    print("############# RETREIVING FROM CACHE ########################")
    json_bytes = decompressor.decompress(compressed)
    return json.loads(json_bytes.decode("utf-8"))
