import asyncio
import time
from typing import List, Literal, Optional

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.helper import make_json_safe
from app.core.prometheus_metrics import (
    QUERY_DURATION,
    QUERY_ERRORS,
    QUERY_SUCCESS,
    QUERY_TIMEOUTS,
    TOTAL_QUERY_HITS,
)
from app.logger import get_logger

from .connections import BaseConnectionPool


logger = get_logger(__name__)


class QueryResult(BaseModel):
    sql: str
    rows: List[tuple]
    columns: List[str]
    pool_wait_ms: float
    exec_ms: float
    total_ms: float
    row_count: int
    status: Literal[
        "success",
        "error",
        "timeoutError",
        "programmingError",
        "unexpectedError",
    ]
    error: Optional[str] = None


async def get_table_from_sql(
    pool: BaseConnectionPool,
    db_name: str,
    sql_query: str,
    row_limit: int | None = 500,
    query_timeout: int = 300,
) -> QueryResult:
    start_total = time.time()
    pool_wait_ms = 0.0
    exec_ms = 0.0

    TOTAL_QUERY_HITS.labels(db_name).inc()

    with QUERY_DURATION.labels(db_name).time():
        try:
            acquire_start = time.time()

            async with pool.get_session() as session:
                pool_wait_ms = (time.time() - acquire_start) * 1000
                exec_start = time.time()

                result = await asyncio.wait_for(
                    session.execute(text(sql_query)),
                    timeout=query_timeout,
                )

                if row_limit is not None:
                    rows = result.fetchmany(row_limit)
                else:
                    rows = result.fetchall()

                columns = list(result.keys())
                exec_ms = (time.time() - exec_start) * 1000
                total_ms = (time.time() - start_total) * 1000

                logger.info(
                    "SQL query completed",
                    extra={
                        "event_type": "sql_query_completed",
                        "db_name": db_name,
                        "row_count": len(rows),
                        "pool_wait_ms": round(pool_wait_ms, 2),
                        "execution_seconds": round(exec_ms / 1000, 2),
                        "total_seconds": round(total_ms / 1000, 2),
                    },
                )

                QUERY_SUCCESS.labels(db_name).inc()

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

        except asyncio.TimeoutError:
            total_ms = (time.time() - start_total) * 1000
            QUERY_TIMEOUTS.labels(db_name).inc()

            logger.error(
                "SQL query timed out",
                extra={
                    "event_type": "sql_query_timeout",
                    "db_name": db_name,
                    "query_timeout": query_timeout,
                    "total_seconds": round(total_ms / 1000, 2),
                    "sql": sql_query,
                },
            )

            return QueryResult(
                sql=sql_query,
                rows=[],
                columns=[],
                pool_wait_ms=pool_wait_ms,
                exec_ms=exec_ms,
                total_ms=total_ms,
                row_count=0,
                status="timeoutError",
                error=f"Query exceeded timeout of {query_timeout}s",
            )

        except SQLAlchemyError as exc:
            total_ms = (time.time() - start_total) * 1000
            QUERY_ERRORS.labels(db_name).inc()

            logger.error(
                "SQL query execution failed",
                extra={
                    "event_type": "sql_query_error",
                    "db_name": db_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "total_seconds": round(total_ms / 1000, 2),
                    "sql": sql_query,
                },
                exc_info=True,
            )

            return QueryResult(
                sql=sql_query,
                rows=[],
                columns=[],
                pool_wait_ms=pool_wait_ms,
                exec_ms=exec_ms,
                total_ms=total_ms,
                row_count=0,
                status="programmingError",
                error=str(exc),
            )

        except Exception as exc:
            total_ms = (time.time() - start_total) * 1000
            QUERY_ERRORS.labels(db_name).inc()

            logger.error(
                "Unexpected SQL query error",
                extra={
                    "event_type": "unexpected_query_error",
                    "db_name": db_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "total_seconds": round(total_ms / 1000, 2),
                    "sql": sql_query,
                },
                exc_info=True,
            )

            return QueryResult(
                sql=sql_query,
                rows=[],
                columns=[],
                pool_wait_ms=pool_wait_ms,
                exec_ms=exec_ms,
                total_ms=total_ms,
                row_count=0,
                status="unexpectedError",
                error=str(exc),
            )


async def get_table_from_sql_parallel(
    pool: BaseConnectionPool,
    db_name: str,
    sql_queries: list[str],
    max_concurrent: int = 3,
    row_limit: int | None = 500,
    query_timeout: int = 60,
) -> list[QueryResult]:
    start_time = time.time()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_query(index: int, query: str) -> QueryResult:
        query_start = time.time()

        async with semaphore:
            logger.info(
                "Starting dashboard SQL query",
                extra={
                    "event_type": "dashboard_query_started",
                    "query_index": index,
                    "query_timeout": query_timeout,
                    "sql_preview": query[:500],
                },
            )

            try:
                # Protect the complete query lifecycle, including execution,
                # row fetching, session cleanup, and result conversion.
                result = await asyncio.wait_for(
                    get_table_from_sql(
                        pool=pool,
                        db_name=db_name,
                        sql_query=query,
                        row_limit=row_limit,
                        query_timeout=query_timeout,
                    ),
                    timeout=query_timeout + 5,
                )

            except asyncio.TimeoutError:
                total_ms = (time.time() - query_start) * 1000
                QUERY_TIMEOUTS.labels(db_name).inc()

                logger.error(
                    "Dashboard SQL query timed out",
                    extra={
                        "event_type": "dashboard_query_timeout",
                        "query_index": index,
                        "query_timeout": query_timeout,
                        "total_seconds": round(total_ms / 1000, 2),
                        "sql": query,
                    },
                )

                return QueryResult(
                    sql=query,
                    rows=[],
                    columns=[],
                    pool_wait_ms=0.0,
                    exec_ms=total_ms,
                    total_ms=total_ms,
                    row_count=0,
                    status="timeoutError",
                    error=f"Query exceeded timeout of {query_timeout}s",
                )

            except asyncio.CancelledError:
                logger.warning(
                    "Dashboard SQL query was cancelled",
                    extra={
                        "event_type": "dashboard_query_cancelled",
                        "query_index": index,
                        "sql": query,
                    },
                )
                raise

            except Exception as exc:
                total_ms = (time.time() - query_start) * 1000
                QUERY_ERRORS.labels(db_name).inc()

                logger.error(
                    "Unhandled exception in dashboard SQL query",
                    extra={
                        "event_type": "dashboard_query_exception",
                        "query_index": index,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "total_seconds": round(total_ms / 1000, 2),
                        "sql": query,
                    },
                    exc_info=True,
                )

                return QueryResult(
                    sql=query,
                    rows=[],
                    columns=[],
                    pool_wait_ms=0.0,
                    exec_ms=total_ms,
                    total_ms=total_ms,
                    row_count=0,
                    status="unexpectedError",
                    error=str(exc),
                )

            if result.status == "success":
                logger.info(
                    "Dashboard SQL query succeeded",
                    extra={
                        "event_type": "dashboard_query_succeeded",
                        "query_index": index,
                        "row_count": result.row_count,
                        "total_seconds": round(result.total_ms / 1000, 2),
                    },
                )
            else:
                logger.error(
                    "Dashboard SQL query failed",
                    extra={
                        "event_type": "dashboard_query_failed",
                        "query_index": index,
                        "status": result.status,
                        "error": result.error,
                        "total_seconds": round(result.total_ms / 1000, 2),
                        "sql": query,
                    },
                )

            return result

    tasks = [
        asyncio.create_task(run_query(index, query))
        for index, query in enumerate(sql_queries)
    ]

    gathered_results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    results: list[QueryResult] = []

    for index, result in enumerate(gathered_results):
        if isinstance(result, BaseException):
            logger.error(
                "Unhandled exception in parallel SQL query",
                extra={
                    "event_type": "parallel_query_exception",
                    "query_index": index,
                    "error_type": type(result).__name__,
                    "error": str(result),
                    "sql": sql_queries[index],
                },
            )

            results.append(
                QueryResult(
                    sql=sql_queries[index],
                    rows=[],
                    columns=[],
                    pool_wait_ms=0.0,
                    exec_ms=0.0,
                    total_ms=0.0,
                    row_count=0,
                    status="unexpectedError",
                    error=str(result),
                )
            )
        else:
            results.append(result)

    process_time = (time.time() - start_time) * 1000
    success_count = sum(result.status == "success" for result in results)
    timeout_count = sum(result.status == "timeoutError" for result in results)
    failure_count = (
        len(results)
        - success_count
        - timeout_count
    )

    logger.info(
        "Parallel SQL execution completed",
        extra={
            "event_type": "parallel_query_execution_completed",
            "query_count": len(sql_queries),
            "success_count": success_count,
            "failure_count": failure_count,
            "timeout_count": timeout_count,
            "process_seconds": round(process_time / 1000, 2),
        },
    )

    return results


def get_table_and_status_and_columns(table_details: QueryResult):
    table_status = table_details.status

    if table_details.columns and table_details.rows:
        table_columns = {
            f"column_{index}": column
            for index, column in enumerate(table_details.columns)
        }
        df = pd.DataFrame(
            table_details.rows,
            columns=table_details.columns,
        )
    else:
        table_columns = {}
        df = pd.DataFrame()

    table_json = df.to_dict(orient="records")
    table_json = make_json_safe(table_json)

    if table_json:
        is_entirely_null = (
            pd.DataFrame(table_json)
            .isnull()
            .all()
            .all()
        )
        if is_entirely_null:
            table_json = []

    return table_json, table_status, table_columns
