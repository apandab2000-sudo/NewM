from fastapi import APIRouter, Depends, HTTPException
from app.models import ReportConversation, ReportGeneration, ReportSelectable
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
from app.core.report_builder.report_component import ReportChat
from typing import List, Optional

VERSION = "v1"

router = APIRouter(prefix=f"/egai/report_builder/{VERSION}", tags=["Report Builder"])

logger = get_logger()


def is_proceed_query(query: str) -> bool:
    if not query: return False
    query = query.lower().strip()
    proceed_keywords = ["proceed", "next", "confirm", "looks good", "perfect", "move on", "ok", "okay", "yes"]
    return any(keyword == word for keyword in proceed_keywords for word in query.split())

def merge_selectables(category, user_input_selectables, ai_extracted, ai_suggested):
    user_state = {}
    for s in user_input_selectables:
        field = s.get('field') if isinstance(s, dict) else s.field
        option = s.get('option') if isinstance(s, dict) else s.option
        is_sel = s.get('is_selected') if isinstance(s, dict) else s.is_selected
        if field == category:
            user_state[option] = is_sel
    
    final_map = {}
    for item in ai_extracted:
        final_map[item] = {"field": category, "option": item, "is_selected": True}
    for item in ai_suggested:
        if item not in final_map:
            final_map[item] = {"field": category, "option": item, "is_selected": user_state.get(item, False)}
    for option, is_sel in user_state.items():
        if option not in final_map:
            final_map[option] = {"field": category, "option": option, "is_selected": is_sel}
    return list(final_map.values())


def get_last_successful_intent(transactions):
    if not transactions: return ""
    for t in transactions:
        try:
            raw = json.loads(t.raw_response)
            if "intent_identification" in raw:
                return raw["intent_identification"].get("intent", "")
            if "response" in raw:
                return raw["response"].get("intent", "")
        except: continue
    return ""


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



async def run_step_1(
        i_data:InternalSQLHelper, llm_name: str, chat_id: str,  
        report_chat: ReportChat, query: str | None, 
        selectables: Optional[List[ReportSelectable]] = None, 
        chat_history: list = []
    ):
    
    raw_user_input = {"query": query}
    user_input = f"User Query: {query}"

    intent_details = await report_chat.identify_intent(user_input)
    print(intent_details)
    if not intent_details:
        await i_data.add_llm_usage(
            api_endpoint="report_chat_transaction", 
            llm=llm_name,
            **report_chat.token_usage.model_dump()
        )
        raise HTTPException(detail="Intent identification failed", status_code=400)
    if not intent_details["intent_identified"]: # Intent is not clear and requires clarification from user
        raw_response = { "intent_identification": intent_details["response"]}
        
        transaction_output = {
            "followup_question": intent_details["response"]["followup_question"],
            "selectables": [
                {   
                    "field": "prompt_suggestions",
                    "option": k, 
                    "is_selected": False
                } 
                for k in intent_details["response"]["suggested_query"]
            ]
        }

        report_transaction_details = await i_data.add_report_chat_transaction(
            {
                "chat_id": chat_id,
                "raw_response": json.dumps(raw_response),
                "user_prompted_back": True,
                "step_at": 0,
                "user_input": json.dumps(raw_user_input),
                "transaction_output": json.dumps(transaction_output)
            }
        )

        await i_data.add_llm_usage(
            transaction_id=report_transaction_details.id,
            api_endpoint="report_chat_transaction", 
            llm=llm_name,
            **report_chat.token_usage.model_dump()
        )
        return {
            "report_transactions_id": report_transaction_details.id,
            "followup_question": intent_details["response"]["followup_question"],
            "selectables": [
                {   
                    "field": "prompt_suggestions",
                    "option": k, 
                    "is_selected": False
                } 
                for k in intent_details["response"]["suggested_query"]
            ],
            "report_metadata": intent_details,
            "component_details": []
        }
    
    else: # Intent is clear and now validaiting or generating business_scopes metrics and kpis
        user_input = user_input+f'\nAnalytical Details: {intent_details["response"]}'
        kpi_details = await report_chat.kpi_verification(user_input)

        raw_response = {"intent_identification": intent_details["response"], "kpi_verification": kpi_details}

        # Kpis and metrics extracted while intent identification
        kpi_selectables = [
            {"field": "kpis",  "option": i, "is_selected": True} for i in kpi_details["validated_kpis"]
        ]

        kpi_selectables_suggested = [
            {"field": "kpis",  "option": i, "is_selected": False} for i in kpi_details["suggested_kpis"]
        ]

        transaction_output = {
            "followup_question": kpi_details["followup_question"],
            "selectables": kpi_selectables+kpi_selectables_suggested,
        }
        
        report_transaction_details = await i_data.add_report_chat_transaction(
            {
                "chat_id": chat_id,
                "raw_response": json.dumps(raw_response),
                "user_prompted_back": True,
                "step_at": 1,
                "user_input": json.dumps(raw_user_input),
                "transaction_output": json.dumps(transaction_output),
                "type": intent_details["response"]["dashboard_or_report"]
            }
        )
        # print(report_transaction_details.id)
        
        await i_data.add_llm_usage(
            transaction_id=report_transaction_details.id,
            api_endpoint="report_chat_transaction", 
            llm=llm_name,
            **report_chat.token_usage.model_dump()
        )

        return {
            "report_transactions_id": report_transaction_details.id,
            "question_to_user": kpi_details["followup_question"],
            "selectables": kpi_selectables+kpi_selectables_suggested,
            "report_metadata": intent_details,
            "component_details": []
        }
#########################################


async def handle_conversational_step(i_data, llm_name, payload, report_chat, transactions):
    query = (payload.query or "").strip()
    user_selectables = payload.selectables or []
    
    # 0. RESOLVE CONTEXT
    last_transaction = transactions[0] if transactions else None
    last_step = last_transaction.step_at if last_transaction else 1
    current_step = 1 if last_step == 0 else last_step
    
    cached_intent = get_last_successful_intent(transactions)

    # 1. STEP 1: KPI REFINEMENT
    if current_step == 1:
        # Check for immediate jump via keyword or button
        if is_proceed_query(query) or payload.confirm:
            if not cached_intent: # Fallback to identify intent if history is empty
                intent_res = await report_chat.identify_intent(query, get_chat_history(transactions))
                cached_intent = intent_res.get("response", {}).get("intent", "")
            
            return await handle_step_2_logic(i_data, llm_name, payload, report_chat, transactions, user_selectables, is_jump=True)

        # Standard Intent and KPI check
        intent_str = cached_intent
        if query:
            intent_res = await report_chat.identify_intent(query, get_chat_history(transactions))
            if not intent_res.get("intent_identified", True):
                if not cached_intent:
                    selectables = [{"field": "prompt_suggestions", "option": k, "is_selected": False} 
                                  for k in intent_res["response"].get("suggested_query", [])]
                    return await format_step_response(i_data, payload, intent_res, selectables, 0, llm_name, report_chat)
            intent_str = intent_res.get("response", {}).get("intent", cached_intent)

        existing_kpis = [s.option for s in user_selectables if s.field == "kpis" and s.is_selected]
        kpi_res = await report_chat.kpi_verification(query, get_chat_history(transactions), intent_str, existing_kpis)
        
        merged_kpis = merge_selectables("kpis", user_selectables, kpi_res.get("validated_kpis", []), kpi_res.get("suggested_kpis", []))

        # Check if LLM sensed natural confirmation
        if kpi_res.get("status") == "confirmed":
            return await handle_step_2_logic(i_data, llm_name, payload, report_chat, transactions, merged_kpis, is_jump=True)
        
        full_res = {"intent_identification": {"intent": intent_str}, "kpi_verification": kpi_res}
        return await format_step_response(i_data, payload, full_res, merged_kpis, 1, llm_name, report_chat)

    # 2. STEP 2: DIMENSIONS & TIME GRAIN
    elif current_step == 2:
        return await handle_step_2_logic(i_data, llm_name, payload, report_chat, transactions, user_selectables, is_jump=False)

    # 3. STEP 3: QUESTIONS
    elif current_step == 3:
        return await handle_step_3_logic(i_data, llm_name, payload, report_chat, transactions, user_selectables, is_jump=False)

    else:
        return {"status": "complete", "final_configuration": payload.selectables, "step": 4}

async def handle_step_2_logic(i_data, llm_name, payload, report_chat, transactions, current_selectables, is_jump=False):
    query = payload.query or ""
    
    # Context for LLM
    kpis = [s.get('option') if isinstance(s, dict) else s.option for s in current_selectables if (s.get('field') if isinstance(s, dict) else s.field) == "kpis" and (s.get('is_selected') if isinstance(s, dict) else s.is_selected)]
    existing_dims = [s.get('option') if isinstance(s, dict) else s.option for s in current_selectables if (s.get('field') if isinstance(s, dict) else s.field) in ["dimensions", "time_grain"] and (s.get('is_selected') if isinstance(s, dict) else s.is_selected)]
    
    dim_res = await report_chat.dimension_verification(query, kpis, ", ".join(existing_dims), get_chat_history(transactions))
    
    # Transition Logic: Stop if is_jump=True (Arriving from Step 1)
    if not is_jump:
        if payload.confirm or is_proceed_query(query) or dim_res.get("status") == "confirmed":
            return await handle_step_3_logic(i_data, llm_name, payload, report_chat, transactions, current_selectables, is_jump=True)

    # UI Construction
    kpi_selects = [s if isinstance(s, dict) else s.model_dump() for s in current_selectables if (s.get('field') if isinstance(s, dict) else s.field) == "kpis"]
    dims = merge_selectables("dimensions", current_selectables, dim_res["response"].get("dimensions", {}).get("extracted", []), dim_res["response"].get("dimensions", {}).get("suggested", []))
    times = merge_selectables("time_grain", current_selectables, dim_res["response"].get("time_grain", {}).get("extracted", []), dim_res["response"].get("time_grain", {}).get("suggested", []))
    
    return await format_step_response(i_data, payload, dim_res, kpi_selects + dims + times, 2, llm_name, report_chat)

async def handle_step_3_logic(i_data, llm_name, payload, report_chat, transactions, current_selectables, is_jump=False):
    kpis = [s.get('option') if isinstance(s, dict) else s.option for s in current_selectables if (s.get('field') if isinstance(s, dict) else s.field) == "kpis" and (s.get('is_selected') if isinstance(s, dict) else s.is_selected)]
    dims = [s.get('option') if isinstance(s, dict) else s.option for s in current_selectables if (s.get('field') if isinstance(s, dict) else s.field) == "dimensions" and (s.get('is_selected') if isinstance(s, dict) else s.is_selected)]
    
    q_res = await report_chat.generate_questions(f"KPIs: {kpis}. Dimensions: {dims}.")
    
    if payload.confirm and not is_jump:
        return {"status": "complete", "final_configuration": current_selectables, "step": 4, "question_to_user": "Configuration finalized."}

    question_selectables = [{"field": "report_questions", "option": q, "is_selected": True} for q in q_res.get("questions", [])]
    return await format_step_response(i_data, payload, q_res, question_selectables, 3, llm_name, report_chat)


async def format_step_response(i_data, payload, results, selectables, step_at, llm_name, report_chat):
    # Try to find the question in various common locations
    followup = results.get("followup_question")
    
    # If not found at top level, check inside "response" (Step 0)
    if not followup and "response" in results:
        followup = results["response"].get("followup_question")
        
    # If not found, check inside "kpi_verification" (Step 1)
    if not followup and "kpi_verification" in results:
        followup = results["kpi_verification"].get("followup_question")

    # If still not found, check inside "dimension_verification" (Step 2)
    if not followup and "dimension_verification" in results:
        followup = results["dimension_verification"].get("followup_question")

    transaction_output = {
        "followup_question": followup,
        "selectables": selectables
    }
    
    # Save to DB
    report_transaction_details = await i_data.add_report_chat_transaction({
        "chat_id": payload.chat_id,
        "raw_response": json.dumps(results),
        "step_at": step_at,
        "user_input": json.dumps({"query": payload.query}),
        "transaction_output": json.dumps(transaction_output)
    })

    # Track Usage
    await i_data.add_llm_usage(
        transaction_id=report_transaction_details.id,
        api_endpoint="report_chat_transaction", 
        llm=llm_name,
        **report_chat.token_usage.model_dump()
    )

    return {
        "report_transactions_id": report_transaction_details.id,
        "question_to_user": followup, # This will now be correctly populated
        "selectables": selectables,
        "step": step_at
    }

########################################
################ original get_chat_history function ############
# def get_chat_history(report_chat_transactions):
#     chat_history = []

#     for i in report_chat_transactions[:3]:
#         if i.step_at==0:
#             print(json.loads(i.user_input))
#             print(json.loads(i.transaction_output))

#             chat_history.append({"role": "user", "content": json.loads(i.user_input)["query"]})
#             chat_history.append({"role": "assistant", "content": json.loads(i.transaction_output)["followup_question"]})
#         else:
#             pass
#     return chat_history   

def get_chat_history(report_chat_transactions):
    chat_history = []
    # Only take the last 5 transactions to avoid token bloat
    for i in reversed(report_chat_transactions[:5]):
        try:
            user_input = json.loads(i.user_input).get("query", "").strip()
            # If the last transaction was a failure (Step 0) and we are trying to 
            # recover, don't feed the "failure" back into the LLM as it causes loops.
            if i.step_at == 0:
                continue 
            
            output = json.loads(i.transaction_output)
            ans = output.get("followup_question", "")

            if user_input:
                chat_history.append({"role": "user", "content": user_input})
            if ans:
                chat_history.append({"role": "assistant", "content": ans})
        except:
            continue
    return chat_history             


################# base version ###########
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

#     report_chat_transactions = await i_data.get_report_chat_transactions(payload.chat_id)

#     token_usage = {
#         "input_tokens": 0,
#         "output_tokens": 0,
#         "cached_tokens": 0
#     }

#     # If not report transactions - Means its the first query added by user in chat
#     report_chat = ReportChat(
#         dbname=payload.dbname,
#         llm=llm, 
#         llm_name=llm_name
#     )

#     # If not report transactions - Means its the first query added by user in chat
#     if not report_chat_transactions:
#         # Step 1 - identifying intent
#         step_1_results = await run_step_1( 
#             i_data = i_data, 
#             llm_name = llm_name, 
#             chat_id = payload.chat_id, 
#             report_chat = report_chat, 
#             selectables=payload.selectables,
#             query = payload.query
#         )
#         return step_1_results
            
#     else:
#         if report_chat_transactions[0].step_at==0: # case of previous question has resulte din failed intent identification
#             chat_history = get_chat_history(report_chat_transactions)
#             print(chat_history)
#             step_1_results = await run_step_1( 
#                 i_data = i_data, 
#                 llm_name = llm_name, 
#                 chat_id = payload.chat_id, 
#                 report_chat = report_chat, 
#                 query = payload.query if payload.query else payload.selectables[0].option,
#                 chat_history=chat_history
#             )
#             return step_1_results

#         if report_chat_transactions[0].step_at==1:
#             pass

#         if report_chat_transactions[0].step_at==2:
#             pass

#         if report_chat_transactions[0].step_at==3:
#             pass

################## working but extracting all at once ##########


# async def run_unified_extraction(
#     i_data: InternalSQLHelper, 
#     llm_name: str, 
#     chat_id: str, 
#     report_chat: ReportChat, 
#     query: str, 
#     user_selectables: List[ReportSelectable] = [], 
#     step_at: int = 1
# ):
#     """
#     Unified step to extract KPIs, Dimensions, and Time Grain.
#     Handles dynamic suggestions by looking at what the user already selected.
#     """
#     # 1. AI Extraction (Uses the unified prompt)
#     results = await report_chat.identify_intent_and_requirements(query, user_selectables)
    
#     # CASE: Intent is not clear (Ambiguous query)
#     if not results.get("intent_identified", True):
#         transaction_output = {
#             "followup_question": results["response"]["followup_question"],
#             "selectables": [
#                 {"field": "prompt_suggestions", "option": k, "is_selected": False} 
#                 for k in results["response"].get("suggested_query", [])
#             ]
#         }
#         report_transaction_details = await i_data.add_report_chat_transaction({
#             "chat_id": chat_id,
#             "raw_response": json.dumps(results),
#             "step_at": 0,
#             "user_input": json.dumps({"query": query}),
#             "transaction_output": json.dumps(transaction_output)
#         })
        
#         await i_data.add_llm_usage(
#             transaction_id=report_transaction_details.id,
#             api_endpoint="report_chat_transaction", 
#             llm=llm_name,
#             **report_chat.token_usage.model_dump()
#         )
        
#         return {
#             "report_transactions_id": report_transaction_details.id,
#             "followup_question": transaction_output["followup_question"],
#             "selectables": transaction_output["selectables"],
#             "report_metadata": results,
#             "component_details": []
#         }

#     # CASE: Intent Clear -> Process Selection logic
#     def build_selectables(category, ai_data, current_user_selections):
#         # Items user currently has checked in the UI
#         user_checked = [s.option for s in current_user_selections if s.field == category and s.is_selected]
#         # Items AI found in the query
#         ai_extracted = ai_data.get("extracted", [])
#         # Items AI is newly suggesting
#         ai_suggested = ai_data.get("suggested", [])
        
#         all_options = list(set(ai_extracted + ai_suggested + user_checked))
#         res = []
#         for opt in all_options:
#             res.append({
#                 "field": category, "option": opt,
#                 "is_selected": True if (opt in user_checked or opt in ai_extracted) else False
#             })
#         return res

#     new_selectables = (
#         build_selectables("kpis", results["response"]["kpis"], user_selectables) +
#         build_selectables("dimensions", results["response"]["dimensions"], user_selectables) +
#         build_selectables("time_grain", results["response"]["time_grain"], user_selectables)
#     )

#     transaction_output = {
#         "followup_question": results["response"]["followup_question"],
#         "selectables": new_selectables
#     }
    
#     report_transaction_details = await i_data.add_report_chat_transaction({
#         "chat_id": chat_id,
#         "raw_response": json.dumps(results),
#         "user_prompted_back": True,
#         "step_at": step_at,
#         "user_input": json.dumps({"query": query}),
#         "transaction_output": json.dumps(transaction_output)
#     })

#     # Track Token Usage
#     await i_data.add_llm_usage(
#         transaction_id=report_transaction_details.id,
#         api_endpoint="report_chat_transaction", 
#         llm=llm_name,
#         **report_chat.token_usage.model_dump()
#     )

#     return {
#         "report_transactions_id": report_transaction_details.id,
#         "question_to_user": transaction_output["followup_question"],
#         "selectables": new_selectables,
#         "report_metadata": results,
#         "component_details": []
#     }

# @router.post(f'/reports/generate-report-chat', status_code=200)
# async def generate_report_through_chat(
#     payload: ReportGeneration,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     i_data = InternalSQLHelper(session)

#     chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
#     if not chat_details:
#         raise HTTPException(detail="Chat session not found", status_code=404)
    
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     report_chat_transactions = await i_data.get_report_chat_transactions(payload.chat_id)
#     report_chat = ReportChat(dbname=payload.dbname, llm=llm, llm_name=llm_name)

#     # --- NEW: FINAL CONFIRMATION LOGIC ---
#     if payload.confirm:
#         final_config = {
#             "kpis": [s.option for s in payload.selectables if s.field == "kpis" and s.is_selected],
#             "dimensions": [s.option for s in payload.selectables if s.field == "dimensions" and s.is_selected],
#             "time_grains": [s.option for s in payload.selectables if s.field == "time_grain" and s.is_selected]
#         }
        
#         report_transaction_details = await i_data.add_report_chat_transaction({
#             "chat_id": payload.chat_id,
#             "raw_response": json.dumps(final_config),
#             "user_prompted_back": False,
#             "step_at": 3,
#             "user_input": "USER_CONFIRMED",
#             "transaction_output": json.dumps(final_config)
#         })

#         return {
#             "report_transactions_id": report_transaction_details.id,
#             "question_to_user": "Configuration confirmed. I'm now generating your report.",
#             "selectables": [],
#             "report_metadata": {"status": "confirmed", "final_config": final_config},
#             "component_details": []
#         }

#     # --- ORIGINAL FLOW: STEP HANDLING ---
#     if not report_chat_transactions:
#         # First query: Extract everything
#         return await run_unified_extraction(
#             i_data, llm_name, payload.chat_id, report_chat, payload.query, step_at=1
#         )
            
#     else:
#         # Step 0: User is replying to a clarification question
#         if report_chat_transactions[0].step_at == 0:
#             chat_history = get_chat_history(report_chat_transactions)
#             query = payload.query if payload.query else payload.selectables[0].option
#             return await run_unified_extraction(
#                 i_data, llm_name, payload.chat_id, report_chat, query, step_at=1
#             )

#         # Step 1 or 2: Refinement Loop (User updated selectables or typed a new detail)
#         if report_chat_transactions[0].step_at in [1, 2]:
#             # Retrieve the very first query for context if the user didn't type a new refinement
#             original_query = json.loads(report_chat_transactions[-1].user_input).get("query")
#             query = payload.query if payload.query else original_query
            
#             return await run_unified_extraction(
#                 i_data, llm_name, payload.chat_id, report_chat, 
#                 query, user_selectables=payload.selectables, step_at=2
#             )

#         # Step 3: Already confirmed
#         if report_chat_transactions[0].step_at == 3:
#             return {"status_message": "Report configuration already confirmed."}


##################

@router.post(f'/reports/generate-report-chat', status_code=200)
async def generate_report_through_chat(
    payload: ReportGeneration,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    chat_details = await i_data.get_chat_details_from_chatid(payload.chat_id)
    if not chat_details:
        raise HTTPException(detail="Chat session not found", status_code=404)

    # Load Config & LLM
    with open("app/clientConfig.yaml", "r") as f:
        config = yaml.safe_load(f)
    llm_base = config[payload.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = config[payload.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    # Get state from last transaction
    report_chat_transactions = await i_data.get_report_chat_transactions(payload.chat_id)
    # current_step = report_chat_transactions[0].step_at if report_chat_transactions else 1
    
    report_chat = ReportChat(dbname=payload.dbname, llm=llm, llm_name=llm_name)

    # return await handle_conversational_step(i_data, llm_name, payload, report_chat, current_step)
    return await handle_conversational_step(i_data, llm_name, payload, report_chat, report_chat_transactions)