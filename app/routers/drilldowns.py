from fastapi import APIRouter, HTTPException, Depends
import os
import json
import yaml
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DoubleClick
from app.logger import get_logger
from app.databases.dependencies import (
    get_db_async,
    get_vector_client,
    get_nosql_client,
    get_pool,
)
from app.databases.client_sql.operations import (
    get_table_from_sql,
    get_table_and_status_and_columns,
    get_table_from_sql_parallel,
)
from app.core.text_2_sql.drilldown import GraphDrillDown
from app.core.helper import (
    serialize_filters,
    format_percentage_columns,
)
from app.core.llms import get_llm, get_llm_response
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from .base_check import perform_base_check
# from app.core.table_from_sql import get_table_from_sql
from app.core.prompts import PromptGetter
import pandas as pd
from app.core.prometheus_metrics import (
    TEXT2SQL_HITS,
    TEXT2SQL_ERRORS,
    TEXT2SQL_FIRST_SUCCESS,
)
from app.databases.vector.operations import VectorStore


router = APIRouter(prefix="/egai", tags=["Drilldown"])

logger = get_logger()


@router.get("/create_hierarchies", status_code=200)
async def create_hierarchies(
    dbname: str,
    session: AsyncSession = Depends(get_db_async),
):
    i_data = InternalSQLHelper(session)

    base_path = f"business_data/{dbname}/hierarchies.json"
    check_file_existance = os.path.exists(base_path)

    if check_file_existance:
        with open(base_path, "r") as f:
            heirachy_json = json.load(f)
        return heirachy_json

    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    prompt_getter = PromptGetter(dbname)
    hierarchies_sys_prompt = prompt_getter.get_prompt(
        "hierarchies_sys_prompt"
    )

    schema_text_file_path = f"app/core/schema_strings/{dbname}.txt"
    with open(schema_text_file_path, "r", encoding="UTF-8") as f:
        schema_str = f.read()

    messages = [
        {
            "role": "system",
            "content": hierarchies_sys_prompt,
        },
        {
            "role": "user",
            "content": f"SCHEMA: {schema_str}",
        },
    ]

    results, token_usage = await get_llm_response(
        llm,
        llm_name,
        messages,
    )

    await i_data.add_llm_usage(
        api_endpoint="hierarchy",
        llm=llm_name,
        **token_usage.model_dump(),
    )

    with open(base_path, "w") as f:
        json.dump(results, f)

    return results


@router.post("/chatWithGraph", status_code=200)
async def graph_double_click(
    data: DoubleClick,
    session: AsyncSession = Depends(get_db_async),
):
    TEXT2SQL_HITS.labels(data.dbname).inc()

    i_data = InternalSQLHelper(session)

    await get_nosql_client()

    fetched_details = await i_data.get_dataset_and_connection_details(
        db_name=data.dbname
    )
    if not fetched_details:
        raise HTTPException(
            status_code=404,
            detail="Dataset and DB Connection not found",
        )

    db_details, connection_details = fetched_details
    client_pool = await get_pool(
        db_details,
        connection_details,
    )

    await get_nosql_client()
    nosql_helper = NOSQLHelper()

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)
    await vector_db.ensure_collection(data.dbname)

    user_details, db_details, chat_details = await perform_base_check(
        i_data,
        data.first_name,
        data.last_name,
        data.email_id,
        data.dbname,
        data.chat_id,
    )

    filters_json = serialize_filters(data.filters)

    if not data.drilldown_features:
        raise HTTPException(
            detail="Drill down feature is not provided",
            status_code=404,
        )

    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    clicked_values = [
        data.click_event[0].X,
        data.click_event[0].Y,
        data.click_event[0].legend,
    ]

    df = pd.DataFrame(data.table)

    clicked_feature_value_mappings = []

    for clicked_value in clicked_values:
        for column_name in df.columns:
            if clicked_value in df[column_name].values.tolist():
                clicked_feature_value_mappings.append(
                    {
                        "column": column_name,
                        "clicked_value": clicked_value,
                    }
                )

            if clicked_value in ["NSAT", "DSAT", "CSAT"]:
                clicked_feature_value_mappings.append(
                    {
                        "column": "Rating",
                        "clicked_value": clicked_value,
                    }
                )

            if clicked_value in [
                "NPS",
                "Likely_to_Recoomend_HPE",
            ]:
                clicked_feature_value_mappings.append(
                    {
                        "column": "Likely_to_Recoomend_HPE",
                        "clicked_value": clicked_value,
                    }
                )

    graph_drilldown = GraphDrillDown(
        data.dbname,
        llm=llm,
        llm_name=llm_name,
        initial_question=data.query,
        initial_sql=data.sql,
        filters=filters_json,
        exploration_feature=data.drilldown_features[0].col_name,
        clicked_features=clicked_feature_value_mappings,
        vector_client=vector_db,
    )

    resp = await graph_drilldown.question_and_sql_query_generator()

    if not resp:
        await i_data.add_llm_usage(
            api_endpoint="drilldown",
            llm=llm_name,
            **graph_drilldown.token_usage.model_dump(),
        )
        raise HTTPException(
            detail="LLM response not generated properly",
            status_code=400,
        )

    if not resp.get("new_sql"):
        await i_data.add_llm_usage(
            api_endpoint="drilldown",
            llm=llm_name,
            **graph_drilldown.token_usage.model_dump(),
        )
        raise HTTPException(
            detail="SQL not generated properly",
            status_code=400,
        )

    query_results = await get_table_from_sql(
        client_pool,
        data.dbname,
        resp["new_sql"],
        row_limit=500,
    )

    table_json, table_status, table_columns = (
        get_table_and_status_and_columns(query_results)
    )

    query_details = await i_data.create_or_get_query(
        user_query=resp["new_question"]
    )
    if not query_details:
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        raise HTTPException(
            detail="Query not saved properly",
            status_code=400,
        )

    sql_details = await i_data.create_or_get_sql(
        sql_code=resp["new_sql"]
    )
    if not sql_details:
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        raise HTTPException(
            detail="SQL not saved properly",
            status_code=400,
        )

    new_transaction_details = await i_data.create_transaction(
        db_id=db_details.id,
        query_id=query_details.id,
        sql_id=sql_details.id,
        chat_id=data.chat_id,
        filters=filters_json,
        approach=resp.get("approach"),
        question_type=(
            "complete"
            if table_status == "success"
            else "error"
        ),
        raw_response=json.dumps(
            {
                "sql_query": resp["new_sql"],
                "approach": resp["approach"],
            }
        ),
        resolved_query=resp["new_question"],
    )

    # Store the original numeric table.
    await nosql_helper.record_table(
        new_transaction_details.id,
        table_json,
        resp["approach"],
    )

    if table_status != "success":
        raise HTTPException(
            detail="SQL is not executable",
            status_code=400,
        )

    error_message = ""

    if not table_json:
        TEXT2SQL_ERRORS.labels(data.dbname).inc()
        error_message = (
            "No data found for the given selection. "
            "Try clicking other fields or selecting another "
            "feature for drilldown."
        )

    TEXT2SQL_FIRST_SUCCESS.labels(data.dbname).inc()

    # Format only the final API response. Internal and stored values remain
    # numeric for later graphs, calculations, sorting, and drilldowns.
    response_table = format_percentage_columns(table_json)

    return {
        "query_key": str(new_transaction_details.id),
        "query_id": str(data.transaction_id),
        "query": resp["new_question"],
        "chat_id": data.chat_id,
        "sql": resp["new_sql"],
        "table": response_table,
        "table_columns": table_columns,
        "status_message": (
            "complete"
            if table_status == "success" and table_json
            else "awaiting_human_input"
        ),
        "status": (
            200
            if table_status == "success" and table_json
            else 406
        ),
        "chart_type": "auto",
        "chart_sub_type": "auto",
        "sql_response": (
            resp["new_sql"]
            if table_json
            else error_message
        ),
        "prompt": "",
        "approach": resp["approach"],
        "resolved_query": resp["new_question"],
    }
