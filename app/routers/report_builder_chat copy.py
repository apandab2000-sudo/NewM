from fastapi import APIRouter, Depends, HTTPException
from app.models import ReportConversation, ReportGeneration, ReportSelectable, ResetChat
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.connections import (
    get_db_async,
    get_nosql_client,
    client_connection_pool,
    get_vector_db,
    get_redis_client
)
from app.databases.internal_sql_operations import InternalSQLHelper
from app.databases.internal_nosql_operations import NOSQLHelper
from app.databases.nosql_schema import Plotly_Graph
from app.core.table_from_sql import get_table_from_sql_parallel, get_table_from_sql
from app.appConfig import settings
from app.core.graphs.plotly.custom_dashboard import generate_custom_kpi_graphs
import pandas as pd
import asyncio
from app.core.helper import get_table_and_status_and_columns, log_sql_data, get_drilldown_features
import yaml
import json
import os
from datetime import date, datetime
from decimal import Decimal
from app.core.dashboards.introductions import get_column_stats, get_updated_metadata
from .base_check import perform_base_check
from app.core.llms import get_llm
from app.core.dashboards.custom_dashboard import GenerateCustomDashboard
from app.core.graphs.plotly.base import generate_graphs
from app.core.graphs.echarts.graphs import GraphGenerator
from app.core.report_builder.report_component import ReportComponent
from app.core.text_2_sql.text2sql import Text2SQL
from app.databases.vector_operations import VectorStore
from app.core.graphs.echarts.graphs import GraphGenerator, generate_graph_title
from .report_builder import process_username
import uuid
from app.core.report_builder.report_component import ReportChat, AgentState
from typing import List, Optional
from fastapi.encoders import jsonable_encoder

VERSION = "v1"

router = APIRouter(prefix=f"/egai/report_builder/{VERSION}", tags=["Report Builder"])

logger = get_logger()

def get_client_config(dbname: str):
    config_path = "app/clientConfig.yaml"
    if not os.path.exists(config_path):
        return None
    
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    return config.get(dbname)

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


@router.post('/reports/suggestions', status_code=200)
async def get_report_suggestions(
    payload: ResetChat,
    session: AsyncSession = Depends(get_db_async)
):
    # 1. Fetch config for the specific dbname
    config = get_client_config(payload.dbname)
    
    if not config:
        raise HTTPException(
            status_code=404, 
            detail=f"Configuration for database '{payload.dbname}' not found."
        )
    suggestions = config.get("REPORT_SUGGESTIONS", [])

    return {
        "dbname": payload.dbname,
        "prompt_suggestions": suggestions,
        "status": 200,
        "status_message": "Success",
    }

@router.post(f'/reports/conversation-id', status_code=200)
async def get_conversation_id(
    payload: ReportConversation,
    session: AsyncSession = Depends(get_db_async)
):
    redis_client = get_redis_client()

    first_name, last_name, email_id = process_username(payload.user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=payload.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(payload.report_id)
    if not report_details:
        raise HTTPException(detail="Report with provided id not found", status_code=404)
    
    chat_id = str(uuid.uuid4()) + "-report-" + str(user_details.id) + "-" + str(db_details.id)
    chat_details = await i_data.create_or_get_chat(
        chat_id=chat_id, user_id=user_details.id, db_id=db_details.id, is_report=True
    )
    if not chat_details:
        raise HTTPException(
            detail="Chat does not exists nor created successfully", status_code=404
        )
    
    return {
        "chat_id": chat_id,
        "prompot_suggestions": [
            'Generate a report showing total Sell In Gross Revenue and On Hand Inventory by country and business unit for 2023, with a breakdown by quarter.',
            'Provide a summary dashboard of Gross Profit and Gross To Net Ratio across all regions for the last fiscal year, highlighting top-selling product groups.',
            'Create a report comparing Sell In Net Revenue and inventory aged over 60 days by brand and region for senior leadership.'
        ],
        "status": 200,
        "status_message": "Success",
    }


@router.post(f'/reports/generate-report-chat', status_code=200)
async def generate_report_through_chat(
    payload: ReportGeneration,
    session: AsyncSession = Depends(get_db_async)
):
    redis_client = get_redis_client()
    
    i_data = InternalSQLHelper(session)

    chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
    if not chat_details:
        raise HTTPException(detail="Chat does not exists nor created successfully", status_code=404)
    
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    report_workflow_transactions = await i_data.get_report_history(payload.chat_id)
    chat_history = []
    for m in report_workflow_transactions:
        chat_history.extend([
            {"role": "uuer", "content": m.query},
            {"role": "assistant", "content": m.text_output}
        ])

    if report_workflow_transactions:
        lt = report_workflow_transactions[-1]
        agent_state = AgentState(
            intent_messages=json.loads(lt.intent_messages) if lt.intent_messages else [],
            kpi_messages=json.loads(lt.kpi_messages) if lt.kpi_messages else [],
            additional_detail_messages=json.loads(lt.additional_detail_messages) if lt.additional_detail_messages else [],
            structure_messages=json.loads(lt.structure_messages) if lt.structure_messages else [],
            report_messages=json.loads(lt.report_messages) if lt.report_messages else [],
            kpis=json.loads(lt.kpis) if lt.kpis else None,
            structure=json.loads(lt.structure) if lt.structure else None,
            build_type=lt.build_type,
            initial_query=lt.initial_query,
            intent=lt.intent,
            report=json.loads(lt.report) if lt.report else None,
            completed_steps=json.loads(lt.completed_steps) if lt.completed_steps else [],
            additional_details=json.loads(lt.additional_details) if lt.additional_details else None
        )
        # agent_state = AgentState(**json.loads(report_workflow_transactions[-1].state))
    else:
        agent_state = AgentState()

    report_chat = ReportChat(
        dbname=payload.dbname,
        llm=llm, 
        llm_name=llm_name,
        agent_state=agent_state
    )

    resp = await report_chat.workflow_agent(query=payload.query)

    print("&&&&&&&&&&&&&&&&&&&&&")
    print(resp)
    print("&&&&&&&&&&&&&&&&&&&&&")

    # report_transactions_details = await i_data.add_report_workflow_transaction({
    #     "report_id": payload.report_id,
    #     "chat_id": payload.chat_id,
    #     "query": payload.query,
    #     "text_output": resp["response"] if resp else None,
    #     "options": json.dumps(resp["options"]) if resp else None,
    #     # "state": json.dumps(report_chat.agent_state.model_dump())
    #     "intent_messages": json.dumps(report_chat.agent_state.intent_messages) if report_chat.agent_state.intent_messages else None,
    #     "kpi_messages": json.dumps(report_chat.agent_state.kpi_messages) if report_chat.agent_state.kpi_messages else None,
    #     "additional_detail_messages": json.dumps(report_chat.agent_state.additional_detail_messages) if report_chat.agent_state.additional_detail_messages else None,
    #     "structure_messages": json.dumps(report_chat.agent_state.structure_messages) if report_chat.agent_state.structure_messages else None,
    #     "report_messages": json.dumps(report_chat.agent_state.report_messages) if report_chat.agent_state.report_messages else None,
    #     "kpis": json.dumps(report_chat.agent_state.kpis) if report_chat.agent_state.kpis else None,
    #     "structure": json.dumps(report_chat.agent_state.structure) if report_chat.agent_state.structure else None,
    #     "build_type": report_chat.agent_state.build_type,
    #     "initial_query": report_chat.agent_state.initial_query,
    #     "intent": report_chat.agent_state.intent,
    #     "report": json.dumps(report_chat.agent_state.report) if report_chat.agent_state.report else None,
    #     "completed_steps": json.dumps(report_chat.agent_state.completed_steps) if report_chat.agent_state.completed_steps else [],
    #     "additional_details": json.dumps(report_chat.agent_state.additional_details) if report_chat.agent_state.additional_details else []
    # })

    report_transactions_details = await i_data.add_report_workflow_transaction({
        "report_id": payload.report_id,
        "chat_id": payload.chat_id,
        "query": payload.query,
        "text_output": resp["response"] if resp else None,
        "options": json.dumps(resp["options"]) if resp else None,
        # "state": json.dumps(report_chat.agent_state.model_dump())
        # FIX: Added default=json_serial to all dumps
        "intent_messages": json.dumps(report_chat.agent_state.intent_messages, default=json_serial) if report_chat.agent_state.intent_messages else None,
        "kpi_messages": json.dumps(report_chat.agent_state.kpi_messages, default=json_serial) if report_chat.agent_state.kpi_messages else None,
        "additional_detail_messages": json.dumps(report_chat.agent_state.additional_detail_messages, default=json_serial) if report_chat.agent_state.additional_detail_messages else None,
        "structure_messages": json.dumps(report_chat.agent_state.structure_messages, default=json_serial) if report_chat.agent_state.structure_messages else None,
        "report_messages": json.dumps(report_chat.agent_state.report_messages, default=json_serial) if report_chat.agent_state.report_messages else None,
        "kpis": json.dumps(report_chat.agent_state.kpis, default=json_serial) if report_chat.agent_state.kpis else None,
        "structure": json.dumps(report_chat.agent_state.structure, default=json_serial) if report_chat.agent_state.structure else None,
        
        "build_type": report_chat.agent_state.build_type,
        "initial_query": report_chat.agent_state.initial_query,
        "intent": report_chat.agent_state.intent,
        
        "report": json.dumps(report_chat.agent_state.report, default=json_serial) if report_chat.agent_state.report else None,
        
        "completed_steps": json.dumps(report_chat.agent_state.completed_steps) if report_chat.agent_state.completed_steps else [],
        "additional_details": json.dumps(report_chat.agent_state.additional_details, default=json_serial) if report_chat.agent_state.additional_details else []
    })

    llm_usage = await i_data.add_llm_usage(
        report_transactions_details.id,
        api_endpoint="report_workflow",
        llm=llm_name,
        **report_chat.token_usage.model_dump()
    )

    # return {
    #     "text_output": resp["response"],
    #     "options": resp["options"],
    #     "state": {
    #         "kpis": report_chat.agent_state.kpis,
    #         "intent": report_chat.agent_state.intent,
    #         "report": report_chat.agent_state.report,
    #         "structure": report_chat.agent_state.structure,
    #         "contextual_scope": report_chat.agent_state.additional_details
    #     }
    # }

    return {
        "text_output": resp["response"],
        "options": resp["options"],
        "state": jsonable_encoder({ # This will safely convert dates to strings
            "kpis": report_chat.agent_state.kpis,
            "intent": report_chat.agent_state.intent,
            "report": report_chat.agent_state.report,
            "structure": report_chat.agent_state.structure,
            "contextual_scope": report_chat.agent_state.additional_details
        })
    }