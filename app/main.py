from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from app.logger import get_logger
from contextlib import asynccontextmanager
from app.appConfig import settings
from app.middlewares.logging import LoggingMiddleware
from app.routers import (
    metrics_router,
    health_router, 
    chats_router, 
    tables_router,
    graphs_router,
    suggestions_router,
    dashboards_router,
    insights_router,
    drilldown_router,
    feedback_router,
    conversation_router,
    setup_router,
    # whatif_router,
    # admin_dashboards_router,
    # report_builder_router,
    # report_builder_chat_router,
    db_connections_router,
    datasets_router,
    vectors_router,
    self_serve_router
)
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.core.prometheus_metrics import REQUEST_COUNT, REQUEST_LATENCY


from app.databases.dependencies import (
    application_pool_manager,
    application_nonsql_pool_manager,
    caching_pool_manager,
    vector_pool_manager,
    client_pool_manager
)


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    try:
        logger.info("Starting up Application")
        
        # Initialize pool managers
        application_pool_manager.start_cleanup_task()
        await application_nonsql_pool_manager.get_pool() # <--- ADDED THIS LINE
        application_nonsql_pool_manager.start_cleanup_task()
        caching_pool_manager.start_cleanup_task()
        vector_pool_manager.start_cleanup_task()
        client_pool_manager.start_cleanup_task()

        logger.info("All pool managers initialized")
        yield
        
    except Exception as e:
        logger.error(
            "Error during startup",
            extra={"event_type": "startup_error", "error": str(e)},
            exc_info=True,
        )
        raise
    
    finally:
        logger.info("Shutting down Application")
        
        try:
            # Graceful shutdown of all pool managers
            await application_pool_manager.shutdown()
            await application_nonsql_pool_manager.shutdown()
            await caching_pool_manager.shutdown()
            await vector_pool_manager.shutdown()
            await client_pool_manager.shutdown()
            
            logger.info("All pool managers shut down successfully")
        except Exception as e:
            logger.error(
                "Error during shutdown",
                extra={"event_type": "shutdown_error", "error": str(e)},
                exc_info=True,
            )

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=50_000)  # Compress responses > 50KB
app.add_middleware(LoggingMiddleware)  # Custom logging middleware

app.include_router(metrics_router)
app.include_router(health_router)
app.include_router(dashboards_router)
app.include_router(chats_router)
app.include_router(tables_router)
app.include_router(graphs_router)
app.include_router(drilldown_router)
app.include_router(suggestions_router)
app.include_router(insights_router)
app.include_router(feedback_router)
app.include_router(conversation_router)
app.include_router(setup_router)
# app.include_router(whatif_router)
# app.include_router(admin_dashboards_router)
# app.include_router(report_builder_router)
# app.include_router(report_builder_chat_router)
app.include_router(db_connections_router)
app.include_router(datasets_router)
app.include_router(vectors_router)
app.include_router(self_serve_router)
