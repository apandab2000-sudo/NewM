from pydantic import BaseModel, Field
from typing import List, Any, Optional
from .users import UserName
from .datasets import DBName

class ResetChat(UserName, DBName):
    pass


class ConversationFilter(BaseModel):
    alias: str = Field(..., description="alias for the column for display puposes")
    col_name: str = Field(..., description="actual column name in the database")
    selected_values: List[Any] = Field(default_factory=list, description="list of selected values for the filter")


class UpdateFiltersRequest(BaseModel):
    filters: Optional[List[ConversationFilter]] = Field(default_factory=list)


class ConversationFiltersAddons(ConversationFilter):
    possible_values: List[Any] = Field(default_factory=list, description="list of possible values for the filter")


class FiltersResponse(BaseModel):
    filters: List[ConversationFiltersAddons] = Field(default_factory=list, description="list of filters with possible values")
    