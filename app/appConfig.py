import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

load_dotenv()

class Settings(BaseSettings):
    # load_dotenv(".env.dev")

    openai_api_key: str

    # main_application
    app_name: str = "IOD Backend - ITG Build"
    app_debug: bool = False
    app_version: str = "4.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 5030
    app_startpoint: str = "app.main:app"
    app_workers: int = 1

    # logs
    log_level: str = "debug" if os.environ.get("APP_ENV", "dev") == "dev" else "info"
    log_to_file: bool = True
    log_file_path: str = "logs/app.log"
    log_max_file_size: int = 50 * 1024 * 1024 
    log_backup_count: int = 5

    # internal databases
    sql_host: str 
    sql_port: str 
    sql_username: str 
    sql_password: str 
    sql_database: str 
    sql_schema: str

    sql_pool_size: int = 5
    sql_pool_timeout: int = 30
    sql_max_overflow: int = 2
    sql_pool_recycle: int = 1800
    
    nosql_host: str
    nosql_port: str
    nosql_username: str
    nosql_password: str
    nosql_database: str
    nosql_collection: str
    
    vector_host: str
    vector_port: int 
    
    caching_host: str
    caching_port: int 
    caching_database: str

    # client database
    client_sql_host: str
    client_sql_port: str
    client_sql_username: str
    client_sql_password: str
    client_sql_database: str
    client_connection_pool_per_worker: int = 4

    base_caching_ttl: int = int(0.5 * 60 * 60)
    filters_caching_ttl: int = 24 * 60 * 60
    sql_caching_ttl: int = 24 * 60 * 60

    # Database Connection Pool Manager Stats
    max_pools:int = 5
    max_pool_idle_time: int = 3600 # if pool is inactive for 1 hour, it automcatically closes
    pool_cleanup_cycle_time: int = 1800 # every 20 mins appplication scans for idle pools and closes them
    
    # Database Connection Stats
    query_timeout_database_level: int = 30 # post this time connection will closed automatically
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800

    file_upload_path: str = "client_data"

    caching_prefix: str = os.environ.get("APP_ENV", "dev")+"__"

    model_config = SettingsConfigDict(
        env_file=(f'.env.{os.environ.get("APP_ENV", "dev")}'), 
        env_file_encoding='utf-8',
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings() #type: ignore

settings = get_settings()

