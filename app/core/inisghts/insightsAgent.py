from app.core.llms import get_llm_response, TokenUsage
from app.core.prompts import PromptGetter
from app.logger import get_logger
import pandas as pd
from pathlib import Path
from app.databases.caching.operations import get_cached_data
from app.databases.vector.operations import VectorStore
from app.core.text_2_sql.agent.schema_retreivers.tables_retreiver import TableSchemaRetreiver
from app.core.text_2_sql.agent.schema_retreivers.entity_retreiver import EntityRetreiver
from typing import Optional
from app.core.text_2_sql.agent.nlu_extractor import NLUExtractor


logger = get_logger(__name__)


class InsightsGenerator:
    def __init__(
            self,
            dbname: str,
            llm,
            llm_name: str,
            question: str,
            filters: str,
            sql_query: str,
            vector_client: VectorStore
        ):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.question = question
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
        self.data_filters = filters
        self.sql_query = sql_query
        self.vector_store = vector_client

        self.nlu_extractor = NLUExtractor(dbname, llm, llm_name)
        self.results = {}

        self.tables_retriever = TableSchemaRetreiver(dbname, self.vector_store)
        self.entity_retreiver = EntityRetreiver(dbname, self.vector_store)


    async def get_entites(self, user_query: str, filters: str, chat_history: Optional[list] = None):
        try:
            nlu_results = await self.nlu_extractor.run(user_query, filters, chat_history=chat_history)
            self.token_usage += self.nlu_extractor.token_usage
            self.results['nlu_extraction'] = nlu_results
            return nlu_results.model_dump()
        except Exception as e:
            logger.error(
                "Error during NLU extraction",
                extra={"event_type": "nlu_extraction_error", "error": str(e)},
                exc_info=True,
            )
            return {}


    async def get_schema_string(self, user_query: str, filters: str):
        # checking if schema string present as text file or yaml file in the schema_strings folder.
        default_schema_string_text_path= Path("app") / "core" / "schema_strings" / f"{self.dbname}.txt"
        if default_schema_string_text_path.exists():
            with open(default_schema_string_text_path, "r", encoding="UTF-8") as f:
                schema_string = f.read()
            logger.info("Reading the existing text schema string for db: %s", self.dbname)
            return schema_string
        
        default_schema_string_yaml_path= Path("app") / "core" / "schema_strings" / f"{self.dbname}.yaml"
        if default_schema_string_yaml_path.exists():
            with open(default_schema_string_yaml_path, "r", encoding="UTF-8") as f:
                schema_string = f.read()
            logger.info("Reading the existing yaml schema string for db: %s", self.dbname)
            return schema_string

        
        # if not found in files, then check in cache
        self.caching_key = f"{self.dbname}__{user_query}"
        schema_string = await get_cached_data(self.caching_key, self.dbname, "suggestions")

        if schema_string:
            return schema_string
        else:
            logger.debug("Schema string not found in cache")
        
        # building schema string from vector store using tables retriever and entity retriever
        try:
            logger.info("Building schema string from vector store for db: %s", self.dbname)
            entities = await self.get_entites(user_query, filters)
            tables_candidates = await self.tables_retriever.get_table_candidates(user_query, filters, entities)
            self.table_candidates = tables_candidates
            schema_string = self.tables_retriever.build_schema(tables_candidates)
            return schema_string
        except Exception as e:
            logger.error(
                "Error during fetching table metadata",
                extra={"event_type": "table_metadata_error", "error": str(e)},
                exc_info=True,
            )
            raise 

    async def extract_cols_and_descriptive_sqls(self):
        insights_sql_sys_prompt = self.prompt_getter.get_prompt("insights_sql_sys_prompt")

        try:
            schema_str = await self.get_schema_string(self.question, self.data_filters)
        except Exception as e:
            logger.error(
                "Error during fetching schema string",
                extra={"event_type": "schema_string_error", "error": str(e)},
                exc_info=True,
            )
            raise Exception("Failed to fetch schema string for insights generation - " + str(e))

        sys_prompt = insights_sql_sys_prompt.format(
            schema=schema_str,
            dialect='mssql',
            data_filters=self.data_filters
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Primary Question: {self.question}\nPrimary SQL: {self.sql_query}"}
        ]
        
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        print("=== LLM RAW OUTPUT FOR ADDITIONAL SQLS ===")
        print(results)
        return results


    async def generate_insights(self, primary_table: list, secondary_tables: list):
        primary_df = pd.DataFrame(primary_table)
        primary_df_json = primary_df.to_json(orient="records")
        primary_df_stats = primary_df.describe(include="all").to_json()

        secondary_data = []

        for i, st in enumerate(secondary_tables):
            if st:
                st_df = pd.DataFrame(st)
                st_json = st_df.to_json(orient="records")
                st_stats = st_df.describe(include="all")
                sd_data = f"""Secondary Table {i+1}
                {st_json}
                Secondary Table {i+1} - stats
                {st_stats}
                """
                secondary_data.append(sd_data)

        insights_generator_sys_prompt = self.prompt_getter.get_prompt("insights_generator_sys_prompt")

        base_user_message = f"""user_initial_input: {self.question}
        ============================
        primary_table\n{primary_df_json}
        stats:\n{primary_df_stats}
        ============================"""
        
        user_message = base_user_message+"============================\n".join(secondary_data)

        print("+++++++++++++++++")
        print(user_message)
        print("+++++++++++++++++")

        messages = [
            {"role": "system", "content": insights_generator_sys_prompt},
            {"role": "user", "content": user_message}
        ]

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        return results

