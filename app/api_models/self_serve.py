from pydantic import BaseModel, Field, field_validator, model_serializer, model_validator
from typing import Literal, Optional
from .users import UserName
from .datasets import DBName


class SQLConnectionDetails(BaseModel):
    UID: str = Field(..., description="Username for the SQL database")
    PWD: str = Field(..., description="Password for the SQL database")
    SERVER: str = Field(..., description="Host address of the SQL database")
    PORT: int = Field(..., description="Port number for the SQL database")
    DATABASE: str = Field(..., description="Database name in the SQL server")
    DRIVER: Optional[str] = Field(None, description="ODBC driver for SQL Server (required if dialect is 'mssql')")
    dialect: Optional[Literal["mssql", "pgsql", "mysql", "clickhouse"]] = "mssql"
    name: Optional[str] = Field(None, description="Optional name for the connection")
    description: Optional[str] = None
    

    @model_serializer()
    def create_name_if_none(self):
        if self.name is None:
            self.name = f"{self.UID}__{self.DATABASE}"
        return self
    
    @property
    def username(self) -> str:
        """Return the username for the SQL connection."""
        return self.UID
    
    @property
    def password(self) -> str:
        """Return the password for the SQL connection."""
        return self.PWD
    
    @property
    def host(self) -> str:
        """Return the host address for the SQL connection."""
        return self.SERVER
    
    @property
    def port(self) -> int:
        """Return the port number for the SQL connection."""
        return self.PORT
    
    @property
    def db(self) -> str:
        """Return the database name for the SQL connection."""
        return self.DATABASE
    
    @property
    def driver(self) -> str:
        """Return the appropriate driver based on the SQL dialect."""
        if self.DRIVER:
            return self.DRIVER
        if self.dialect == "mssql":
            return "ODBC Driver 17 for SQL Server"        


class AiModelMappings(BaseModel):
    sql: str
    suggestions: str
    insights: str
    graph: str


class BaseDatabaseSetupRequest(UserName, DBName):
    ai_provider: Optional[Literal["azure", "openai", "anthropic"]] = Field("openai", description="AI provider to use for this dataset")
    ai_model_mappings: Optional[AiModelMappings] = Field(None, description="Optional mapping of AI tasks to specific models for this dataset")
    graph_type: Optional[Literal["plotlycharts", "echarts"]] = Field(default="plotlycharts", description="Type of graph to use for visualizations in the application")
    db_schema: Optional[str] = Field(None, description="Database schema to use for this dataset. If not provided, defaults to 'dbo' for MSSQL and 'public' for PostgreSQL")
    
    @property
    def email_id(self) -> str:
        """Derive email ID from the user name."""
        if "@" in self.user_name:
            return self.user_name
        else:
            return self.user_name.replace(" ", ".").lower() + "@eclerx.com"
        

class SqlDatabaseSetupRequest(BaseDatabaseSetupRequest):
    database_details: SQLConnectionDetails = Field(..., description="Connection details for the SQL database")

    @model_validator(mode="after")
    def set_defaults(self):
        if self.ai_provider == "openai" and self.ai_model_mappings is None:
            self.ai_model_mappings = AiModelMappings(
                sql="gpt-4.1",
                suggestions="gpt-4.1",
                insights="gpt-4.1",
                graph="gpt-4.1",
            )

        if not self.db_schema:
            if self.database_details.dialect == "mssql":
                self.db_schema = "dbo"
            elif self.database_details.dialect == "pgsql":
                self.db_schema = "public"

        return self


class FlatFileDatabaseSetupRequest(BaseDatabaseSetupRequest):
    mode: Literal["new", "append", "replace"] = Field("new", description="Mode of dataset creation. 'new' will create a new dataset, while 'append' will add to an existing dataset with the same name.")
    is_continued: Optional[bool] = Field(False, description="Files are too large and cannot fit in single file. If True, it indicates that the file upload is being done in multiple parts and the system should wait for all parts to be uploaded before processing.")


class TablesToUseUpdate(UserName, DBName):
    tables_in_use: list[str] = Field(..., description="List of tables to use for the dataset. This will update the clientConfig.yaml file with the provided list of tables for the specified dataset.")
    replace_existing: bool = Field(False, description="Whether to replace the existing list of tables in the clientConfig.yaml file for the specified dataset. If False, the provided list of tables will be appended to the existing list.")