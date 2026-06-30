from fastapi import APIRouter, HTTPException, Depends
import yaml
import json
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import GetSuggestions, SuggestionAnalysis
from app.logger import get_logger
from app.databases.dependencies import (
    get_db_async,
    get_vector_client,
    get_nosql_client,
    get_pool,
)
from app.core.helper import (
    serialize_filters,
    get_drilldown_features,
    format_percentage_columns,
)
from app.core.llms import get_llm
from app.databases.application_nosql.models import Suggestion
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.vector.operations import VectorStore
from .base_check import perform_base_check
from app.core.suggestionsAgent import GenerateSuggestions
import pandas as pd
from app.core.graphs.plotly.base import generate_graphs
from app.databases.application_nosql.models import Plotly_Graph
import os
from app.databases.client_sql.operations import get_table_from_sql, get_table_and_status_and_columns, get_table_from_sql_parallel
from app.core.prometheus_metrics import TEXT2SQL_INVALID_HITS, TEXT2SQL_ERRORS, TEXT2SQL_HITS, TEXT2SQL_FIRST_SUCCESS, TEXT2SQL_SECOND_SUCCESS, GRAPHS_GENERATED_PER_QUESTION, GRAPHS_ERRORS, SUGGESTIONS_ERRORS, SUGGESTIONS_GENERATED_PER_QUESTION, SUGGESTIONS_HITS, GRAPH_HITS


router = APIRouter(prefix="/egai", tags=["Suggestions"])


logger = get_logger(__name__)


############# BELOW FUNCTION COPIES FNCTIONALITY FROM models.py under GetTable ##################
def correct_query(query: str):
    query_split = query.split(" ")
    query_split = [q.strip() for q in query_split if len(q.strip()) > 0]
    return " ".join(query_split)


@router.post('/getSuggestions', status_code=200)
async def get_suggestions(
    data: GetSuggestions,
    session: AsyncSession = Depends(get_db_async)
):
    SUGGESTIONS_HITS.labels(data.dbname).inc()
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    transaction_details = await i_data.get_transaction_details_from_id(data.transaction_id)
    if not transaction_details:
        raise HTTPException(detail="Transaction details not found", status_code=404)
    
    resolved_query = transaction_details.resolved_query if transaction_details.resolved_query else data.query

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)
    await vector_db.ensure_collection(data.dbname)

    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)
    # Database Connections
    # client_pool = client_connection_pool
    # i_data = InternalSQLHelper(session)
    # nosql_client = get_nosql_client()
    nosql_client = await get_nosql_client()
    nosql_helper = NOSQLHelper()

    _ = await perform_base_check(
        i_data, 
        data.first_name,
        data.last_name,
        data.email_id,
        data.dbname,
        data.chat_id
    )
    
    filters_json = serialize_filters(data.filters)

    transaction_details = await i_data.get_transaction_details_from_id(data.transaction_id)
    if not transaction_details:
        raise HTTPException(detail="Base question didn't ran successfully. No Transaction Details found", status_code=404)

    sql_details = await i_data.get_sql_details_from_id(transaction_details.sql_id)
    if not sql_details:
        raise HTTPException(detail="Base question didn't ran successfully. No Base SQL found", status_code=404)

    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    suggestions_generator = GenerateSuggestions(
        dbname=data.dbname,
        llm=llm, 
        llm_name=llm_name,
        question=resolved_query,
        filters=filters_json,
        sql_query=sql_details.sql_code,
        vector_client=vector_db
    )

    suggestions = await suggestions_generator.get_suggestions()
    await i_data.add_llm_usage(
        data.transaction_id, 
        "suggestions", 
        llm_name, 
        **suggestions_generator.token_usage.model_dump()
    )
    
    if not suggestions:
        SUGGESTIONS_ERRORS.labels(data.dbname).inc()
        logger.error("Suggestion not generated properly")
        raise HTTPException(detail="Suggestion not generated successfully", status_code=400)
    
    suggestions = suggestions["follow_ups"]

    sql_queries = [s["sql_query"] for s in suggestions]

    try:
        query_results = await asyncio.wait_for(
            get_table_from_sql_parallel(
                pool=client_pool,
                db_name=data.dbname,
                sql_queries=sql_queries,
                max_concurrent=3,
                row_limit=100,
                query_timeout=60,
            ),
            timeout=150,
        )
    except asyncio.TimeoutError:
        SUGGESTIONS_ERRORS.labels(data.dbname).inc()
        logger.error(
            "Complete suggestion SQL execution timed out",
            extra={
                "event_type": "suggestions_execution_timeout",
                "transaction_id": data.transaction_id,
                "query_count": len(sql_queries),
                "timeout_seconds": 150,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=504,
            detail="Suggestion queries exceeded the allowed execution time",
        )

    working_suggestions = []
    suggestion_question_list = []
    non_working_suggestions = []

    idx = 1
    for s, r in zip(suggestions, query_results):

        if r.status != "success":
            non_working_suggestions.append(
                json.dumps(
                    {
                        "question": s["question"],
                        "sql_query": s["sql_query"],
                        "status": r.status,
                        "error": r.error,
                    },
                    default=str,
                )
            )
            logger.warning(
                "Skipping unsuccessful suggestion query",
                extra={
                    "event_type": "suggestion_query_skipped",
                    "question": s["question"],
                    "query_status": r.status,
                    "error": r.error,
                },
            )
            continue

        table_json, table_status, _ = get_table_and_status_and_columns(r)

        if table_json and table_status == "success":
            user_query = correct_query(s["question"])
            sugg = Suggestion(
                suggestion_id=idx,
                user_query=user_query,
                sql_code=s["sql_query"],
                sql_table=table_json,  # type: ignore
                approach=f"<b>Business Rationale</b><br>{s.get('business_rationale')}<br><br><b>Solution Approach</b><br>{s.get('sql_technique')}",
                category=s["category"]
            )
            suggestion_question_list.append(user_query)
            working_suggestions.append(sugg)
            idx += 1
        else:
            non_working_suggestions.append(
                json.dumps(
                    {
                        "question": s["question"],
                        "sql_query": s["sql_query"],
                        "status": table_status,
                        "error": "Query returned no usable rows",
                    },
                    default=str,
                )
            )

    if non_working_suggestions:
        logger.warning(f"Non working Questions - {', '.join(non_working_suggestions)}")

    if not working_suggestions:
        SUGGESTIONS_ERRORS.labels(data.dbname).inc()
        logger.error("Suggestions not generated properly")
        raise HTTPException(detail="Not able to generate any successful suggestion", status_code=400)
    
    SUGGESTIONS_GENERATED_PER_QUESTION.labels(data.dbname).inc(len(suggestion_question_list))

    doc = await nosql_helper.record_suggestions(data.transaction_id, working_suggestions)
    if not doc:
        logger.error("Suggestions not stored properly")
        raise HTTPException(detail="Suggestions not stored properly", status_code=400)

    try:
        await suggestions_generator.cache_schema_string_for_working_suggestions(working_suggestions)
    except Exception as e:
        logger.error(
            "Error during caching schema string for working suggestions",
            extra={"event_type": "cache_schema_string_error", "error": str(e)},
            exc_info=True,
        )
    
    return {
        "status": 200,
        "status_message": "Success",
        "suggestions": suggestion_question_list
    }


@router.post('/getSuggestionAnalysis', status_code=200)
async def get_suggestion_analysis(
    data: SuggestionAnalysis,
    session: AsyncSession = Depends(get_db_async)
):
    # Database Connections
    # i_data = InternalSQLHelper(session)
    # nosql_client = get_nosql_client()
    nosql_client = await get_nosql_client()
    TEXT2SQL_HITS.labels(data.dbname).inc()
    GRAPH_HITS.labels(data.dbname).inc()

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)
    
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    nosql_helper = NOSQLHelper()

    #serielizing_filters for caching process
    filters_json = serialize_filters(data.filters)

    user_details, db_details, chat_details = await perform_base_check(
        i_data, 
        data.first_name,
        data.last_name,
        data.email_id,
        data.dbname,
        data.chat_id
    )

    transaction_details = await i_data.get_transaction_details_from_id(data.transaction_id)
    if not transaction_details:
        raise HTTPException(detail="Base question didn't ran successfully. No Transaction Details found", status_code=404)

    nosql_transaction_details = await nosql_helper.get_transaction(transaction_id=data.transaction_id)

    if not nosql_transaction_details:
        logger.error("Suggestion not found with provided Transaction ID")
        raise HTTPException(detail="Suggestion not found with provided Transaction ID", status_code=404)
    
    clicked_suggestion = [s for s in nosql_transaction_details.suggestions if s.user_query == data.query][0]

    query_details = await i_data.create_or_get_query(user_query=clicked_suggestion.user_query)
    if not query_details:
        raise HTTPException(detail="Query not saved properly", status_code=400)
    
    sql_details = await i_data.create_or_get_sql(sql_code=clicked_suggestion.sql_code)
    if not sql_details:
        raise HTTPException(detail="SQL not saved properly", status_code=400)
    
    new_transaction_details = await i_data.create_transaction(
        db_id=db_details.id,
        query_id=query_details.id,
        sql_id=sql_details.id,
        chat_id=data.chat_id,
        filters=filters_json,
        approach=clicked_suggestion.approach,
        question_type="complete",
        raw_response=json.dumps({"sql_query": clicked_suggestion.sql_code, "approach": clicked_suggestion.approach, "status": "complete"}),
        resolved_query=clicked_suggestion.user_query
    )
    
    await nosql_helper.record_table(
        new_transaction_details.id, #type: ignore
        clicked_suggestion.sql_table, 
        clicked_suggestion.approach
    )

    suggested_df = pd.DataFrame(clicked_suggestion.sql_table)

    with open("app/clientConfig.yaml", 'r') as f:
        config_dict = yaml.safe_load(f)

    llm_base = config_dict[data.dbname]["LLM"]["GRAPH"]["BASE"]
    llm_name = config_dict[data.dbname]["LLM"]["GRAPH"]["MODEL"]
    llm = await get_llm(base=llm_base)

    suggested_df_copy = suggested_df.copy()    

    TEXT2SQL_FIRST_SUCCESS.labels(data.dbname).inc()
    
    graphs_list, token_usage = await generate_graphs(
        user_query=data.query,
        df=suggested_df_copy, 
        db_name=data.dbname, 
        llm = llm, #type: ignore
        filters=filters_json,
        llm_model=llm_name
    )

    await i_data.add_llm_usage(
        new_transaction_details.id, #type: ignore
        "graph",
        llm=llm_name,
        **token_usage.model_dump()
        )

    GRAPHS_GENERATED_PER_QUESTION.labels(data.dbname).inc(len(graphs_list))

    if not graphs_list:
        GRAPHS_ERRORS.labels(data.dbname).inc()
        logger.warning(f"Graphs were not generated successfully for the table {suggested_df.shape}, {suggested_df.columns}")
    else:
        GRAPHS_GENERATED_PER_QUESTION.labels(data.dbname).inc(len(graphs_list))
        logger.info(f"Graph generated successfully for data {suggested_df.shape}, {suggested_df.columns}")
        plotly_graphs = []
        for g in graphs_list:
            plotly_graphs.append(Plotly_Graph(
                graph_id=g["graph_id"],
                plotly_code=g["graph"],
                chart_type=g["type"]
            ))
        await nosql_helper.record_graph(
            transaction_id=new_transaction_details.id, #type: ignore
            graphs=plotly_graphs
        )

    try:
        drilldown_features_mappings_list = get_drilldown_features(
            data.dbname, 
            pd.DataFrame(clicked_suggestion.sql_table)
        )
    except Exception as e:
        logger.error(
            "Error during fetching drilldown features",
            extra={"event_type": "drilldown_features_error", "error": str(e)},
            exc_info=True,
        )
        drilldown_features_mappings_list = []

    table_keys = clicked_suggestion.sql_table[0].keys()
    table_columns = {f"column_{k}": v for k, v in enumerate(table_keys)}

    # Format percentage values only for the final API response.
    # Keep clicked_suggestion.sql_table numeric for MongoDB storage,
    # DataFrame processing, graph generation, and drilldown logic.
    response_table = format_percentage_columns(
        clicked_suggestion.sql_table
    )
    
    return {
        "query_key": str(new_transaction_details.id), #type: ignore
        "query_id": str(data.transaction_id),
        "id": str(clicked_suggestion.suggestion_id),
        "suggestion_query": clicked_suggestion.user_query,
        "chart_type": "auto",
        "chart_sub_type": "auto",
        "chat_id": data.chat_id,
        "sql": clicked_suggestion.sql_code,
        "table": response_table,
        "table_columns": table_columns,
        "plotlycharts": graphs_list,
        "comment": "",
        "status": 200,
        "status_message": "Success",
        "drilldown_features": drilldown_features_mappings_list,
        "approach": clicked_suggestion.approach
    }