import time
from app.databases.connections import AioODBCPool
from pydantic import BaseModel
from typing import List, Literal, Optional
import pyodbc
import asyncio
from app.logger import get_logger
from sqlalchemy import text

logger = get_logger()


class QueryResult(BaseModel):
    sql: str
    rows: List[tuple]
    columns: List[str]
    pool_wait_ms: float
    exec_ms: float
    total_ms: float
    row_count: int
    status: Literal["success", "error", "timeoutError", "programmingError"]
    error: Optional[str] = None


# async def get_table_from_sql(
#     pool: AioODBCPool,
#     sql_query: str,
#     row_limit: int | None = 500,
#     query_timeout: int = 10,
# ):
#     start_total = time.time()
#     pool_wait_start = time.time()
#     pool_wait_ms = 0
#     exec_start = time.time()
#     exec_ms = 0
#     conn = None
    
#     try:
#         conn = await pool.acquire()
#         pool_wait_ms = (time.time() - pool_wait_start) * 1000
#         exec_start = time.time()

#         async def _exec():
#             async with conn.cursor() as cursor:
#                 await cursor.execute(sql_query)
#                 if row_limit:
#                     rows = await cursor.fetchmany(row_limit)
#                 else:
#                     rows = await cursor.fetchall()
#                 columns = (
#                     [desc[0] for desc in cursor.description]
#                     if cursor.description
#                     else []
#                 )
#             return rows, columns

#         rows, columns = await asyncio.wait_for(_exec(), timeout=query_timeout)
#         exec_ms = (time.time() - exec_start) * 1000
#         total_ms = (time.time() - start_total) * 1000

#         logger.info(f"Query Execution took {total_ms / 1000:.2f}s")
#         return QueryResult(
#             sql=sql_query,
#             rows=rows,
#             columns=columns,
#             pool_wait_ms=pool_wait_ms,
#             exec_ms=exec_ms,
#             total_ms=total_ms,
#             row_count=len(rows),
#             status="success",
#         )

#     except asyncio.TimeoutError as e:
#         logger.error(f"Timeout Error - {repr(e)}")

#         if conn:
#             try:
#                 await conn.close()  # Close the connection instead of releasing
#                 conn = None  # Prevent release in finally block
#             except Exception as cancel_error:
#                 logger.error(f"Error closing timed-out connection: {cancel_error}")
        
#         return QueryResult(
#             sql=sql_query,
#             rows=[],
#             columns=[],
#             pool_wait_ms=pool_wait_ms,
#             exec_ms=(time.time() - exec_start) * 1000,
#             total_ms=(time.time() - start_total) * 1000,
#             row_count=0,
#             status="timeoutError",
#             error=str(e),
#         )
        

#     except pyodbc.ProgrammingError as e:
#         logger.error(f"Programming Error - {repr(e)}")
#         return QueryResult(
#             sql=sql_query,
#             rows=[],
#             columns=[],
#             pool_wait_ms=pool_wait_ms,
#             exec_ms=(time.time() - exec_start) * 1000,
#             total_ms=(time.time() - start_total) * 1000,
#             row_count=0,
#             status="programmingError",
#             error=str(e),
#         )
#     except Exception as e:
#         logger.error(f"Error - {repr(e)}")
#         return QueryResult(
#             sql=sql_query,
#             rows=[],
#             columns=[],
#             pool_wait_ms=pool_wait_ms,
#             exec_ms=(time.time() - exec_start) * 1000,
#             total_ms=(time.time() - start_total) * 1000,
#             row_count=0,
#             status="programmingError",
#             error=str(e),
#         )
#     finally:
#         if conn is not None:
#             await pool.release(conn)


async def get_table_from_sql(
    pool: AioODBCPool,
    sql_query: str,
    row_limit: int | None = 500,
    query_timeout: int = 10,
):
    start_total = time.time()

    try:
        async with pool.engine.connect() as conn:
            
            pool_wait_ms = (time.time() - start_total) * 1000
            exec_start = time.time()
            
            result = await asyncio.wait_for(
                conn.execute(text(sql_query)),
                timeout=query_timeout
            )
            
            # Fetch rows
            if row_limit:
                rows = result.fetchmany(row_limit)
            else:
                rows = result.fetchall()
            
            columns = list(result.keys()) if result.keys() else []
            exec_ms = (time.time() - exec_start) * 1000
            total_ms = (time.time() - start_total) * 1000
            
            logger.info(f"Query took {total_ms / 1000:.2f}s")
            
            return QueryResult(
                sql=sql_query,
                rows=[tuple(row) for row in rows],
                columns=columns,
                pool_wait_ms=pool_wait_ms,
                exec_ms=exec_ms,
                total_ms=total_ms,
                row_count=len(rows),
                status="success",
            )
            
    except asyncio.TimeoutError as e:
        logger.error(f"Query timeout: {e}")
        return QueryResult(
            sql=sql_query,
            rows=[],
            columns=[],
            pool_wait_ms=0,
            exec_ms=(time.time() - start_total) * 1000,
            total_ms=(time.time() - start_total) * 1000,
            row_count=0,
            status="timeoutError",
            error=str(e),
        )
    
    except pyodbc.ProgrammingError as e:
        logger.error(f"Programming Error - {repr(e)}")
        return QueryResult(
            sql=sql_query,
            rows=[],
            columns=[],
            pool_wait_ms=pool_wait_ms,
            exec_ms=(time.time() - exec_start) * 1000,
            total_ms=(time.time() - start_total) * 1000,
            row_count=0,
            status="programmingError",
            error=str(e),
        )
        
    except Exception as e:
        logger.error(f"Query error: {e}")
        return QueryResult(
            sql=sql_query,
            rows=[],
            columns=[],
            pool_wait_ms=0,
            exec_ms=(time.time() - start_total) * 1000,
            total_ms=(time.time() - start_total) * 1000,
            row_count=0,
            status="error",
            error=str(e),
        )    



async def get_table_from_sql_parallel(
    pool,
    sql_queries: List[str],
    max_concurrent: int = 5,
    row_limit: int | None = 500,
    query_timeout: int = 10,
):  
    start_time = time.time()
    semaphore = asyncio.Semaphore(max_concurrent)
    async def run_with_limit(query):
        async with semaphore:
            return await get_table_from_sql(
                pool, query, row_limit=row_limit, query_timeout=query_timeout
            )

    tasks = [asyncio.create_task(run_with_limit(query)) for query in sql_queries]
    results = await asyncio.gather(*tasks)
    process_time = (time.time()-start_time)*1000
    logger.info(f"Total parallel Query Execution took {process_time / 1000:.2f}s")
    return results


# # Alternative: Using context manager
# async def example_with_context_manager():
#     async with AioODBCPool(db_name="mydb", size=20) as pool:
#         conn = await pool.acquire()
#         try:
#             async with conn.cursor() as cursor:
#                 await cursor.execute("SELECT 1")
#                 result = await cursor.fetchone()
#                 print(result)
#         finally:
#             await pool.release(conn)
