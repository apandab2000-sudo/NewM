from pathlib import Path
import json
from app.logger import get_logger
import yaml
from typing import List, Dict, Any


logger = get_logger(__name__)


def remove_null_objs(obj: dict | list):
    """Recursively remove keys with null values from a dictionary or list.
        also remove row where is_primary_key == False
    Args:
        obj: The input dictionary or list to clean.
    Returns:
        A new dictionary or list with all null values removed.
    """

    if isinstance(obj, dict):
        return {k: remove_null_objs(v) for k, v in obj.items() if v is not None and not (k == "is_primary_key" and v == False)}
    elif isinstance(obj, list):
        return [remove_null_objs(item) for item in obj if item is not None]
    else:
        return obj


class SchemaGenerationHelper:
    def __init__(self, dbname: str):
        self.dbname = dbname
        self.schema_base_path = Path("app") / "core" / "schema_strings" / f"{dbname}.yaml"

        self.columns_metadata_path = Path(f"business_data/{dbname}/columns")
        self.tables_metadata_path = Path(f"business_data/{dbname}/tables/tables.json")

    def setup_schema_string(self, replace_existing: bool = False):
        """Generates and saves the schema string for the given database.
    
        The schema string is generated based on the tables and columns metadata 
        for the specified database. The generated string is saved to a file for 
        later use in LLM prompts or other operations that require an understanding 
        of the database schema.

        If the schema string file already exists and replace_existing is set to False, 
        the function will skip generation to avoid overwriting existing data.
        """    

        if self.schema_base_path.exists() and not replace_existing:
            return

        with open(self.tables_metadata_path, "r") as f:
            tables_metadata = json.load(f)

        tables_info = []

        print(len(tables_metadata))

        for table in tables_metadata:

            ti = {
                "Table": table.get("name").upper(),
                "Description": table.get("description"),
            }

            print("#"*20)
            print("table_info", len(ti))
            print("#"*20)

            try:
                with open(self.columns_metadata_path / f"{table.get('name')}.json", "r") as f:
                    columns_metadata = json.load(f)
            except FileNotFoundError:
                logger.error(f"Columns metadata file not found for table: {table.get('name')}")
                raise

            cols_info = []

            for col in columns_metadata:

                sample_values = [i["value"] for i in col.get("unique_values", [])][:5] if col.get("unique_values") else None
                if not sample_values:
                    if col.get("min_value") is not None and col.get("max_value") is not None:
                        sample_values = [col.get("min_value"), col.get("max_value")]

                cols_info.append({
                    "name": col.get("name").upper(),
                    "type": col.get("type"),
                    "synonyms": col.get("synonyms") if col.get("synonyms") else None,
                    "description": col.get("description") if col.get("description") else None,
                    "is_primary_key": col.get("is_primary_key") if col.get("is_primary_key") is not None else None,
                    "sample_values": sample_values 
                })

            print("#"*20)
            print("col_info", len(cols_info))
            print("#"*20)

            ti["Columns"] = cols_info
            ti["Relationships"] = table.get("relationships") if table.get("relationships") else None

            tables_info.append(ti)
        
        with open(self.schema_base_path, "w") as f:
            yaml.safe_dump(remove_null_objs(tables_info), f, sort_keys=False, default_flow_style=False, indent=4)