from pydantic import BaseModel, Field, field_serializer

class DBName(BaseModel):
    dbname: str = Field(..., description="Name ofgiven to the dataset in the application")

    @field_serializer("dbname")
    def validate_db_name(self, dbname: str) -> str:
        if not dbname or not dbname.strip():
            raise ValueError("db_name cannot be empty")
        return dbname.strip()
    
    @property
    def db_name(self) -> str:
        return self.dbname.strip()