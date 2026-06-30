from pathlib import Path
import yaml
from app.logger import get_logger
from datetime import datetime, date


logger = get_logger(__name__)


class ConfigGenerationHelper:
    def __init__(self, dbname: str):
        self.dbname = dbname
        self.config_base_path = Path("app/clientConfig.yaml")

    def setup_client_config(self, available_tables: list[str], replace_existing: bool = False):
        """Generates and saves the client configuration for the given database.
    
        The client configuration is generated based on the database name and saved 
        to a YAML file. This configuration can be used for setting up client-specific 
        settings or parameters that are required for connecting to or interacting with 
        the database.

        If the client configuration file already exists and replace_existing is set to False, 
        the function will skip generation to avoid overwriting existing data.
        """    

        with open(self.config_base_path, "r") as f:
            config_data = yaml.safe_load(f)

        if config_data.get(self.dbname) and not replace_existing:
            logger.info(f"Client configuration for database '{self.dbname}' already exists. Skipping generation.")
            return
        
        if not config_data.get(self.dbname):
            config_data[self.dbname] = {
                "AUTO_DASHBOARD": True,
                "DATABASE": {
                    "available_tables": available_tables
                },
                "GRAPH_TYPE": "plotlycharts",
                "LLM": {
                    "GRAPH": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "INSIGHTS": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "SQL": {"BASE": "gpt", "MODEL": "gpt-4.1"},
                    "SUGGESTIONS": {"BASE": "gpt", "MODEL": "gpt-4.1"}
                },
                "DATA_REFRESH": {
                    "FREQUENCY": "0 0 * * *",
                    "LAST_REFRESH_DATE": str(date.today())
                },
                "CONVERSATION_FILTERS": [],
                "PROMPT_SUGGESTIONS": []
            }
        else:
            if replace_existing:
                logger.info(f"Replacing existing client configuration for database '{self.dbname}'.")
                config_data[self.dbname]["DATABASE"]["available_tables"] = available_tables
                config_data[self.dbname]["DATA_REFRESH"]["LAST_REFRESH_DATE"] = str(date.today())
            else:
                logger.info(f"Client configuration for database '{self.dbname}' already exists. Updating available tables and last refresh date.")
                existing_tables = set(config_data[self.dbname]["DATABASE"].get("available_tables", []))
                updated_tables = list(existing_tables.union(set(available_tables)))
                config_data[self.dbname]["DATABASE"]["available_tables"] = updated_tables
                config_data[self.dbname]["DATA_REFRESH"]["LAST_REFRESH_DATE"] = str(date.today())
        
        with open(self.config_base_path, "w") as f:
            yaml.safe_dump(config_data, f)