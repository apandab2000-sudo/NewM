from pathlib import Path
import json
from app.logger import get_logger


logger = get_logger(__name__)


class IntroductionHelper:

    INTRO_BASE_PATH = Path("business_data") 

    def __init__(self, dbname: str):
        self.dbname = dbname
        self.intro_path_path = self.INTRO_BASE_PATH / f"{dbname}" / "introduction_meta.json"
        self.columns_metadata_path = self.INTRO_BASE_PATH / f"{dbname}" / "columns" 
        self.tables_metadata_path = self.INTRO_BASE_PATH / f"{dbname}" / "tables/tables.json"

    
    def write_introduction_metadata(self, introduction_data: list[dict]):
        output_path = self.INTRO_BASE_PATH / self.dbname / "introduction_meta.json"
        with open(output_path, "w") as f:
            json.dump(introduction_data, f, indent=4)

    
    def get_columns_metadata(self):
        columns_metadata = []

        for files in self.columns_metadata_path.glob("*.json"):
            with open(files, "r") as f:
                file_metadata = json.load(f)
            
            columns_metadata.append({
                "table_name": files.stem,
                "columns": [{
                    "column_name": col.get("name"),
                    "description": col.get("description"),
                    "numeric_stats": {"min": col.get("min_value"), "max": col.get("max_value")} if col.get("min_value") else None,
                    "categorical_stats": {i["value"]: i["pct"] for i in col.get("distribution_mappings", [])} if col.get("distribution_mappings") else None,
                    "unique_external_ref": {"unique_values": col.get("num_unique_values")} if col.get("num_unique_values") else None,
                    "comment_stats": None
                }
                for col in file_metadata]
            })
        return columns_metadata
    
    def get_tables_metadata(self):
        tables_metadata = []

        with open(self.tables_metadata_path, "r") as f:
            file_metadata = json.load(f)

        for i, table in enumerate(file_metadata):
            tables_metadata.append({
                "row_num": i+3,
                "columns":[
                    {
                        "query_key":"",
                        "type": "table",
                        "space_occupy":12,
                        "height":300,
                        "text_data":f"<b>About this table:</b> {table.get('description')}" if table.get('description') else "",
                        "plotlycharts":"",
                        "insight":"",
                        "header":table.get("name").replace("_", " ").replace("dbo.", ""),
                        "table_name": table.get("name"),
                        "about_this_data":f"<b>About this table:</b> {table.get('description')}" if table.get('description') else "",
                        "metadata":[
                            {"relationships": table.get("relationships")} ,
                        ] if table.get("relationships") else [],
                        "table":[]
                    }
                ]
            })
        
        return tables_metadata
    
          
    def setup_introduction(self, replace_existing: bool = False):
        if self.intro_path_path.exists():
            if not replace_existing:
                return
            
        try:
            columns_metadata = self.get_columns_metadata()
        except Exception as e:
            logger.error(f"Error fetching columns metadata: {str(e)}", exc_info=True)
            raise
        
        try:
            tables_metadata = self.get_tables_metadata()
        except Exception as e:
            logger.error(f"Error fetching tables metadata: {str(e)}", exc_info=True)
            raise
            
        introduction_data = {
            "output": tables_metadata,
            "columns_metadata": columns_metadata
        }

        self.write_introduction_metadata(introduction_data)