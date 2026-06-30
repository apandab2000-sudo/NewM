from typing import List, Any, Optional
from .agent.schema_retreivers.entity_retreiver import EntityRetreiver
from .agent.nlu_extractor import NLUExtractor
from .agent.schema_retreivers.tables_retreiver import TableSchemaRetreiver
from .agent.query_resolver import QueryResolver
from app.core.llms import get_llm_response, TokenUsage
from app.logger import get_logger
from app.databases.vector.operations import VectorStore
from pathlib import Path
from app.core.helper import get_system_prompt
from app.databases.caching.operations import cache_data


logger = get_logger(__name__)




class Text2SQL:
    def __init__(
        self,
        dbname: str,
        vector_client: VectorStore,
        llm,
        llm_name: str,
        question: str,
        filters: str,
        relevant_questions: list = [],
    ):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.question = question
        self.vector_store = vector_client
        self.token_usage: TokenUsage = TokenUsage()
        self.last_relevant_questions = relevant_questions
        self.data_filters = filters
        self.sys_prompt: None | str = None
        self.table_candidates = None

        self.results = {}

        self.query_resolver = QueryResolver(dbname, llm, llm_name) 
        self.nlu_extractor = NLUExtractor(dbname, llm, llm_name)
        
        self.tables_retriever = TableSchemaRetreiver(dbname, self.vector_store)
        self.entity_retreiver = EntityRetreiver(dbname, self.vector_store)


    async def init_vectorsore(self):
        await self.vector_store.ensure_collection(self.dbname)


    async def get_positive_examples(self, user_query: str, num_examples: int = 5):   
        try:
            results = await self.vector_store._query_data(
                user_query=user_query,
                must_filters={"context_type": "sample_sql_query", "is_positive_example": True}, 
                n_results=num_examples
            )
        except Exception as e:
            logger.error(
                "Error during fetching positive examples",
                extra={"event_type": "positive_examples_error", "error": str(e)},
                exc_info=True,
            )
            results = []
        
        examples_list = []
        for res in results:
            user_input = res["payload"]["question"]
            sql = res["payload"]["sql_query"]
            ex = f"Question: {user_input}\nSQL: {sql}"
            examples_list.append(ex)
        return "\n\n".join(examples_list) if examples_list else "None"
    

    async def get_schema_string(self, user_query: str, filters: str, entities: dict):
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
        
        logger.info("Building schema from vector store for db: %s", self.dbname)

        try:
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
        
    
    async def get_value_hints(self, entities: dict):
        
        tables_to_use = [t.table_name for t in self.table_candidates] if self.table_candidates else None
        
        if not tables_to_use:
            return "None"
        
        try:
            value_hints = await self.entity_retreiver.get_entities(tables_to_use, entities)
            value_hint_string = self.entity_retreiver.get_entity_hint_string(value_hints)
            return value_hint_string
        except Exception as e:
            logger.error(
                "Error during fetching value hints",
                extra={"event_type": "value_hints_error", "error": str(e)},
                exc_info=True,
            )
            return "None"


    def get_chat_history(self, last_transactions: List[Any]) -> list:
        if len(last_transactions) == 0:
            return []
        chat_history_list = []
        for lt in last_transactions:
            chat_history_list.extend([
                {
                    "role": "user",
                    "content": lt.user_query
                },
                {
                    "role": "assistant",
                    "content": lt.raw_response
                }
            ])
        return chat_history_list
    

    async def get_resolved_query(self, user_query: str, filters: str, chat_history: list = [], num_history: int = 2):
        try:
            resolved_query_results = await self.query_resolver.run(user_query, filters, chat_history=chat_history, num_history=num_history)
            resolved_query = resolved_query_results.resolved_query
            self.results['resolved_query'] = resolved_query
            return resolved_query
        except Exception as e:
            logger.error(
                "Error during query resolution",
                extra={"event_type": "query_resolution_error", "error": str(e)},
                exc_info=True,
            )
            self.results['resolved_query'] = user_query
            return user_query
    
    
    async def sql_query_generator(self, chat_history: list, dialect: str = "mssql"):
        resolved_query = await self.get_resolved_query(self.question, self.data_filters, chat_history=chat_history) # optional
        positive_examples = await self.get_positive_examples(resolved_query, 5) # optional
        entities = await self.get_entites(resolved_query, self.data_filters, chat_history) # optional
        schema_string = await self.get_schema_string(resolved_query, self.data_filters, entities)  # mandatory      
        value_hints = await self.get_value_hints(entities) # optional

        caching_key = f"{self.dbname}__{resolved_query}"
        await cache_data(caching_key, schema_string, 300)

        text2sql_sys_prompt = get_system_prompt(self.dbname, "text2sql_sys_prompt")
        
        self.sys_prompt = text2sql_sys_prompt.format(
            dialect=dialect,
            schema= schema_string,
            matched_values=value_hints,
            examples=positive_examples,
            data_filters=self.data_filters
        )
        
        messages = [{"role": "system", "content": self.sys_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": resolved_query})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage += token_usage
        print("results.........", results)

        print("############ SYSTEM PROMPT ################")
        print('sys prompt........', self.sys_prompt)

        return results

    async def correct_sql_query(self, chat_history: list):
        logger.warning("Initial SQL resulted din error. Regenerating SQL")
        messages = [{"role": "system", "content": self.sys_prompt}]
        messages.extend(chat_history)
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage += token_usage 
        return results
    

        
