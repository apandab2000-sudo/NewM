import yaml
from functools import lru_cache
from app.databases.client_sql.operations import get_table_from_sql
from app.databases.client_sql.connections import BaseConnectionPool
from app.logger import get_logger
from app.models import ConversationFilter
from typing import List, Optional
import json
import pandas as pd
import os


logger = get_logger(__name__)


@lru_cache(maxsize=10)
def load_config(dbname: str):
    file_path = f"business_data/{dbname}/introduction_meta.json"
    
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        introduction_meta = json.load(f)
    return introduction_meta



class IntroductionText:
    def __init__(self, dbname: str):
        self.dbname = dbname

    def get(self):
        introduction_meta = load_config(self.dbname)
        
        if not introduction_meta:
            return ""
        
        db_description = ""
        for row in introduction_meta.get("output", []):
            if row.get("row_num") == 1:
                columns = row.get("columns", [])
                if columns:
                    db_description = columns[0].get("text_data", "")
                break
        return db_description
