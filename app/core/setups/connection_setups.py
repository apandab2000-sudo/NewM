from urllib.parse import quote 
from sqlalchemy import create_engine, inspect
from functools import cached_property
import os

class ClientConnection:
    def __init__(self, USERNAME: str, PASSWORD: str, HOST: str, PORT: str, DATABASE: str, DIALECT: str = "mssql", DRIVER = None):
        self.UID = USERNAME
        self.PWD = PASSWORD
        self.SERVER = HOST
        self.PORT = PORT
        self.DATABASE = DATABASE
        self.DIALECT = DIALECT.lower()
        self.engine = self._create_engine()

    def _default_driver(self):
        return {
            "mssql": "ODBC+Driver+17+for+SQL+Server",  # for pyodbc
            "mysql": "pymysql",
            "pgsql": "psycopg2",
            "clickhouse": None  # if using sqlalchemy-clickhouse
        }.get(self.DIALECT)

    def _create_engine(self):
        driver = self._default_driver()
        if self.DIALECT == "mssql":
            driver_str = f"driver={driver}"
            url =  f'mssql+pyodbc://{self.UID}:{quote(self.PWD)}@{self.SERVER}:{self.PORT}/{self.DATABASE}?'+f'{driver_str}'
        else:
            driver_part = f"+{driver}" if driver else ""
            url = (
                f"{self.DIALECT}{driver_part}://{self.UID}:{quote(self.PWD)}@"
                f"{self.SERVER}:{self.PORT}/{self.DATABASE}"
            )
        return create_engine(url, future=True)

    def check_connectivity(self) -> bool:
        try:
            with self.engine.connect() as conn:
                return True
        except Exception as e:
            print(f"[Connection Error] {e!r}")
            return False

    @cached_property
    def inspector(self):
        return inspect(self.engine)

    def get_available_tables(self) -> list:
        return self.inspector.get_table_names()

    def get_table_info(self, table: str) -> list:
        return [
            {"col_name": col["name"], "data_type": str(col["type"])}
            for col in self.inspector.get_columns(table)
        ]

    def get_primary_key_constraints(self, table: str) -> list:
        return self.inspector.get_pk_constraint(table).get("constrained_columns", [])

    def get_foreign_key_constraints(self, table: str) -> list:
        fks = self.inspector.get_foreign_keys(table)
        return [col for fk in fks for col in fk.get("constrained_columns", [])]

    def get_relationships(self, table: str) -> list:
        relationships = []
        for fk in self.inspector.get_foreign_keys(table):
            print("##################### FK ############################")
            print(fk)
            print("##################### FK END ############################")
            for local_col, remote_col in zip(
                fk.get("constrained_columns", []),
                fk.get("referred_columns", [])
            ):
                relationships.append({
                    "from_table": table,
                    "to_table": fk.get("referred_table"),
                    "from_table_column": local_col,
                    "to_table_column": remote_col,
                })
        return relationships
    

class GenerateSchemaBase:
    def __init__(self, client: str, client_engine, relationships: list,
                 table_details: list):
        self.client = client
        self.engine = client_engine
        self.relationships = relationships
        self.table_details = table_details
        self.base_location = None

    def get_schema_str(self):
        schema = []
        for td in self.table_details:
            table_name = td.table
            col_definitions = []
            primary_keys = []
            for col in td.column_details:
                col_name = col.col_name
                data_type = str(col.data_type).replace('COLLATE "SQL_Latin1_General_CP1_CI_AS"', "").strip()
                alias = col.alias
                display_name = f"{col_name} {data_type}"+ (f" ALIAS {alias}" if alias else "")
                col_definitions.append(display_name + ",\n")
                if col.primary_key:
                    primary_keys.append(col_name)

            if len(primary_keys)>0:
                primary_keys_string = f"Primary Key: {table_name}(" + ", ".join(primary_keys)+")\n"
            else:
                primary_keys_string = "\n"

            table_relationships = [rel for rel in self.relationships if rel["from_table"]==table_name]

            rel_string_list = []
            if len(table_relationships)>0:
                for rel in table_relationships:
                    rel_string_list.append(f"{rel['from_table']}({rel['from_table_column']}) references {rel['to_table']}({rel['to_table_column']})")
            rel_string = "Foreign Key: " + ", ".join(rel_string_list) if len(rel_string_list)>0 else ""+"\n"

            col_definitions[-1] = col_definitions[-1].replace(",\n","")
            table_schema_string = f"Table {table_name}({''.join(col_definitions)})\n"
            table_schema_string+=primary_keys_string
            table_schema_string+=rel_string
            schema.append(table_schema_string.strip())

        schema_string = "\n\n".join(schema)
        schema_string_path = "schema_strings"
        os.makedirs(schema_string_path, exist_ok=True)
        with open(os.path.join(schema_string_path, f"{self.client}.txt"), "w", encoding="utf-8") as f:
            f.write(schema_string)
        return schema_string