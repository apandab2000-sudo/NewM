# import os
# import logging
# from logging.handlers import RotatingFileHandler
# from app.appConfig import settings

# LOG_DIR = "logs"
# os.makedirs(LOG_DIR, exist_ok=True)
# LOG_FILE = os.path.join(LOG_DIR, "app.log")


# def get_logger(name: str = "app"):
#     logger = logging.getLogger(name)
#     if logger.hasHandlers():
#         return logger

#     logger.setLevel(settings.log_level.upper())

#     formatter = logging.Formatter(
#         "%(asctime)s | %(levelname)s | %(process)d | %(funcName)s | %(message)s"
#     )

#     if settings.log_to_file:
#         file_handler = RotatingFileHandler(
#             LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5
#         )
#         file_handler.setFormatter(formatter)
#         logger.addHandler(file_handler)

#     console_handler = logging.StreamHandler()
#     console_handler.setFormatter(formatter)
#     logger.addHandler(console_handler)

#     return logger

# import os
# import logging
# import json
# from logging.handlers import RotatingFileHandler
# from datetime import datetime
# from contextvars import ContextVar
# from typing import Any, Dict
# from app.appConfig import settings

# LOG_DIR = "logs"
# os.makedirs(LOG_DIR, exist_ok=True)
# LOG_FILE = os.path.join(LOG_DIR, "app.log")

# # Context variable to store request_id across async contexts
# request_id_ctx: ContextVar[str] = ContextVar("request_id", default=None)


# class JSONFormatter(logging.Formatter):
#     """Custom JSON formatter for structured logging"""
    
#     def format(self, record: logging.LogRecord) -> str:
#         log_data = {
#             "timestamp": datetime.utcnow().isoformat() + "Z",
#             "level": record.levelname,
#             "logger": record.name,
#             "message": record.getMessage(),
#             "module": record.module,
#             "function": record.funcName,
#             "line": record.lineno,
#             "process_id": record.process,
#             "thread_id": record.thread,
#         }
        
#         # Add request_id if available
#         request_id = request_id_ctx.get()
#         if request_id:
#             log_data["request_id"] = request_id
        
#         # Add exception info if present
#         if record.exc_info:
#             log_data["exception"] = self.formatException(record.exc_info)
        
#         # Add extra fields from the record
#         extra_fields = {
#             k: v for k, v in record.__dict__.items()
#             if k not in [
#                 "name", "msg", "args", "created", "filename", "funcName",
#                 "levelname", "levelno", "lineno", "module", "msecs",
#                 "message", "pathname", "process", "processName",
#                 "relativeCreated", "thread", "threadName", "exc_info",
#                 "exc_text", "stack_info", "taskName"
#             ]
#         }
        
#         if extra_fields:
#             log_data.update(extra_fields)
        
#         return json.dumps(log_data, default=str)


# def get_logger(name: str = "app") -> logging.Logger:
#     """Get or create a logger with JSON formatting"""
#     logger = logging.getLogger(name)
#     if logger.hasHandlers():
#         return logger

#     logger.setLevel(settings.log_level.upper())
#     logger.propagate = False  # Prevent duplicate logs

#     formatter = JSONFormatter()

#     if settings.log_to_file:
#         file_handler = RotatingFileHandler(
#             LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5
#         )
#         file_handler.setFormatter(formatter)
#         logger.addHandler(file_handler)

#     console_handler = logging.StreamHandler()
#     console_handler.setFormatter(formatter)
#     logger.addHandler(console_handler)

#     return logger


# def set_request_id(request_id: str) -> None:
#     """Set the request_id in the context"""
#     request_id_ctx.set(request_id)


# def get_request_id() -> str:
#     """Get the current request_id from context"""
#     return request_id_ctx.get()


import os
import logging
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from contextvars import ContextVar
from typing import Optional
from app.appConfig import settings


LOG_DIR = settings.log_file_path.rsplit("/", 1)[0]
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = settings.log_file_path


# Context variables for distributed tracing
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_ctx: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
        }
        
        # Add distributed tracing fields
        if request_id := request_id_ctx.get():
            log_data["request_id"] = request_id
        if trace_id := trace_id_ctx.get():
            log_data["trace_id"] = trace_id
        if span_id := span_id_ctx.get():
            log_data["span_id"] = span_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            log_data["exception_type"] = record.exc_info[0].__name__
        
        # Add extra fields from the record
        excluded_keys = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "message", "pathname", "process", "processName",
            "relativeCreated", "thread", "threadName", "exc_info",
            "exc_text", "stack_info", "taskName", "request_id", 
            "trace_id", "span_id"
        }
        
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in excluded_keys
        }
        
        if extra_fields:
            log_data.update(extra_fields)
        
        return json.dumps(log_data, default=str)


def get_logger(name: str = "app") -> logging.Logger:
    """Get or create a logger with JSON formatting"""
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel((settings.log_level or "debug").upper())
    logger.propagate = False

    formatter = JSONFormatter()

    if settings.log_to_file:
        file_handler = RotatingFileHandler(
            LOG_FILE, 
            maxBytes=settings.log_max_file_size, 
            backupCount=settings.log_backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def set_request_id(request_id: str) -> None:
    """Set the request_id in the context"""
    request_id_ctx.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request_id from context"""
    return request_id_ctx.get()


def set_trace_context(trace_id: str, span_id: str) -> None:
    """Set distributed tracing context for correlation"""
    trace_id_ctx.set(trace_id)
    span_id_ctx.set(span_id)


def log_with_context(logger: logging.Logger, level: str, message: str, **kwargs) -> None:
    """Helper to log with automatic context injection"""
    getattr(logger, level)(message, extra=kwargs)


def clear_context():
    request_id_ctx.set(None)
    trace_id_ctx.set(None)
    span_id_ctx.set(None)