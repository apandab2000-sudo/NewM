from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ask_question.driver_analysis.service import run_driver_analysis
from app.core.llm_connections.outputs import llm_factory
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.dependencies import get_pool
from app.models import EditGraph


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _shape_driver_analysis_response(data: EditGraph, driver_analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": 200,
        "status_message": "Success",
        "chart_type": "driver_analysis",
        "chart_sub_type": data.chart_sub_type,
        "plotlycharts": [],
        "drilldown_features": [],
        "driver_analysis": driver_analysis,
    }


def _transaction_id_from_query_key(query_key: str) -> int:
    try:
        return int(query_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="query_key must be a valid transaction id") from exc


async def build_driver_analysis_edit_graph_response(
    data: EditGraph,
    db_session: AsyncSession,
) -> dict[str, Any]:
    dataset_helper = DatasetHelper(db_session)
    db_details, connection_details = await dataset_helper.get_dataset_and_connection_details(db_name=data.dbname)
    if not db_details or not connection_details:
        raise HTTPException(status_code=404, detail="Dataset and DB connection not found")

    transaction_context = await InternalSQLHelper(db_session).get_transaction_context_from_id(
        _transaction_id_from_query_key(data.query_key)
    )
    if not transaction_context:
        raise HTTPException(status_code=404, detail="Transaction details not found for query_key")

    sql = _first_non_empty(data.sql, transaction_context.get("sql_code"))
    analysis_query = _first_non_empty(
        data.previous_user_query,
        data.resolved_query,
        transaction_context.get("resolved_query"),
        transaction_context.get("user_query"),
        data.query,
    )

    client_pool = await get_pool(db_details, connection_details)
    llm = llm_factory.get_llm(provider="openai", model="gpt-4.1")

    driver_analysis = await run_driver_analysis(
        dbname=data.dbname,
        llm=llm,
        client_pool=client_pool,
        query=analysis_query,
        sql=sql,
        table=data.table,
    )

    return _shape_driver_analysis_response(data, driver_analysis)
