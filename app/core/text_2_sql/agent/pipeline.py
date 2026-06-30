from typing import Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text_2_sql.agent.query_planner import QueryPlanner
from .query_resolver import QueryResolver
from .schema_retreiver import SchemaRetriever
from .nlu_extractor import NLUExtractorV2
from app.databases.vector.operations import VectorStore
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.client_sql.connections import BaseConnectionPool
from app.logger import get_logger
from app.api_models.chats import ConversationFilter
from .query_validator import UserQueryValidator
from .error_classes import QueryValidationError, SQLExecutionError, QueryResolutionError, SchemaRetrievalError, NLUExtractionError, QueryPlanningError
from app.core.helper import serialize_filters
from app.core.llm_connections.base import LLMBase, TokenUsage
# from app.core.llms import get_llm_response, TokenUsage, get_llm


logger = get_logger(__name__)


class Text2SQLAgentPipeline:
    def __init__(
        self,
        dbname: str,
        applciation_db_session: AsyncSession,
        vector_client: Any,
        nosql_helper: NOSQLHelper,
        client_pool: BaseConnectionPool,
        llm: LLMBase,
    ):
        self.dbname = dbname
        self.db_session = applciation_db_session
        self.vector_client = vector_client
        self.vector_store = VectorStore(vector_client)  # Initialize VectorStore
        self.nosql_helper = nosql_helper
        self.client_pool = client_pool
        self.llm = llm
        self.token_usage = TokenUsage()

        self.query_validator = UserQueryValidator(llm, self.vector_store)
        self.query_resolver = QueryResolver(dbname, applciation_db_session, llm)
        self.nlu_extractor = NLUExtractorV2(dbname, llm) # done
        self.schema_retriever = SchemaRetriever(dbname, self.vector_store)
        self.query_planner = QueryPlanner(self.dbname, self.llm)

        # storing all data and results
        self.transaction_data = {}
        self.results = {}

        logger.info(
            f"Text2SQLAgent initialized for database: {dbname}",
            extra={"event_type": "agent_initialized", "db_name": dbname}
        )


    async def run(self, user_query: str, filters: Optional[List[ConversationFilter]]) -> str:
        await self.vector_store.ensure_collection(self.dbname)
        
        filters = serialize_filters(filters) if filters else None
        
        self.transaction_data['user_query'] = user_query
        self.transaction_data['filters'] = filters
        
        try:
            validation_result = self.query_validator.run(user_query)
            self.results['query_validation'] = validation_result
            self.transaction_data['query_is_valid'] = validation_result["is_valid"]
            if not validation_result["is_valid"]:
                raise QueryValidationError(validation_result["reason"])
        except Exception as e:
            logger.error(
                "Error during query validation",
                extra={"event_type": "query_validation_error", "error": str(e)},
                exc_info=True,
            )
            raise QueryValidationError(f"Query validation failed: {str(e)}")
        

        try:
            resolved_query_results = await self.query_resolver.run(user_query, filters)
            resolved_query = resolved_query_results.resolved_query
            self.transaction_data['resolved_query'] = resolved_query
            self.token_usage += self.query_resolver.token_usage
            self.results['resolved_query'] = resolved_query_results
        except Exception as e:
            logger.error(
                "Error during query resolution",
                extra={"event_type": "query_resolution_error", "error": str(e)},
                exc_info=True,
            )
            raise QueryResolutionError(f"Query resolution failed: {str(e)}")


        try:
            nlu_result = await self.nlu_extractor.run(resolved_query, filters)
            self.token_usage += self.nlu_extractor.token_usage
            self.results['nlu_extraction'] = nlu_result
        except Exception as e:
            logger.error(
                "Error during NLU extraction",
                extra={"event_type": "nlu_extraction_error", "error": str(e)},
                exc_info=True,
            )
            raise NLUExtractionError(f"NLU extraction failed: {str(e)}")
        

        try:
            schema_retriever = SchemaRetriever(self.dbname, self.vector_store)
            schema_string, entity_string = await schema_retriever.build_schema(user_query, filters, nlu_result)
            self.results['schema_string'] = schema_string
            self.results['entity_string'] = entity_string
            logger.info(("Schema retrieved successfully"), extra={"event_type": "schema_retrieval_success", "schema_string_length": len(schema_string), "entity_string_length": len(entity_string)})
        except Exception as e:
            logger.error(
                "Error during schema building and entity mapping",
                extra={"event_type": "entity_mapping_error", "error": str(e)},
                exc_info=True,
            )
            raise SchemaRetrievalError(f"Entity mapping failed: {str(e)}")
        
        try:
            query_plan_results = await self.query_planner.run(resolved_query, filters, nlu_result, schema_string+"\n\n"+entity_string)
            self.results['query_plan'] = query_plan_results
            self.token_usage += self.query_planner.token_usage
        except Exception as e:
            logger.error(
                "Error during query planning",
                extra={"event_type": "query_planning_error", "error": str(e)},
                exc_info=True,
            )
            raise QueryPlanningError(f"Query planning failed: {str(e)}")

        
        # logger.info(
        #     "Running Text2SQLAgent pipeline",
        #     extra={"event_type": "agent_run_started", "user_query": user_query, "filters": str(filters)}
        # )

        # # Step 1: Generate SQL query using LLM
        # sql_query = await self.generate_sql_query(user_query, filters)
        # self.transaction_data['generated_sql'] = sql_query

        # # Step 2: Execute SQL query and get results
        # query_result = await self.execute_sql_query(sql_query)
        # self.transaction_data['query_result'] = query_result

        # # Step 3: Process results and generate final response
        # final_response = await self.generate_final_response(query_result)
        # self.transaction_data['final_response'] = final_response

        # logger.info(
        #     "Text2SQLAgent pipeline completed",
        #     extra={"event_type": "agent_run_completed", "transaction_data": str(self.transaction_data)}
        # )

        # return final_response
    
    