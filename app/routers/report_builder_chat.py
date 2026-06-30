from fastapi import APIRouter, Depends, HTTPException
from app.models import ReportConversation, ReportGeneration, ReportSelectable, ResetChat
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.dependencies import (
    get_db_async,
    get_vector_client,
    get_nosql_client,
    get_pool,
    get_caching_client,
)
# Update SQL helpers to the new location
from app.databases.client_sql.operations import (
    get_table_from_sql, 
    get_table_and_status_and_columns, 
    get_table_from_sql_parallel
)
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.application_nosql.models import Plotly_Graph
# from app.core.table_from_sql import get_table_from_sql_parallel, get_table_from_sql
from app.appConfig import settings
from app.core.graphs.plotly.custom_dashboard import generate_custom_kpi_graphs
import pandas as pd
import asyncio
from app.core.helper import log_sql_data, get_drilldown_features
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
# from app.databases.vector_operations import VectorStore
from app.databases.vector.operations import VectorStore
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


# def detect_skip_intent(query: str) -> dict:
#     """Detect if user wants to skip steps or auto-generate"""
#     skip_patterns = {
#         "auto_generate": ["add all", "generate all", "build now", "create report", "let's build"],
#         "confirm": ["yes", "ok", "proceed", "next", "continue", "looks good"],
#         "skip_scope": ["skip", "no filters", "basic", "simple"],
#     }
    
#     query_lower = query.lower()
    
#     for intent, patterns in skip_patterns.items():
#         if any(pattern in query_lower for pattern in patterns):
#             return {"intent": intent, "detected": True}
    
#     return {"intent": None, "detected": False}

def detect_skip_intent(query: str) -> dict:
    q = query.lower()
    # High-intent keywords for Auto-Generation
    if any(x in q for x in ["generate report", "build report", "create dashboard", "give me a report", "build now", "add all"]):
        return {"intent": "auto_generate", "detected": True}
    
    # Affirmative keywords for transition
    if any(x in q for x in ["yes", "proceed", "looks good", "next", "continue", "build structure"]):
        return {"intent": "proceed", "detected": True}
    
    return {"intent": None, "detected": False}

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
    # redis_client = get_redis_client()
    # REDIS UPDATE: Use caching_client from connections
    redis = get_caching_client 

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

# #########################
# @router.post(f'/reports/generate-report-chat', status_code=200)
# async def generate_report_through_chat(
#     payload: ReportGeneration,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     redis_client = get_redis_client()
    
#     i_data = InternalSQLHelper(session)

#     chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
#     if not chat_details:
#         raise HTTPException(detail="Chat does not exists nor created successfully", status_code=404)
    
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     report_workflow_transactions = await i_data.get_report_history(payload.chat_id)
#     chat_history = []
#     for m in report_workflow_transactions:
#         chat_history.extend([
#             {"role": "uuer", "content": m.query},
#             {"role": "assistant", "content": m.text_output}
#         ])

#     if report_workflow_transactions:
#         lt = report_workflow_transactions[-1]
#         agent_state = AgentState(
#             intent_messages=json.loads(lt.intent_messages) if lt.intent_messages else [],
#             kpi_messages=json.loads(lt.kpi_messages) if lt.kpi_messages else [],
#             additional_detail_messages=json.loads(lt.additional_detail_messages) if lt.additional_detail_messages else [],
#             structure_messages=json.loads(lt.structure_messages) if lt.structure_messages else [],
#             report_messages=json.loads(lt.report_messages) if lt.report_messages else [],
#             kpis=json.loads(lt.kpis) if lt.kpis else None,
#             structure=json.loads(lt.structure) if lt.structure else None,
#             build_type=lt.build_type,
#             initial_query=lt.initial_query,
#             intent=lt.intent,
#             report=json.loads(lt.report) if lt.report else None,
#             completed_steps=json.loads(lt.completed_steps) if lt.completed_steps else [],
#             additional_details=json.loads(lt.additional_details) if lt.additional_details else None
#         )
#         # agent_state = AgentState(**json.loads(report_workflow_transactions[-1].state))
#     else:
#         agent_state = AgentState()

#     report_chat = ReportChat(
#         dbname=payload.dbname,
#         llm=llm, 
#         llm_name=llm_name,
#         agent_state=agent_state
#     )

#     resp = await report_chat.workflow_agent(query=payload.query)

#     print("&&&&&&&&&&&&&&&&&&&&&")
#     print(resp)
#     print("&&&&&&&&&&&&&&&&&&&&&")

#     # report_transactions_details = await i_data.add_report_workflow_transaction({
#     #     "report_id": payload.report_id,
#     #     "chat_id": payload.chat_id,
#     #     "query": payload.query,
#     #     "text_output": resp["response"] if resp else None,
#     #     "options": json.dumps(resp["options"]) if resp else None,
#     #     # "state": json.dumps(report_chat.agent_state.model_dump())
#     #     "intent_messages": json.dumps(report_chat.agent_state.intent_messages) if report_chat.agent_state.intent_messages else None,
#     #     "kpi_messages": json.dumps(report_chat.agent_state.kpi_messages) if report_chat.agent_state.kpi_messages else None,
#     #     "additional_detail_messages": json.dumps(report_chat.agent_state.additional_detail_messages) if report_chat.agent_state.additional_detail_messages else None,
#     #     "structure_messages": json.dumps(report_chat.agent_state.structure_messages) if report_chat.agent_state.structure_messages else None,
#     #     "report_messages": json.dumps(report_chat.agent_state.report_messages) if report_chat.agent_state.report_messages else None,
#     #     "kpis": json.dumps(report_chat.agent_state.kpis) if report_chat.agent_state.kpis else None,
#     #     "structure": json.dumps(report_chat.agent_state.structure) if report_chat.agent_state.structure else None,
#     #     "build_type": report_chat.agent_state.build_type,
#     #     "initial_query": report_chat.agent_state.initial_query,
#     #     "intent": report_chat.agent_state.intent,
#     #     "report": json.dumps(report_chat.agent_state.report) if report_chat.agent_state.report else None,
#     #     "completed_steps": json.dumps(report_chat.agent_state.completed_steps) if report_chat.agent_state.completed_steps else [],
#     #     "additional_details": json.dumps(report_chat.agent_state.additional_details) if report_chat.agent_state.additional_details else []
#     # })

#     report_transactions_details = await i_data.add_report_workflow_transaction({
#         "report_id": payload.report_id,
#         "chat_id": payload.chat_id,
#         "query": payload.query,
#         "text_output": resp["response"] if resp else None,
#         "options": json.dumps(resp["options"]) if resp else None,
#         # "state": json.dumps(report_chat.agent_state.model_dump())
#         # FIX: Added default=json_serial to all dumps
#         "intent_messages": json.dumps(report_chat.agent_state.intent_messages, default=json_serial) if report_chat.agent_state.intent_messages else None,
#         "kpi_messages": json.dumps(report_chat.agent_state.kpi_messages, default=json_serial) if report_chat.agent_state.kpi_messages else None,
#         "additional_detail_messages": json.dumps(report_chat.agent_state.additional_detail_messages, default=json_serial) if report_chat.agent_state.additional_detail_messages else None,
#         "structure_messages": json.dumps(report_chat.agent_state.structure_messages, default=json_serial) if report_chat.agent_state.structure_messages else None,
#         "report_messages": json.dumps(report_chat.agent_state.report_messages, default=json_serial) if report_chat.agent_state.report_messages else None,
#         "kpis": json.dumps(report_chat.agent_state.kpis, default=json_serial) if report_chat.agent_state.kpis else None,
#         "structure": json.dumps(report_chat.agent_state.structure, default=json_serial) if report_chat.agent_state.structure else None,
        
#         "build_type": report_chat.agent_state.build_type,
#         "initial_query": report_chat.agent_state.initial_query,
#         "intent": report_chat.agent_state.intent,
        
#         "report": json.dumps(report_chat.agent_state.report, default=json_serial) if report_chat.agent_state.report else None,
        
#         "completed_steps": json.dumps(report_chat.agent_state.completed_steps) if report_chat.agent_state.completed_steps else [],
#         "additional_details": json.dumps(report_chat.agent_state.additional_details, default=json_serial) if report_chat.agent_state.additional_details else []
#     })

#     llm_usage = await i_data.add_llm_usage(
#         report_transactions_details.id,
#         api_endpoint="report_workflow",
#         llm=llm_name,
#         **report_chat.token_usage.model_dump()
#     )

#     # return {
#     #     "text_output": resp["response"],
#     #     "options": resp["options"],
#     #     "state": {
#     #         "kpis": report_chat.agent_state.kpis,
#     #         "intent": report_chat.agent_state.intent,
#     #         "report": report_chat.agent_state.report,
#     #         "structure": report_chat.agent_state.structure,
#     #         "contextual_scope": report_chat.agent_state.additional_details
#     #     }
#     # }

#     return {
#         "text_output": resp["response"],
#         "options": resp["options"],
#         "state": jsonable_encoder({ # This will safely convert dates to strings
#             "kpis": report_chat.agent_state.kpis,
#             "intent": report_chat.agent_state.intent,
#             "report": report_chat.agent_state.report,
#             "structure": report_chat.agent_state.structure,
#             "contextual_scope": report_chat.agent_state.additional_details
#         })
#     }


########################### skip working 
# @router.post(f'/reports/generate-report-chat', status_code=200)
# async def generate_report_through_chat(
#     payload: ReportGeneration,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     """
#     Enhanced endpoint with better workflow control and post-generation refinement.
#     """
#     redis_client = get_redis_client()
#     i_data = InternalSQLHelper(session)

#     chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
#     if not chat_details:
#         raise HTTPException(detail="Chat not found", status_code=404)
    
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     # Detect if user wants to skip approval loops
#     skip_intent = detect_skip_intent(payload.query)

#     # Retrieve previous report history
#     report_workflow_transactions = await i_data.get_report_history(payload.chat_id)
    
#     # Reconstruct agent state from DB
#     # if report_workflow_transactions:
#     #     lt = report_workflow_transactions[-1]
#     #     agent_state = AgentState(
#     #         intent_messages=json.loads(lt.intent_messages) if lt.intent_messages else [],
#     #         kpi_messages=json.loads(lt.kpi_messages) if lt.kpi_messages else [],
#     #         additional_detail_messages=json.loads(lt.additional_detail_messages) if lt.additional_detail_messages else [],
#     #         structure_messages=json.loads(lt.structure_messages) if lt.structure_messages else [],
#     #         report_messages=json.loads(lt.report_messages) if lt.report_messages else [],
#     #         kpis=json.loads(lt.kpis) if lt.kpis else None,
#     #         structure=json.loads(lt.structure) if lt.structure else None,
#     #         build_type=lt.build_type,
#     #         initial_query=lt.initial_query,
#     #         intent=lt.intent,
#     #         report=json.loads(lt.report) if lt.report else None,
#     #         completed_steps=json.loads(lt.completed_steps) if lt.completed_steps else [],
#     #         additional_details=json.loads(lt.additional_details) if lt.additional_details else None
#     #     )
#     # else:
#     #     agent_state = AgentState()

#     if report_workflow_transactions:
#         lt = report_workflow_transactions[-1]
        
#         # Parse report - handle both dict and list cases
#         report_data = None
#         if lt.report:
#             try:
#                 report_data = json.loads(lt.report)
#                 # Ensure it's a dict, not a list
#                 if isinstance(report_data, list):
#                     report_data = {"components": report_data}
#             except json.JSONDecodeError:
#                 report_data = None
        
#         agent_state = AgentState(
#             intent_messages=json.loads(lt.intent_messages) if lt.intent_messages else [],
#             kpi_messages=json.loads(lt.kpi_messages) if lt.kpi_messages else [],
#             additional_detail_messages=json.loads(lt.additional_detail_messages) if lt.additional_detail_messages else [],
#             structure_messages=json.loads(lt.structure_messages) if lt.structure_messages else [],
#             report_messages=json.loads(lt.report_messages) if lt.report_messages else [],
#             kpis=json.loads(lt.kpis) if lt.kpis else None,
#             structure=json.loads(lt.structure) if lt.structure else None,
#             build_type=lt.build_type,
#             initial_query=lt.initial_query,
#             intent=lt.intent,
#             report=report_data,  # FIX: Use parsed report_data
#             completed_steps=json.loads(lt.completed_steps) if lt.completed_steps else [],
#             additional_details=json.loads(lt.additional_details) if lt.additional_details else None
#         )
#     else:
#         agent_state = AgentState()

#     report_chat = ReportChat(
#         dbname=payload.dbname,
#         llm=llm,
#         llm_name=llm_name,
#         agent_state=agent_state
#     )

#     # ENHANCED: Pass skip_intent to workflow
#     resp = await report_chat.workflow_agent(
#         query=payload.query,
#         skip_intent=skip_intent  # NEW PARAMETER
#     )

#     if not resp:
#         raise HTTPException(detail="Failed to generate response", status_code=500)

#     # FIX: Parse JSON string to dict
#     if isinstance(resp, str):
#         try:
#             resp = json.loads(resp)
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse workflow response: {str(e)}")
#             raise HTTPException(detail="Invalid response format from workflow", status_code=500)

#     # Persist state and transaction
#     report_transactions_details = await i_data.add_report_workflow_transaction({
#         "report_id": payload.report_id,
#         "chat_id": payload.chat_id,
#         "query": payload.query,
#         "text_output": resp.get("response") if resp else None,
#         "options": json.dumps(resp.get("options")) if resp else None,
#         "intent_messages": json.dumps(report_chat.agent_state.intent_messages, default=json_serial) if report_chat.agent_state.intent_messages else None,
#         "kpi_messages": json.dumps(report_chat.agent_state.kpi_messages, default=json_serial) if report_chat.agent_state.kpi_messages else None,
#         "additional_detail_messages": json.dumps(report_chat.agent_state.additional_detail_messages, default=json_serial) if report_chat.agent_state.additional_detail_messages else None,
#         "structure_messages": json.dumps(report_chat.agent_state.structure_messages, default=json_serial) if report_chat.agent_state.structure_messages else None,
#         "report_messages": json.dumps(report_chat.agent_state.report_messages, default=json_serial) if report_chat.agent_state.report_messages else None,
#         "kpis": json.dumps(report_chat.agent_state.kpis, default=json_serial) if report_chat.agent_state.kpis else None,
#         "structure": json.dumps(report_chat.agent_state.structure, default=json_serial) if report_chat.agent_state.structure else None,
#         "build_type": report_chat.agent_state.build_type,
#         "initial_query": report_chat.agent_state.initial_query,
#         "intent": report_chat.agent_state.intent,
#         "report": json.dumps(report_chat.agent_state.report, default=json_serial) if report_chat.agent_state.report else None,
#         "completed_steps": json.dumps(report_chat.agent_state.completed_steps),
#         "additional_details": json.dumps(report_chat.agent_state.additional_details, default=json_serial) if report_chat.agent_state.additional_details else None
#     })

#     # await i_data.add_llm_usage(
#     #     report_transactions_details.id,
#     #     api_endpoint="report_workflow",
#     #     llm=llm_name,
#     #     **report_chat.token_usage.model_dump()
#     # )

#     if report_transactions_details:
#         await i_data.add_llm_usage(
#             report_transactions_details.id,
#             api_endpoint="report_workflow",
#             llm=llm_name,
#             **report_chat.token_usage.model_dump()
#         )
#     else:
#         logger.warning(f"Transaction not saved for chat {payload.chat_id} due to DB error.")

#     return {
#         "text_output": resp.get("response"),
#         "options": resp.get("options"),
#         "state": jsonable_encoder({
#             "kpis": report_chat.agent_state.kpis,
#             "intent": report_chat.agent_state.intent,
#             "report": report_chat.agent_state.report,
#             "structure": report_chat.agent_state.structure,
#             "contextual_scope": report_chat.agent_state.additional_details,
#             "completed_steps": report_chat.agent_state.completed_steps
#         }),
#         "next_action": resp.get("next_action", "waiting_for_approval")
#     }

@router.post(f'/reports/generate-report-chat', status_code=200)
async def generate_report_through_chat(
    payload: ReportGeneration,
    session: AsyncSession = Depends(get_db_async)
):
    """
    Enhanced endpoint with insights modification support.
    """
    # redis_client = get_redis_client()
    redis_client = get_caching_client 
    i_data = InternalSQLHelper(session)

    # 1. DYNAMIC CLIENT POOL FETCHING (REQUIRED FOR NEW ARCHITECTURE)
    fetched_details = await i_data.get_dataset_and_connection_details(db_name=payload.dbname)
    if not fetched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB Connection not found") 
    db_details, connection_details = fetched_details
    client_pool = await get_pool(db_details, connection_details)

    vector_client_raw = await get_vector_client()
    vector_db = VectorStore(vector_client_raw)
    await vector_db.ensure_collection(data.dbname)


    chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
    if not chat_details:
        raise HTTPException(detail="Chat not found", status_code=404)
    
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    # Retrieve previous report history
    report_workflow_transactions = await i_data.get_report_history(payload.chat_id)
    
    # Reconstruct agent state from DB
    if report_workflow_transactions:
        lt = report_workflow_transactions[-1]
        
        # Parse report - handle both dict and list cases
        report_data = None
        if lt.report:
            try:
                report_data = json.loads(lt.report)
                if isinstance(report_data, list):
                    report_data = {"sections": report_data}
            except json.JSONDecodeError:
                report_data = None
        
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
            report=report_data,
            completed_steps=json.loads(lt.completed_steps) if lt.completed_steps else [],
            additional_details=json.loads(lt.additional_details) if lt.additional_details else None
        )
    else:
        agent_state = AgentState()

    report_chat = ReportChat(
        dbname=payload.dbname,
        llm=llm,
        llm_name=llm_name,
        agent_state=agent_state,
        vector_client=vector_db
        # vector_client=vector_client.get_vector_db()
    )

    # ===== DETECT INSIGHTS REQUEST =====
    query_lower = payload.query.lower()
    is_insights_request = any(x in query_lower for x in [
        "add insights", "insights", "analysis", "enhance", "add analysis"
    ])

    # ===== INSIGHTS MODIFICATION HANDLER =====
    if is_insights_request and agent_state.report:
        logger.info(f"Insights modification request: {payload.query}")
        
        resp = await report_chat.add_insights_to_component(query=payload.query)
        
        if isinstance(resp, str):
            try:
                resp = json.loads(resp)
            except json.JSONDecodeError:
                resp = {"response": resp, "status": "success"}

        if resp.get("status") in ["success"]:
            # ===== PERSIST UPDATED REPORT WITH INSIGHTS =====
            await i_data.add_report_workflow_transaction({
                "report_id": payload.report_id,
                "chat_id": payload.chat_id,
                "query": payload.query,
                "text_output": resp.get("response"),
                "options": json.dumps({"component_updated": resp.get("component_id")}),
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
                "completed_steps": json.dumps(report_chat.agent_state.completed_steps),
                "additional_details": json.dumps(report_chat.agent_state.additional_details, default=json_serial) if report_chat.agent_state.additional_details else None
            })

            logger.info(f"Report updated with insights for component: {resp.get('component_id')}")

            return {
                "text_output": resp.get("response"),
                "status": "insights_added",
                "component_id": resp.get("component_id"),
                "component_title": resp.get("component_title"),
                "state": jsonable_encoder({
                    "kpis": report_chat.agent_state.kpis,
                    "intent": report_chat.agent_state.intent,
                    "report": report_chat.agent_state.report,
                    "structure": report_chat.agent_state.structure,
                    "contextual_scope": report_chat.agent_state.additional_details,
                    "completed_steps": report_chat.agent_state.completed_steps
                }),
                "next_action": "insights_added"
            }
        else:
            # Component not found - return helpful message with available components
            return {
                "text_output": resp.get("error") or "Could not find the specified component.",
                "status": "component_not_found",
                "available_components": resp.get("available_components", []),
                "suggestion": resp.get("suggestion", "Please specify which component to add insights to."),
                "next_action": "needs_clarification"
            }

    # ===== ORIGINAL WORKFLOW (unchanged) =====
    skip_intent = detect_skip_intent(payload.query)

    resp = await report_chat.workflow_agent(
        query=payload.query,
        client_pool=client_pool,
        skip_intent=skip_intent
    )

    if not resp:
        raise HTTPException(detail="Failed to generate response", status_code=500)

    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse workflow response: {str(e)}")
            raise HTTPException(detail="Invalid response format from workflow", status_code=500)

    # Persist state and transaction
    report_transactions_details = await i_data.add_report_workflow_transaction({
        "report_id": payload.report_id,
        "chat_id": payload.chat_id,
        "query": payload.query,
        "text_output": resp.get("response") if resp else None,
        "options": json.dumps(resp.get("options")) if resp else None,
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
        "completed_steps": json.dumps(report_chat.agent_state.completed_steps),
        "additional_details": json.dumps(report_chat.agent_state.additional_details, default=json_serial) if report_chat.agent_state.additional_details else None
    })

    if report_transactions_details:
        await i_data.add_llm_usage(
            report_transactions_details.id,
            api_endpoint="report_workflow",
            llm=llm_name,
            **report_chat.token_usage.model_dump()
        )

    return {
        "text_output": resp.get("response"),
        "options": resp.get("options"),
        "state": jsonable_encoder({
            "kpis": report_chat.agent_state.kpis,
            "intent": report_chat.agent_state.intent,
            "report": report_chat.agent_state.report,
            "structure": report_chat.agent_state.structure,
            "contextual_scope": report_chat.agent_state.additional_details,
            "completed_steps": report_chat.agent_state.completed_steps
        }),
        "next_action": resp.get("next_action", "waiting_for_approval")
    }