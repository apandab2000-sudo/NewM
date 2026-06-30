import uvicorn
from app.appConfig import settings
# from app.core.db.sql_schema import setup_internal_data

if __name__ == "__main__":
    # setup_internal_data()
    uvicorn.run(
        app=settings.app_startpoint,
        host=settings.app_host,
        port=settings.app_port,
        #port = 8017,
        reload=settings.app_debug,
        workers=settings.app_workers,
    )
