from pydantic import BaseModel
from typing import List, Optional, Dict

class ConfigureTableColumnMetadataRequest(BaseModel):
    table_list: List[str]

class DistributionMappingRequest(BaseModel):
    value: str
    pct: str | float | int

class UniqueValuesRequest(BaseModel):
    value: str

class MetadatataTableUpdateRequest(BaseModel):
    table_name: str
    name: str
    type: str
    is_primary_key: bool = False
    foreign_key: dict = {}
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    unique_values: Optional[List[UniqueValuesRequest]] = None
    num_unique_values: Optional[int] = None
    distribution_mappings: Optional[List[DistributionMappingRequest]] = None
    description: Optional[str] = None
    synonyms: Optional[List[str]] = None


class TableRelationships(BaseModel):
    parent_table: str
    parent_column: str
    referenced_table: str
    referenced_column: str

class MetadataTableResponse(BaseModel):
    name: str
    description: Optional[str] = None
    columns: Optional[List[str]] = None
    relationships: Optional[List[TableRelationships]] = None

