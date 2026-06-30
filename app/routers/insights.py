from fastapi import APIRouter, HTTPException, Depends
import re
import yaml
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import GetInsights
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
from app.core.helper import (
    serialize_filters,
    format_percentage_columns,
)
from app.core.llms import get_llm
# from app.databases.nosql_schema import Insights, InightsTablePart
from app.databases.application_nosql.models import Insights, InightsTablePart
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from .base_check import perform_base_check
# from app.core.table_from_sql import get_table_from_sql_parallel
from app.core.inisghts.insightsAgent import InsightsGenerator
from app.appConfig import settings
from app.core.prometheus_metrics import (
    INSIGHTS_GENERATED_FOR_QUESTION,
    INSIGHTS_GENERATION_ERRORS,
    INSIGHTS_HITS,
)
from app.databases.vector.operations import VectorStore


router = APIRouter(prefix="/egai", tags=["Insights"])


logger = get_logger(__name__)


def normalize_percentage_text(text):
    """
    Convert percentage wording in generated insight text to the % symbol.

    Examples:
        "24.5 percent"     -> "24.5%"
        "24.5 percentage"  -> "24.5%"
        "24.5%"            -> "24.5%"

    The function preserves HTML and non-percentage text.
    """
    if not isinstance(text, str):
        return text

    return re.sub(
        r"(?P<value>-?\d+(?:\.\d+)?)\s*(?:percent(?:age)?)(?:\s*points?)?",
        lambda match: f"{match.group('value')}%",
        text,
        flags=re.IGNORECASE,
    )


@router.post("/getIntelligentInsights", status_code=200)
async def get_insights(
    data: GetInsights,
    session: AsyncSession = Depends(get_db_async),
):
    INSIGHTS_HITS.labels(data.dbname).inc()

    # Database connections
    i_data = InternalSQLHelper(session)
    nosql_client = await get_nosql_client()

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)
    await vector_db.ensure_collection(data.dbname)

    fetched_details = await i_data.get_dataset_and_connection_details(
        db_name=data.dbname
    )
    if not fetched_details:
        raise HTTPException(
            status_code=404,
            detail="Dataset and DB Connection not found",
        )

    db_details, connection_details = fetched_details
    client_pool = await get_pool(db_details, connection_details)

    nosql_helper = NOSQLHelper()

    _ = await perform_base_check(
        i_data,
        data.first_name,
        data.last_name,
        data.email_id,
        data.dbname,
        data.chat_id,
    )

    filters_json = serialize_filters(data.filters)

    transaction_details = await i_data.get_transaction_details_from_id(
        data.transaction_id
    )
    if not transaction_details:
        raise HTTPException(
            detail=(
                "Base question didn't run successfully. "
                "No Transaction Details found"
            ),
            status_code=404,
        )

    resolved_query = (
        transaction_details.resolved_query
        if transaction_details.resolved_query
        else data.query
    )

    sql_details = await i_data.get_sql_details_from_id(
        transaction_details.sql_id
    )
    if not sql_details:
        raise HTTPException(
            detail="Base question didn't run successfully. No Base SQL found",
            status_code=404,
        )

    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    insights_generator = InsightsGenerator(
        dbname=data.dbname,
        llm=llm,
        llm_name=llm_name,
        question=resolved_query,
        filters=filters_json,
        sql_query=sql_details.sql_code,
        vector_client=vector_db,
    )

    insights_sqls = (
        await insights_generator.extract_cols_and_descriptive_sqls()
    )

    if not insights_sqls:
        await i_data.add_llm_usage(
            data.transaction_id,
            "insights",
            llm_name,
            **insights_generator.token_usage.model_dump(),
        )
        logger.error("Insights SQLs not generated properly")
        raise HTTPException(
            detail="Insights not generated successfully",
            status_code=400,
        )

    sql_queries = [
        item["sql_query"]
        for item in insights_sqls["additional_sqls"]
    ]

    query_results = await get_table_from_sql_parallel(
        client_pool,
        data.dbname,
        sql_queries,
        settings.client_connection_pool_per_worker,
        row_limit=500,
    )

    # Format only the copies passed to the LLM. This ensures percentage
    # metrics are visible with % while leaving original source data unchanged.
    primary_table = format_percentage_columns(data.table)

    secondary_tables = []

    for result in query_results:
        if not result:
            secondary_tables.append([])
            continue

        table_json, table_status, _ = (
            get_table_and_status_and_columns(result)
        )

        if table_json and table_status == "success":
            print("table_added")
            formatted_table = format_percentage_columns(table_json)
            secondary_tables.append(formatted_table)
        else:
            print("table_not_added")
            secondary_tables.append([])

    executive_synopsis = await insights_generator.generate_insights(
        primary_table,
        secondary_tables,
    )

    await i_data.add_llm_usage(
        data.transaction_id,
        "insights",
        llm_name,
        **insights_generator.token_usage.model_dump(),
    )

    if not executive_synopsis:
        INSIGHTS_GENERATION_ERRORS.labels(data.dbname).inc()
        raise HTTPException(
            status_code=400,
            detail="Insights not generated successfully",
        )

    INSIGHTS_GENERATED_FOR_QUESTION.labels(data.dbname).inc()

    consolidated_insight = normalize_percentage_text(
        executive_synopsis["executive_synopsis"]["summary"]
    )

    detailed_analysis = normalize_percentage_text(
        executive_synopsis["executive_synopsis"]["detailed_analysis"]
    )

    distinct_insights = detailed_analysis.split("<h3>")
    distinct_insights = [
        insight.strip()
        for insight in distinct_insights
        if insight.strip()
    ]
    distinct_insights = [
        "<h3>" + insight
        for insight in distinct_insights
    ]

    table_parts = [
        InightsTablePart(sql=sql, table=table)
        for sql, table in zip(sql_queries, secondary_tables)
    ]

    nosql_insights_data = Insights(
        distinct_insights=distinct_insights,
        consolidated_insight=consolidated_insight,
        insights_data=table_parts,
    )

    await nosql_helper.record_insights(
        transaction_id=data.transaction_id,
        insights=nosql_insights_data,
    )

    return {
        "status": 200,
        "status_message": "Success",
        "insights": distinct_insights,
        "consolidated_insights": consolidated_insight,
    }
