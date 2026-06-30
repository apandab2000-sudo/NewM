import time
import uuid
import os
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.prometheus_metrics import REQUEST_COUNT, REQUEST_LATENCY

from app.logger import (
    get_logger,
    set_request_id,
    set_trace_context,
    clear_context,
)

logger = get_logger(__name__)


NOT_LOGGED_PATHS = {"/docs", "/health", "/openapi.json", "/metrics", "/favicon.ico"}


def truncate_large_structures(obj, max_array_length=10, max_depth=5, depth=0):
    if depth > max_depth:
        return "...truncated..."

    if isinstance(obj, dict):
        return {k: truncate_large_structures(v, max_array_length, max_depth, depth + 1) for k, v in obj.items()}

    if isinstance(obj, list):
        if len(obj) > max_array_length:
            return obj[:max_array_length] + [f"... {len(obj) - max_array_length} more"]
        return [truncate_large_structures(i, max_array_length, max_depth, depth + 1) for i in obj]

    return obj


async def prepare_body_log(request: Request) -> dict | None:
    """Safely extract body for logging without consuming it"""
    content_type = request.headers.get("content-type", "")
    content_length = request.headers.get("content-length")

    if "application/json" not in content_type:
        return None

    try:
        if content_length and int(content_length) > 50_000:
            return {"_skipped": "body exceeds 50KB"}
        
        body = await request.body()
        if body:
            parsed = json.loads(body)
            return truncate_large_structures(parsed)
    except json.JSONDecodeError:
        return {"error": "invalid_json"}
    except Exception as e:
        return {"error": str(e)}

    return None

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # IDs
        request_id = str(uuid.uuid4())
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
        span_id = str(uuid.uuid4())

        set_request_id(request_id)
        set_trace_context(trace_id, span_id)

        path = request.url.path
        worker_pid = os.getpid()

        try:
            # Log request
            if path not in NOT_LOGGED_PATHS:
                body = await prepare_body_log(request)
                headers = dict(request.headers)
                for k in ["authorization", "cookie"]:
                    headers.pop(k, None)

                logger.info(
                    "Incoming request",
                    extra={
                        "event_type": "http_request",
                        "method": request.method,
                        "path": path,
                        "query_params": dict(request.query_params),
                        "headers": headers,
                        "body": body,
                        "worker_pid": worker_pid,
                        "client_ip": request.client.host if request.client else "unknown",
                    },
                )

            response = await call_next(request)
            process_time = round(time.time() - start_time, 5)

            # Log response
            if path not in NOT_LOGGED_PATHS:
                logger.info(
                    "Request completed",
                    extra={
                        "event_type": "http_response",
                        "method": request.method,
                        "path": path,
                        "status_code": response.status_code,
                        "process_time": process_time,
                        "worker_pid": worker_pid,
                    },
                )

            # Prometheus metrics
            REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
            REQUEST_LATENCY.labels(endpoint=request.url.path).observe(process_time)

            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id
            response.headers["X-Process-Time"] = str(process_time)

            return response

        except Exception as e:
            process_time = round(time.time() - start_time, 5)

            # Prometheus metrics
            REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=500).inc()
            REQUEST_LATENCY.labels(endpoint=request.url.path).observe(process_time)

            # Log exception with context
            logger.error(
                "Request failed with exception",
                extra={
                    "event_type": "http_error",
                    "method": request.method,
                    "path": path,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "process_time": process_time,
                    "worker_pid": worker_pid,
                    "client_ip": request.client.host if request.client else "unknown",
                },
                exc_info=True,
            )
            raise

        finally:
            clear_context()