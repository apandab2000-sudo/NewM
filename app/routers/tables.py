from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.background import BackgroundTasks
from app.core.text_2_sql.agent.pipeline import Text2SQLAgentPipeline
from app.models import GetTable
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
# from app.databases.internal_sql_operations import InternalSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
import yaml
from app.core.helper import (
    serialize_filters,
    log_sql_data,
    format_percentage_columns,
    format_percentage_response,
)
from app.core.llms import get_llm
# from app.core.text_2_sql.text2sql import Text2SQL
from app.core.text_2_sql.text_2_sql_updated import Text2SQL
from app.appConfig import settings
import json
from .base_check import perform_base_check
from app.databases.caching.operations import cache_data, get_cached_data
from app.databases.client_sql.operations import get_table_from_sql, get_table_and_status_and_columns, get_table_and_status_and_columns
from app.core.prometheus_metrics import TEXT2SQL_ERRORS, TEXT2SQL_HITS, TEXT2SQL_FIRST_SUCCESS, TEXT2SQL_SECOND_SUCCESS
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.application_sql.services.users import UsersHelper
from app.databases.application_sql.services.chats import ChatsHelper
from app.databases.dependencies import (
    get_db_async, 
    get_vector_client,
    get_nosql_client,
    get_pool,
)
from app.databases.vector.operations import VectorStore
from app.databases.application_nosql.operations import NOSQLHelper
from app.api_models.tables import TablesRequest, TablesResponse
from app.core.llm_connections.outputs import llm_factory
from app.core.text_2_sql.agent.fallback_handler.fallback_handler import FallbackHandler


router = APIRouter(prefix="/egai", tags=["Tables"])


logger = get_logger(__name__)


@router.post("/getTable", status_code=200)
async def get_table(
    data: GetTable,
    bg_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_db_async),
):
    i_data = InternalSQLHelper(db_session)
    TEXT2SQL_HITS.labels(data.dbname).inc()

    dataset_helper = DatasetHelper(db_session)

    db_details, connection_details = await dataset_helper.get_dataset_and_connection_details(db_name=data.dbname)
    if not db_details or not connection_details:
        raise HTTPException(status_code=404, detail="Dataset and DB CConnection not found") 
    
    client_pool = await get_pool(db_details, connection_details)

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)

    # vector_connection = vector_client.get_vector_db()
    # vector_db = VectorStore(vector_connection)
    await vector_db.ensure_collection(data.dbname)
    # nosql_client = get_nosql_client()
    
    nosql_client = await get_nosql_client()
    nosql_helper = NOSQLHelper()

    # Serielizing filters for caching
    filters_json = serialize_filters(data.filters)

    user_details, db_details, chat_details = await perform_base_check(
        i_data, 
        data.first_name,
        data.last_name,
        data.email_id,
        data.dbname,
        data.chat_id
    )

    cache_key_done: str = settings.caching_prefix+ f"table__{db_details.id}__{data.query}__{filters_json}"
    print(cache_key_done)

    cached_done = await get_cached_data(cache_key_done, data.dbname, endpoint="tables") # if cached sql query
    if cached_done:
        print("################# RETRIEVING CACHED SQL #######################")
        transaction_id = await log_sql_data(
            i_data, 
            query=data.query,
            db_id=db_details.id,
            chat_id=data.chat_id,
            sql_query=cached_done["sql_query"],
            filters_json=filters_json,
            approach=cached_done.get("apporach"),
            raw_response=cached_done,
            resolved_query=data.query
        ) 

        table_details = await get_table_from_sql(client_pool, data.dbname, cached_done["sql_query"])
        
        table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

        # considering only tables with more than 1 row are generated
        await nosql_helper.record_table(transaction_id, table_json, cached_done.get("approach"))
        caching_done = await cache_data(cache_key_done, cached_done, settings.sql_caching_ttl)

        if not caching_done:
            logger.warning("Not caahed properly")

        # Format percentage values only for the final API response.
        # Keep table_json numeric for persistence and internal processing.
        response_table = format_percentage_columns(table_json)

        return {
            "query_key": str(transaction_id),
            "sql": cached_done["sql_query"],
            "approach": cached_done.get("approach"),
            "table": response_table,
            "table_columns": table_columns,
            "sql_response": cached_done["sql_query"],
            "status": 200,
            "status_message": "Success",
            "multiple_response": False,
            "resolved_query": data.query
        }

    # IF NO CACHE RESPONSE AVAILABLE
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    last_transactions = await i_data.get_last_transaction_by_chat_id(data.chat_id, 3)

    print("########### LAST TRANSACTIONS ##############")
    print(last_transactions)
    print("########### LAST TRANSACTIONS ##############")

    t2s = Text2SQL(data.dbname, vector_db, llm, llm_name, data.query, filters_json)
    chat_history = t2s.get_chat_history(last_transactions) #type: ignore
    print("########### CHAT HISTORY ##############")
    print(chat_history)
    print("########### / CHAT HISTORY ##############")
    resp = await t2s.sql_query_generator(chat_history)
    resolved_query = t2s.results.get('resolved_query', data.query)
    
    if not resp: # Case where response generation resulted in error for any reason
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        print("############## NO RESPONSE GENERATED #################")
        transaction_id = await log_sql_data(
            i_data, 
            query=data.query,
            db_id=db_details.id,
            chat_id=data.chat_id,
            filters_json=filters_json,
            question_type="error",
            token_usage=t2s.token_usage.model_dump(),
            resolved_query=resolved_query
        ) 
        logger.error(f"NO RESPONSE GENERATED FOR query - {data.query}")
        raise HTTPException(detail="Could not able to generate the response", status_code=406)

    # Awaiting human input from LLM
    if resp.get("status") == "awaiting_human_input":
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        logger.info("Human input required")
        print("############## AWAITING HUMAN INPUT #################")
        transaction_id = await log_sql_data(
            i_data, 
            query=data.query,
            db_id=db_details.id,
            chat_id=data.chat_id,
            filters_json=filters_json,
            raw_response=resp,
            question_type="awaiting_human_input",
            token_usage=t2s.token_usage.model_dump(),
            resolved_query=resolved_query
        )
        text_response = resp["response"]
        return {
            "query_key": str(transaction_id),
            "sql": None,
            "approach": None,
            "table": [],
            "table_columns": {},
            "sql_response": text_response,
            "status": 406,
            "status_message": "awaiting_human_input",
            "multiple_response": False,
            "resolved_query": resolved_query
        }

    # Normal: SQL QUERY AND THE TABLE
    sql_query = resp["response"][0]["sql_query"]
    approach = resp["response"][0]["approach"]
    table_details = await get_table_from_sql(client_pool, data.dbname, sql_query)

    table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

    if not table_json and table_status == "success":
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        logger.info("SQL executed but no data found")
        print("############## SQL EXECUTED BUT NO DATA FOUND #############")

        fh = FallbackHandler(data.dbname, llm, llm_name, client_pool)
        try:
            text_response = await fh.run(
                user_query=resolved_query,
                filters="",
                sql_query=sql_query,
                dialect=connection_details.dialect
            )
            text_response = text_response.strip().replace("\n", " ").strip()
        except Exception as e:
            logger.error(f"Error in fallback handler: {e}")
            text_response = "No matching data found. Consider rephrasing the question or adjusting the filters."
        transaction_id = await log_sql_data(
            i_data, 
            query=data.query,
            db_id=db_details.id,
            chat_id=data.chat_id,
            sql_query=sql_query,
            filters_json=filters_json,
            raw_response=resp,
            approach=approach,
            question_type="awaiting_human_input",
            token_usage=t2s.token_usage.model_dump()
        )
        return {
            "query_key": str(transaction_id),
            "sql": sql_query,
            "approach": approach,
            "table": table_json,
            "table_columns": table_columns,
            "sql_response": text_response,
            "status": 406,
            "status_message": "awaiting_human_input",
            "multiple_response": False,
            "resolved_query": resolved_query
        }

    # Timeout: ask to limit rows
    if not table_json and table_status == "timeoutError":
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        logger.info("SQL has resulted in Timeout")
        print("############## SQL HAVE RESULTED IN TIMEOUT #############")
        text_response = "Would you like to narrow down your question (apply some filters). Current question is taking too long to find the relavant data."
        transaction_id = await log_sql_data(
            i_data, 
            query=data.query,
            db_id=db_details.id,
            chat_id=data.chat_id,
            sql_query=sql_query,
            filters_json=filters_json,
            raw_response=resp,
            approach=approach,
            question_type="awaiting_human_input",
            token_usage=t2s.token_usage.model_dump()
        )
        return {
            "query_key": str(transaction_id),
            "sql": sql_query,
            "approach": approach,
            "table": [],
            "table_columns": {},
            "sql_response": text_response,
            "status": 406,
            "status_message": "awaiting_human_input",
            "multiple_response": False,
            "resolved_query": resolved_query
        }

    second_success = False
    # Incorrect or runtime: one correction attempt
    if not table_json and table_status in {"programmingError", "error"}:
        logger.info(f"SQL has resulted in Error - {table_status}")
        print("############## SQL EXECUTION FAILED AND RESULTED IN ERROR #############")
        chat_history_new = [
            {"role": "user", "content": data.query},
            {"role": "assistant", "content": json.dumps(resp)},
            {"role":"user", "content": f"Error while running SQL: {table_details.error}. Please correct the SQL query."}
        ]

        resp = await t2s.correct_sql_query(chat_history_new)

        if not resp:
            TEXT2SQL_ERRORS.labels(data.dbname).inc()
            logger.info("Response not generated post SQL correction")
            text_response = "Error generating response"
            transaction_id = await log_sql_data(
                i_data, 
                query=data.query,
                db_id=db_details.id,
                chat_id=data.chat_id,
                filters_json=filters_json,
                question_type="error",
                token_usage=t2s.token_usage.model_dump(),
                resolved_query=resolved_query
            )
            raise HTTPException(detail="not able to generate a reponse for this question", status_code=404)
        
        if resp.get("status") == "awaiting_human_input":
            TEXT2SQL_ERRORS.labels(data.dbname).inc()
            logger.info("Human input required - POST SQL CORRECTION")
            print("############## AWAITING HUMAN INPUT #################")
            transaction_id = await log_sql_data(
                i_data, 
                query=data.query,
                db_id=db_details.id,
                chat_id=data.chat_id,
                filters_json=filters_json,
                raw_response=resp,
                question_type="awaiting_human_input",
                token_usage=t2s.token_usage.model_dump(),
                resolved_query=resolved_query
            )
            text_response = resp["response"]
            return {
                "query_key": str(transaction_id),
                "sql": None,
                "approach": None,
                "table": [],
                "table_columns": {},
                "sql_response": text_response,
                "status": 406,
                "status_message": "awaiting_human_input",
                "multiple_response": False,
                "resolved_query": resolved_query
            }
        
        sql_query = resp["response"][0]["sql_query"]
        approach = resp["response"][0]["approach"]
        table_details = await get_table_from_sql(client_pool, data.dbname, sql_query)

        table_json, table_status, table_columns = get_table_and_status_and_columns(table_details) 

        if not table_json:
            TEXT2SQL_ERRORS.labels(data.dbname).inc()
            logger.info("No Data found - AFTER QUERY CORRECTION")
            print("########## AFTER ERROR CORRECTONS AGAIN SQL WAS NOT CORRECT #############")
            
            if table_status=="success":
                text_response = "I am not able to find any relevant data for your query. Try rephrasing your question or changing the filters."
            else:
                text_response = "Not able to find right response. Try rephrasing your question"

            transaction_id = await log_sql_data(
                i_data, 
                query=data.query,
                db_id=db_details.id,
                chat_id=data.chat_id,
                sql_query=sql_query,
                approach=approach,
                filters_json=filters_json,
                raw_response=resp,
                question_type="error",
                token_usage=t2s.token_usage.model_dump(),
                resolved_query=resolved_query
            )
            return {
                "query_key": str(transaction_id),
                "sql": None,
                "approach": None,
                "table": [],
                "table_columns": {},
                "sql_response": text_response,
                "status": 406,
                "status_message": "awaiting_human_input",
                "multiple_response": False,
                "resolved_query": resolved_query
            }
        else:
            second_success=True

    # Success path
    print("########################## SUCCESS PATH ################################")
    if second_success:
        TEXT2SQL_SECOND_SUCCESS.labels(data.dbname).inc()
    else:
        TEXT2SQL_FIRST_SUCCESS.labels(data.dbname).inc()
    transaction_id = await log_sql_data(
        i_data, 
        query=data.query,
        db_id=db_details.id,
        chat_id=data.chat_id,
        sql_query=sql_query,
        approach=approach,
        filters_json=filters_json,
        raw_response=resp,
        question_type="complete",
        token_usage=t2s.token_usage.model_dump(),
        resolved_query=resolved_query
    )
    
    await nosql_helper.record_table(transaction_id, table_json, approach)

    # if table_json and sql_query:
    #     bg_tasks.add_task(
    #         cache_get_table,
    #         db_details.id,
    #         sql_query,
    #         approach,
    #         filters_json,
    #         last_transactions, #type: ignore
    #         data.query,
    #         resp
    #     )

    # Format percentage values only after the original numeric table has
    # been recorded. This prevents percentage strings from affecting
    # calculations, sorting, caching, graph generation, or persistence.
    response_table = format_percentage_columns(table_json)

    return {
        "query_key": str(transaction_id),
        "sql": sql_query,
        "table_columns": table_columns,
        "table": response_table,
        "sql_response": sql_query,
        "approach": approach,
        "status": 200,
        "status_message": "Success",
        "multiple_response": False,
        "resolved_query": resolved_query
    }


async def cache_get_table(
    db_id: int,
    sql_query: str,
    approach: str,
    filters_json: str,
    last_transactions: list,
    query: str,
    raw_response: dict
):
    try:
        cache_key_done = None
        
        if not last_transactions:  
            print("######## NO LAST TRANSACTIONS ###########")
            cache_key_done = settings.caching_prefix + f"table__{str(db_id)}__{query}__{filters_json}"
            print(cache_key_done)

        if last_transactions:
            if len(last_transactions) == 1:
                print("######## 1 LAST TRANSACTION ###########")

                if last_transactions[-1].question_type == "awaiting_human_input":
                    print("######## CACHING FOR - 1 LAST TRANSACTION - AWI ###########")
                    cache_key_done = settings.caching_prefix+f"table__{str(db_id)}__{last_transactions[-1].user_query}__{filters_json}"
                    
                if last_transactions[-1].question_type in ("complete", "error"):
                    print("######## CACHING FOR - 1 LAST TRANSACTION - C or E ###########")
                    cache_key_done = settings.caching_prefix+ f"table__{str(db_id)}__{query}__{filters_json}"

            if len(last_transactions) == 2:
                print("######## 2 LAST TRANSACTIONS ###########")

                if last_transactions[-1].question_type == "awaiting_human_input" and last_transactions[-2].question_type == "awaiting_human_input":
                    print("######## CACHING FOR - 2 LAST TRANSACTIONs ###########")
                    cache_key_done = settings.caching_prefix+ f"table__{str(db_id)}__{last_transactions[-2].user_query}__{filters_json}"

                if last_transactions[-1].question_type == "awaiting_human_input" and last_transactions[-2].question_type in ("complete", "error"):
                    print("######## CACHING FOR - 2 LAST TRANSACTIONs ###########")
                    cache_key_done = settings.caching_prefix+ f"table__{str(db_id)}__{last_transactions[-1].user_query}__{filters_json}"

                if last_transactions[-1].question_type in ("complete", "error") and last_transactions[-2].question_type in ("complete", "error"):
                    print("######## CACHING FOR - 2 LAST TRANSACTIONs ###########")
                    cache_key_done = settings.caching_prefix+ f"table__{str(db_id)}__{query}__{filters_json}"
                    

        if cache_key_done:
            caching_status = await cache_data(
                cache_key_done,
                {"sql_query": sql_query, "approach": approach, "raw_response": raw_response},
                settings.sql_caching_ttl,
            )
            if not caching_status:
                logger.warning("SQL not cached properly")
        else:
            print("No cache key forund")
    
    except Exception as e:
        logger.error("Caching table sql failed")



@router.post(
    "/tables",
    summary="Fetch tables based on user query",
    description="This endpoint takes a user query and converts into SQL to fetch relevant tables from the database. It also handles caching of SQL queries and their results for faster retrieval in future queries.",
    response_description="The SQL query generated from the user's input and the tables fetched based on that SQL query.",
    responses={
        404: {"description": "Not Found - Dataset or Connection details not found"},
        406: {"description": "Not Acceptable - Unable to generate SQL query or fetch tables, awaiting human input"},
        200: {"description": "Success - SQL query generated and tables fetched successfully"}
    },
    status_code=200,
    # response_model=TablesResponse
)
async def get_table_from_query(
    payload: TablesRequest,
    dbname: str = Query(..., description="Name of the dataset to fetch tables from"),
    user_name: str = Query(..., description="Name of the user making the request"),
    db_session: AsyncSession = Depends(get_db_async),
):  
    
    user_name = user_name.split(" ")
    email_id = f"{user_name[0]}.{user_name[1]}@eclerx.com"

    chats_helper = ChatsHelper(db_session)
    chat, dataset, user, connection = await chats_helper.get_chat_details(
        payload.chat_id
    )
    
    if not chat or user.email_id != email_id:
        logger.error(f"Invalid chat_id or email_id provided in the request", extra={"event_type": "invalid_request", "chat_id": payload.chat_id, "email_id": email_id})
        raise HTTPException(status_code=400, detail="Invalid chat_id or email_id provided in the request")
    
    # initializing database connections and helpers
    client_pool = await get_pool(dataset, connection) # application sql database connection pool
    vector_client = await get_vector_client() # vector database client 
    nosql_client = await get_nosql_client() # application nosql database client
    nosql_helper = NOSQLHelper() # application nosql database helper

    # getting LLM
    ai_provider = dataset.ai_provider
    ai_model = dataset.ai_model_mappings.get("sql")
    llm = llm_factory.get_llm(provider=ai_provider, model=ai_model)

    text_2_sql_pipeline = Text2SQLAgentPipeline(
        dbname=dbname,
        applciation_db_session=db_session,
        vector_client=vector_client,
        nosql_helper=nosql_helper,
        client_pool=client_pool,
        llm=llm
    )

    await text_2_sql_pipeline.run(payload.user_query, payload.filters)
    
    # The pipeline may return nested table/result structures, so apply the
    # recursive formatter only when constructing the final API response.
    response_results = format_percentage_response(
        text_2_sql_pipeline.results
    )

    return {
        "results": response_results,
        "token_usage": text_2_sql_pipeline.token_usage
    }