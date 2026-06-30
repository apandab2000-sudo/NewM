from ..prompts import PromptGetter
from app.core.llms import get_llm_response, TokenUsage
from app.core.text_2_sql.agent.schema_retreivers.tables_retreiver import TableSchemaRetreiver
from app.core.text_2_sql.agent.schema_retreivers.entity_retreiver import EntityRetreiver
from app.databases.vector.operations import VectorStore
from app.logger import get_logger
from app.databases.caching.operations import get_cached_data, cache_data
from pathlib import Path
from typing import Optional
from app.core.text_2_sql.agent.nlu_extractor import NLUExtractor


logger = get_logger(__name__)


class GraphDrillDown:
    def __init__(
        self,
        dbname: str,
        llm,
        llm_name: str,
        initial_question: str,
        initial_sql: str, 
        filters: str,
        clicked_features: list,
        exploration_feature: str,
        vector_client: VectorStore
    ):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.initial_question = initial_question
        self.initial_sql = initial_sql
        self.clicked_features = clicked_features 
        self.token_usage: TokenUsage = TokenUsage()
        self.data_filters = filters
        self.exploration_feature = exploration_feature
        self.prompt_getter = PromptGetter(dbname)
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


    async def question_and_sql_query_generator(self):
        full_question = f"{self.initial_question} {self.clicked_features} {self.exploration_feature}"
        try:
            schema_str = await self.get_schema_string(full_question, self.data_filters)
        except Exception as e:
            logger.error(
                "Error during fetching schema string",
                extra={"event_type": "schema_string_error", "error": str(e)},
                exc_info=True,
            )
            raise Exception("Failed to fetch schema string for suggestions generation - " + str(e))

        drilldown_sys_prompt = self.prompt_getter.get_prompt("drilldown_sys_prompt")
        
        drilldown_sys_prompt = drilldown_sys_prompt.format(
            dialect="mssql",
            schema=schema_str
        )
        
        user_input = f"""primary_question: {self.initial_question}
        data_filters: {self.data_filters}
        primary_sql: {self.initial_sql}
        clicked_features: {self.clicked_features}
        exploration_feature: {self.exploration_feature}"""

        messages = [
            {"role": "system", "content": drilldown_sys_prompt},
            {"role": "user", "content": user_input}
        ]

        print("################ messages #################")
        print(messages)
        print("################ messages #################")

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        return results

    

         
