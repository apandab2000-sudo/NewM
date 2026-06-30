from fastapi import APIRouter, Depends, HTTPException
from app.models import ResetChat, ReportChats, ReportId, ReportComponentId, UpdateReport, UpdateReportComponentId, ReportGeneration
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.connections import (
    get_db_async,
    get_nosql_client,
    client_connection_pool,
    get_vector_db
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



router = APIRouter(prefix="/egai", tags=["Report_Builder"])


logger = get_logger()

VERSION = "v1"

def process_username(user_name: str):
    user_name = user_name.strip().lower()
    first_name, last_name = user_name.split(" ")
    email = f"{user_name[0]}.{user_name[1]}@eclerx.com"
    return first_name, last_name, email

@router.post(f'/report_builder/{VERSION}/reports', status_code=200)
async def create_report(
    data: ReportId,
    session: AsyncSession = Depends(get_db_async)
): 
    i_data = InternalSQLHelper(session)
    user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    report_details = await i_data.get_report_details_from_db_id_and_report_name(db_details.id, data.report_name)
    if not report_details:
        logger.debug("Report does not exists")
    
    report_details = await i_data.create_report(
        data.report_name,
        data.report_description,
        user_details.id,
        db_details.id
    )

    if not report_details:
        logger.error("Report neither retreived nor created successfully")
        raise HTTPException(detail="Report neither retreived nor created successfully", status_code=400)

    return {
        "report_id": report_details.id,
        "report_name": report_details.report_name,
        "report_description": report_details.report_description,
        "dbname": data.dbname
    }


@router.get(f'/report_builder/{VERSION}/reports', status_code=200)
async def get_reports(dbname: str, user_name: str, session: AsyncSession = Depends(get_db_async)):
    first_name, last_name, email_id = process_username(user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    reports = await i_data.get_report_details_from_db_id(db_details.id)
    report_dict = [{
        "report_id": r.id,
        "report_name": r.report_name,
        "report_description": r.report_description,
        "dbname": dbname
    } for r in reports]

    return report_dict


@router.get(f'/report_builder/{VERSION}/reports/{{report_id}}', status_code=200)
async def get_particular_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
    first_name, last_name, email_id = process_username(user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(report_id)
    if not report_details:
        raise HTTPException(detail="Report with provided id not found", status_code=404)
    
    return {
        "report_id": report_details.id,
        "report_name": report_details.report_name,
        "report_description": report_details.report_description,
        "dbname": dbname
    }


@router.delete(f'/report_builder/{VERSION}/reports/{{report_id}}', status_code=204)
async def soft_delete_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
    first_name, last_name, email_id = process_username(user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(report_id)
    if not report_details:
        raise HTTPException(detail="Report with provided id not found", status_code=404)
    
    delete_status = await i_data.update_report_data(report_id, {"is_active": False})
    if not delete_status:
        raise HTTPException(detail="Report was deleted successfully", status_code=404)
    return    


@router.put(f'/report_builder/{VERSION}/reports', status_code=201)
async def update_report(
    data: UpdateReport,
    session: AsyncSession = Depends(get_db_async)
): 
    i_data = InternalSQLHelper(session)
    user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(data.report_id)
    if not report_details:
        raise HTTPException(detail="Report with provided id not found", status_code=404)
    
    update_status = await i_data.update_report_data(
        data.report_id, 
        {   
            "is_active": data.is_active,
            "report_name": data.report_name,
            "report_description": data.report_description
        }
    )
    if not update_status:
        raise HTTPException(detail="Report was NOT updated successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(data.report_id)
    
    if not report_details:        
        logger.warning("Report not found after update")
        raise HTTPException(detail="Report not found after update", status_code=404)
    
    return {
        "report_id": report_details.id,
        "report_name": report_details.report_name,
        "report_description": report_details.report_description,
        "dbname": data.dbname
    }


########################### REPORT COMPONENETS #####################################
@router.post(f'/report_builder/{VERSION}/reports/components', status_code=201)
async def create_component(
    data: ReportComponentId,
    session: AsyncSession = Depends(get_db_async)
): 
    i_data = InternalSQLHelper(session)
    user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    report_details = await i_data.get_report_details_from_report_id(data.report_id)
    if not report_details:
        raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
    # component_details = await i_data.get_component_details_from_name_and_report_id(report_details.id, data.component_name)
    # if component_details:
    #     raise HTTPException(detail="Component with same name exists for this report", status_code=400)

    component_details = await i_data.create_report_component(
        report_id=report_details.id,
        component_name=data.component_name,
        component_description=data.component_description,
        component_type=data.component_metadata.component_type if data.component_metadata else None,
        created_by=user_details.id
    )

    component_type = data.component_metadata.component_type if data.component_metadata else None

    if not component_details:
        raise HTTPException(detail="component was not created properly", status_code=400)

    report_transaction_details = await i_data.add_component_into_transactions(
        component_details.id,
        user_details.id,
        table_details=json.dumps(data.component_metadata.model_dump()) if component_type == "table" else None,
        graph_details=json.dumps(data.component_metadata.model_dump()) if component_type == "graph" else None,
        insights_details=json.dumps(data.component_metadata.model_dump()) if component_type == "insights" else None,
    )

    if not report_transaction_details:
        raise HTTPException(detail="component was not added into transactions", status_code=400)
    
    return {
        "component_id": component_details.id,
        "report_id": report_details.id,
        "component_name": component_details.component_name,
        "component_description": component_details.component_description,
        "component_type": component_details.component_type,
        "is_active": component_details.is_active,
        "component_state_id": report_transaction_details.component_state_id,
        "query": report_transaction_details.query,
        "table_details": json.loads(report_transaction_details.table_details) if report_transaction_details.table_details else None,
        "graph_details": json.loads(report_transaction_details.graph_details) if report_transaction_details.graph_details else None,
        "insights_details": json.loads(report_transaction_details.insights_details) if report_transaction_details.insights_details else None
    }


@router.get(f'/report_builder/{VERSION}/reports/{{report_id}}/components', status_code=200)
async def get_all_components_for_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
    first_name, last_name, email_id = process_username(user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    report_details = await i_data.get_report_details_from_report_id(report_id)
    if not report_details:
        raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
    component_details = await i_data.get_component_ids_for_report(report_id)
    if not component_details:
        raise HTTPException(detail="Components not found", status_code=404)
    
    component_list = []

    for c in component_details:
        ct = await i_data.get_component_last_state(component_id=c.id)
        if ct:
            component_list.append(
                    {
                        "component_id": c.id,
                        "report_id": c.report_id,
                        "component_name": c.component_name,
                        "component_description": c.component_description,
                        "component_type": c.component_type,
                        "is_active": c.is_active,
                        "component_state_id": ct.component_state_id,
                        "query": ct.query,
                        "table_details": json.loads(ct.table_details) if ct.table_details else None,
                        "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
                        "insights_details": json.loads(ct.insights_details) if ct.insights_details else None
                    }
                )
        else:
            logger.warning(f"Component_transactions not fecthed properly for compnent_id - {c.id}")

    return component_list


@router.get(f'/report_builder/{VERSION}/reports/components/{{component_id}}', status_code=200)
async def get_particular_component(dbname: str, user_name: str, component_id: int, session: AsyncSession = Depends(get_db_async)):
    first_name, last_name, email_id = process_username(user_name)

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    component_details = await i_data.get_component_details_from_id(component_id)
    if not component_details:
        raise HTTPException(detail="Components not found", status_code=404)
    
    ct = await i_data.get_component_last_state(component_id=component_details.id)
    if not ct:
        logger.error("Component Not found in transactions")
        raise HTTPException(detail="Component Not found in transactions", status_code=404)

    return {
        "component_id": component_details.id,
        "report_id": component_details.report_id,
        "component_name": component_details.component_name,
        "component_description": component_details.component_description,
        "component_type": component_details.component_type,
        "is_active": component_details.is_active,
        "component_state_id": ct.component_state_id,
        "query": ct.query,
        "table_details": json.loads(ct.table_details) if ct.table_details else None,
        "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
        "insights_details": json.loads(ct.insights_details) if ct.insights_details else None
    }


@router.post(f'/report_builder/{VERSION}/reports/components/update', status_code=200)
async def update_report_component(
    data: UpdateReportComponentId,
    session: AsyncSession = Depends(get_db_async)
):
    client_pool = client_connection_pool
    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    report_details = await i_data.get_report_details_from_report_id(data.report_id)
    if not report_details:
        raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
    component_details = await i_data.get_component_details_from_id(data.component_id)
    if not component_details:
        raise HTTPException(detail="COmponent does not exists nor created successfully", status_code=404)
  
    if not data.query and not data.component_metadata:
        raise HTTPException(detail="No details found to update component", status_code=404)
    
    if data.component_metadata:
        if data.component_metadata.component_type != component_details.component_type:
            raise HTTPException(detail="Cannot modify the type of component", status_code=400)

    comp_id = component_details.id
    comp_type = component_details.component_type
    comp_name_original = component_details.component_name
    
    if data.component_metadata and data.component_metadata.component_type != comp_type:
        raise HTTPException(detail="Cannot modify the type of component", status_code=400)


    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    vector_connection = get_vector_db()
    vector_client = VectorStore(vector_connection)
    await vector_client.ensure_collection(data.dbname)

    component_last_state = await i_data.get_component_last_state(data.component_id)
    rc_helper = ReportComponent(dbname=data.dbname, llm=llm, llm_name=llm_name)

    route_info = await rc_helper.extract_possible_routes(data.query)

    if comp_type == "paragraph":
        if not data.query:
            raise HTTPException(detail="Query required for Paragraph", status_code=400)

        # 1. Check if SQL is needed context
        para_meta = route_info.get("paragraph") or {}
        para_meta_data = para_meta.get("metadata") or {}
        sql_question = para_meta_data.get("sql_question")

        table_json = None
        sql_query = None

        if sql_question:
            t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=sql_question, filters="")
            # t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=data.query, filters="")

            resp = await t2s.sql_query_generator_basic()
            if resp and resp.get("status") == "complete":
                sql_query = resp["response"][0]["sql_query"]
                table_details = await get_table_from_sql(client_pool, sql_query)
                table_json, table_status, _ = get_table_and_status_and_columns(table_details)

        # 2. Generate Narrative Text
        # LLM uses the original query + any fetched table data to write the paragraph
        paragraph_text = await rc_helper.generate_paragraph_text(
            objective=data.query,
            table_data=table_json,
            word_limit=para_meta_data.get("word_limit", 200)
        )
        
        await i_data.add_llm_usage(api_endpoint="paragraph_gen", llm=llm_name, **rc_helper.token_usage.model_dump())

        # 3. Dynamic Title
        dynamic_title, _ = await generate_graph_title(data.query, pd.DataFrame(), data.dbname, llm, llm_name)

        # 4. Save and Return
        await i_data.add_component_into_transactions(
            component_id=comp_id, modified_by=user_details.id, query=data.query,
            component_state_id=component_last_state.component_state_id + 1,
            table_details=json.dumps({"paragraph": paragraph_text}) 
        )

        return {
            "component_id": comp_id,
            "component_type": "paragraph",
            "component_output": {
                "sql": sql_query,
                "paragraph": paragraph_text,
                "title": dynamic_title or "Executive Summary"
            }
        }

    elif comp_type == "smartart":
        if not data.query:
            raise HTTPException(detail="Query required for SmartArt", status_code=400)

        smartart_data_raw = route_info.get("smartart") or {}
        smartart_meta = smartart_data_raw.get("metadata") or {}
        
        llm_suggested_style = smartart_meta.get("style", "list")

        manual_style = None
        if data.component_metadata and data.component_metadata.component_type == "smartart":
            manual_style = data.component_metadata.style

        # Priority: Manual User Selection (from component_metadata) > LLM Suggestion > Default
        final_style = manual_style or llm_suggested_style or "list"


        # # A. SQL Generation
        t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=data.query, filters="")
        resp = await t2s.sql_query_generator_basic()
        
        if not resp:
            raise HTTPException(detail="Text 2 SQL failed", status_code=400)
        
        if resp.get("status") == "awaiting_human_input":
            return {"component_id": data.component_id, "status": "awaiting_human_input", "message": resp.get("response")}

        sql_query = resp["response"][0]["sql_query"]
        
        # B. Data Fetching
        table_details = await get_table_from_sql(client_pool, sql_query)
        table_json, table_status, _ = get_table_and_status_and_columns(table_details)

        if table_status != "success":
            raise HTTPException(detail=f"Database error: {table_details.error}", status_code=400)


        # C. Dynamic Title Generation
        df_temp = pd.DataFrame(table_json)
        dynamic_title, token_usage = await generate_graph_title(
            user_query=data.query, df=df_temp, db_name=data.dbname, llm=llm, llm_model=llm_name
        )
        await i_data.add_llm_usage(api_endpoint="smartart_title", llm=llm_name, **token_usage.model_dump())

        # D. Process Logic
        # Style comes from metadata (decided by LLM in route step) or defaults to 'list'
        # req_style = getattr(data.component_metadata, 'style', 'list')
        
        smartart_data = rc_helper._process_smartart_logic(
            table_json, 
            title=dynamic_title or comp_name_original or "Information", 
            style=final_style
        )

        await i_data.add_component_into_transactions(
            component_id=comp_id, modified_by=user_details.id, query=data.query,
            component_state_id=component_last_state.component_state_id + 1,
            table_details=json.dumps(table_json) 
        )

        return {
            "component_id": comp_id,
            "component_type": "smartart",
            "component_output": {"sql": sql_query, 
            "table": table_json, 
            "smartart": smartart_data}
        }

    # elif comp_type == "header":
    #     # 1. FETCH CONTEXT: Get the report name and description from SQL
    #     # Use the report_details we fetched at the start of the function
    #     report_name = report_details.report_name
    #     report_description = report_details.report_description

    #     # 2. Generate Header Content
    #     header_data = await rc_helper.generate_header_data(
    #         report_name=report_name,
    #         report_desc=report_description,
    #         user_query=data.query # The latest user instruction
    #     )
        
    #     # 3. Save State
    #     await i_data.add_component_into_transactions(
    #         component_id=comp_id, 
    #         modified_by=user_details.id, 
    #         query=data.query,
    #         component_state_id=component_last_state.component_state_id + 1,
    #         table_details=json.dumps(header_data) 
    #     )

    #     return {
    #         "component_id": comp_id,
    #         "component_type": "header",
    #         "component_output": {
    #             "header": header_data # Contains title, subtitle, context
    #         }
    #     }


    elif comp_type == "header":
        # 1. Fetch all components for this report
        existing_components = await i_data.get_component_ids_for_report(data.report_id)
        
        # 2. Extract detailed logic (Natural Language + SQL) for each component
        detailed_context_list = []
        for c in existing_components:
            if c.id == comp_id: # Skip the header itself
                continue
            
            # Fetch the last state (contains the NL query and SQL details)
            last_state = await i_data.get_component_last_state(component_id=c.id)
            
            if last_state:
                # Try to extract the actual SQL from metadata columns
                # This depends on which detail column was used during creation
                raw_metadata = (
                    last_state.table_details or 
                    last_state.graph_details or 
                    last_state.insights_details
                )
                
                actual_sql = "No SQL available"
                if raw_metadata:
                    try:
                        meta_dict = json.loads(raw_metadata)
                        actual_sql = meta_dict.get("sql", "No SQL available")
                    except: pass

                detailed_context_list.append(
                    f"Component: {c.component_name or 'Untitled'}\n"
                    f"- Type: {c.component_type}\n"
                    f"- User Asked: {last_state.query}\n"
                    f"- Database Logic (SQL): {actual_sql}\n"
                )

                print(detailed_context_list)

                        

        # final_content_context = "\n".join(detailed_context_list) if detailed_context_list else "No existing data components."


        # 3. FALLBACK LOGIC: Determine the "Context of Truth"
        if detailed_context_list:
            # Scenario A: We have data components to summarize
            final_content_context = "REPORT CONTENT:\n" + "\n".join(detailed_context_list)
        else:
            # Scenario B: New Report. Check Report Metadata first, then User Query
            db_name = report_details.report_name
            db_desc = report_details.report_description
            
            # Filter out generic placeholder values like "string" or "None"
            # has_name = db_name and db_name.lower() not in ["string", "none", "untitled"]
            has_desc = db_desc and db_desc.lower() not in ["string", "none", "untitled"]

            if has_name or has_desc:
                final_content_context = (
                    "This is a new report with no data components yet. Use the following report settings:\n"
                    # f"Report Name: {db_name if has_name else 'Unnamed'}\n"
                    f"Report Goal: {db_desc if has_desc else 'Not specified'}"
                )
            else:
                # Scenario C: Completely fresh report, use current query and DB name
                final_content_context = (
                    "This is a fresh report with no metadata. Base the header on the user's query and dataset.\n"
                    # f"Current Dataset: {data.dbname}\n"
                    f"Current User Query: {data.query}"
                )
        # 3. Generate Header with Deep Context
        header_data = await rc_helper.generate_header_data(
            report_name=report_details.report_name,
            report_desc=report_details.report_description,
            user_query=data.query,
            content_context=final_content_context
        )
        # 4. Save Transaction (using local comp_id)
        await i_data.add_component_into_transactions(
            component_id=comp_id, 
            modified_by=user_details.id, 
            query=data.query,
            component_state_id=component_last_state.component_state_id + 1,
            table_details=json.dumps(header_data) 
        )

        return {
            "component_id": comp_id,
            "component_type": "header",
            "component_output": {
                "header": header_data
            }
        }

    elif comp_type == "list":
        if not data.query:
            raise HTTPException(detail="Query required", status_code=400)

        # 1. Get dynamic SQL instruction from Router (route_info)
        list_meta = route_info.get("list", {}).get("metadata") or {}
        sql_q = list_meta.get("sql_question") or data.query

        # 2. SQL Fetching
        t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=sql_q, filters="")
        resp = await t2s.sql_query_generator_basic()
        
        if not resp: raise HTTPException(detail="Text 2 SQL failed", status_code=400)
        if resp.get("status") == "awaiting_human_input":
            return {"component_id": comp_id, "status": "awaiting_human_input", "message": resp.get("response")}

        sql_query = resp["response"][0]["sql_query"]
        table_details = await get_table_from_sql(client_pool, sql_query)
        table_json, table_status, _ = get_table_and_status_and_columns(table_details)

        if table_status != "success":
            raise HTTPException(detail=f"DB Error: {table_details.error}", status_code=400)

        # 3. Dynamic Title Generation
        df_temp = pd.DataFrame(table_json)
        dynamic_title, title_tokens = await generate_graph_title(data.query, df_temp, data.dbname, llm, llm_name)
        await i_data.add_llm_usage(api_endpoint="list_title", llm=llm_name, **title_tokens.model_dump())

        # 4. UNIFIED LOGIC: Let the LLM "Decode" if it's a simple list or reasoning points
        # One function call regardless of the query type.
        list_data = await rc_helper.generate_list_component_items(
            user_query=data.query,
            table_data=table_json,
            title=dynamic_title or comp_name_original or "List Overview"
        )
        
        await i_data.add_llm_usage(api_endpoint="list_generation", llm=llm_name, **rc_helper.token_usage.model_dump())

        # 5. Save Transaction
        await i_data.add_component_into_transactions(
            component_id=comp_id, 
            modified_by=user_details.id, 
            query=data.query,
            component_state_id=component_last_state.component_state_id + 1,
            table_details=json.dumps(table_json) 
        )

        return {
            "component_id": comp_id,
            "component_type": "list",
            "component_output": {
                "sql": sql_query,
                "table": table_json,
                "list": list_data 
            }
        }

    elif component_details.component_type in ["kpi_card", "metric_grid"]:
        if data.query:

            indicator_meta = route_info.get("indicator", {}).get("metadata", {})
            if not indicator_meta: # Fallback if LLM uses legacy keys
                indicator_meta = route_info.get(comp_type, {}).get("metadata", {})
                
            sql_question = indicator_meta.get("sql_question", data.query)
            include_trends = indicator_meta.get("include_trends", False)
            
            t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=sql_question, filters="")
            
            # t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=data.query, filters="")
            resp = await t2s.sql_query_generator_basic()
            if not resp or resp.get("status") == "awaiting_human_input":
                raise HTTPException(detail="Failed to generate SQL", status_code=400)
            if resp.get("status") == "awaiting_human_input":
                return {
                    "component_id": data.component_id,
                    "status": "awaiting_human_input",
                    "message": resp.get("response"),
                    "component_output": None
                }
####################################
            sql_query = resp["response"][0]["sql_query"]
            table_details = await get_table_from_sql(client_pool, sql_query)
            table_json, table_status, _ = get_table_and_status_and_columns(table_details)

###########################
            if table_status != "success":
                logger.error(f"KPI SQL failed: {table_details.error}")
                raise HTTPException(
                    detail=f"Database error: {table_details.error}. Please try rephrasing your question.", 
                    status_code=400
                )
            if not table_json:
                 raise HTTPException(detail="No data found for the given criteria.", status_code=404)
#############################
        else:
            raise HTTPException(detail="Query required for KPI components", status_code=400)

        # # Save the state
        # ct = await i_data.add_component_into_transactions(
        #     component_id=component_details.id,
        #     modified_by=user_details.id,
        #     query=data.query,
        #     component_state_id=component_last_state.component_state_id+1,
        #     table_details=json.dumps(data.component_metadata.model_dump()) # Store as table metadata
        # )

        # # 2. Once you have table_json, process it:
        # if component_details.component_type == "kpi_card":
        #     output = {"indicator": rc_helper._process_kpi_logic(table_json, component_details.component_name)}
        # else:
        #     df_grid = pd.DataFrame(table_json)
        #     num_cols = df_grid.select_dtypes(include=['number']).columns.tolist()
        #     output = {"metric_grid": [rc_helper._process_kpi_logic(df_grid[[col]].to_dict('records'), col) for col in num_cols]}

        # return {
        #     "component_id": component_details.id,
        #     "component_type": component_details.component_type,
        #     "component_output": {
        #         "sql": sql_query,
        #         "table": table_json,
        #         **output # This spreads indicator or metric_grid into the response
        #     }
        # }


        # --- DYNAMIC TITLE GENERATION ---
        # Generate a clean title based on the user question (e.g. "Total Sales for Q1")
        df_temp = pd.DataFrame(table_json)
        dynamic_title_obj, token_usage = await generate_graph_title(
            user_query=data.query,
            df=df_temp,
            db_name=data.dbname,
            llm=llm,
            llm_model=llm_name
        )
        # Log token usage for title generation
        await i_data.add_llm_usage(api_endpoint="report_builder_title", llm=llm_name, **token_usage.model_dump())
        
        overall_heading = dynamic_title_obj if dynamic_title_obj else component_details.component_name

        # --- PROCESS OUTPUT ---
        if comp_type == "kpi_card":
            # Use the dynamic title for single KPI card
            output = {"indicator": rc_helper._process_kpi_logic(table_json, overall_heading)}
        # else:
        #     # For metric_grid, iterate through columns and clean titles
        #     df_grid = pd.DataFrame(table_json)
        #     num_cols = df_grid.select_dtypes(include=['number']).columns.tolist()
            
        #     grid_results = []
        #     for col in num_cols:
        #         # Format column name (total_revenue -> Total Revenue)
        #         cleaned_col_name = col.replace("_", " ").title()
        #         # Use the column data but pass the cleaned name
        #         res = rc_helper._process_kpi_logic(df_grid[[col]].to_dict('records'), cleaned_col_name)
        #         grid_results.append(res)
                
        #     output = {"metric_grid": grid_results,
        #     "metric_grid_title": overall_heading }

        else:
            # FOR METRIC GRID:
            df_grid = pd.DataFrame(table_json)
            
            # 1. Get all numerical columns
            all_num_cols = df_grid.select_dtypes(include=['number']).columns.tolist()
            
            # 2. Define columns that should NEVER be KPI cards (Dimensions)
            excluded_columns = {
                'year', 'month', 'quarter', 'day', 'fiscal_year', 
                'id', 'row_index', 'serial_number'
            }
            
            # 3. Filter them out (also filter out anything ending in '_id')
            num_cols = [
                col for col in all_num_cols 
                if col.lower() not in excluded_columns 
                and not col.lower().endswith('_id')
            ]
            
            # 4. If filtering leaves nothing, fall back to all columns 
            # (to prevent an empty screen if the user specifically asked for Year)
            if not num_cols:
                num_cols = all_num_cols[:2]

            grid_results = []
            for col in num_cols:
                cleaned_col_name = col.replace("_", " ").title()
                res = rc_helper._process_kpi_logic(df_grid[[col]].to_dict('records'), cleaned_col_name)
                grid_results.append(res)
                
            output = {
                "metric_grid": grid_results,
                "metric_grid_title": overall_heading
            }

        # Save the transaction
        await i_data.add_component_into_transactions(
            component_id=comp_id,
            modified_by=user_details.id,
            query=data.query,
            component_state_id=component_last_state.component_state_id+1,
            table_details=json.dumps(table_json) 
        )

        return {
            "component_id": comp_id,
            "component_type": comp_type,
            "component_output": {
                "sql": sql_query,
                "table": table_json,
                **output
            }
        }
#################################################
    # # --- NEW UNIFIED INDICATOR BLOCK ---
    # if component_details.component_type == "indicator":
    #     if not data.query:
    #         raise HTTPException(detail="Query required to update indicator", status_code=400)

    #     query_lc = data.query.lower()
    #     trend_keywords = ["last", "previous", "growth", "vs", "compare", "performance", "trend"]
    #     auto_include_trends = any(x in query_lc for x in trend_keywords)
        
    #     # Combine incoming metadata preference with auto-detection
    #     req_trends = getattr(data.component_metadata, 'include_trends', False) or auto_include_trends

    #     t2s_query = data.query
    #     if req_trends:
    #         t2s_query += " (Provide data points grouped by the relevant time dimension to allow growth calculation)"

    #     t2s = Text2SQL(dbname=data.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=t2s_query, filters="")
    #     resp = await t2s.sql_query_generator_basic()
        
    #     if not resp:
    #         raise HTTPException(detail="Text 2 SQL failed", status_code=400)

    #     if resp.get("status") == "awaiting_human_input":
    #         return {"component_id": data.component_id, "status": "awaiting_human_input", "message": resp.get("response")}

    #     sql_query = resp["response"][0]["sql_query"]
    #     table_details = await get_table_from_sql(client_pool, sql_query)
    #     table_json, table_status, _ = get_table_and_status_and_columns(table_details)

    #     if table_status != "success":
    #         logger.error(f"KPI SQL failed: {table_details.error}")
    #         raise HTTPException(detail=f"Database error: {table_details.error}", status_code=400)

    #     dynamic_title, token_usage = await generate_graph_title(
    #         user_query=data.query,
    #         df=pd.DataFrame(table_json),
    #         db_name=data.dbname,
    #         llm=llm,
    #         llm_model=llm_name
    #     )
    #     await i_data.add_llm_usage(api_endpoint="indicator_title", llm=llm_name, **token_usage.model_dump())

    #     indicator_data = rc_helper._process_indicator_logic(
    #         table_json, 
    #         title=dynamic_title or component_details.component_name or "Metric", 
    #         include_trends=req_trends
    #     )

    #     await i_data.add_component_into_transactions(
    #         component_id=component_details.id,
    #         modified_by=user_details.id,
    #         query=data.query,
    #         component_state_id=component_last_state.component_state_id + 1,
    #         table_details=json.dumps(table_json) 
    #     )

    #     return {
    #         "component_id": component_details.id,
    #         "component_type": "indicator",
    #         "component_output": {
    #             "sql": sql_query,
    #             "table": table_json,
    #             "indicator": indicator_data
    #         }
    #     }
    
##########################################################
    if component_details.component_type == "table":
        if data.component_metadata.sql:
            table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

            print("=========== TABLE JSON =============")
            print(table_json)
            print("=========== TABLE JSON =============")
            
            ct = await i_data.add_component_into_transactions(
                component_id=component_details.id,
                modified_by=user_details.id,
                component_state_id=component_last_state.component_state_id+1,
                table_details=json.dumps(data.component_metadata.model_dump())
            )

            if table_status != "success":
                logger.error(f"SQL excetion failed - {repr(table_details.error)}")
                raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
            
            return {
                "component_id": component_details.id,
                "report_id": component_details.report_id,
                "component_name": component_details.component_name,
                "component_description": component_details.component_description,
                "component_type": component_details.component_type,
                "is_active": component_details.is_active,
                "component_state_id": ct.component_state_id,
                "query": ct.query,
                "table_details": json.loads(ct.table_details) if ct.table_details else None,
                "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
                "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
                "component_output": {
                    "sql": None,
                    "table": table_json,
                    "table_columns": table_columns,
                    "graph": None,
                    "insights": None
                } 
            }

        if data.component_metadata.columns:
            query = f"Give me data containing all values from {', '.join(data.component_metadata.columns)}. Use appropriate joins if applicable"
            if data.component_metadata.grouped:
                query = query + " and Group the data long relevant column/s"
        else:
            query = data.query

        ct = await i_data.add_component_into_transactions(
                component_id=component_details.id,
                modified_by=user_details.id,
                component_state_id=component_last_state.component_state_id+1,
                table_details=json.dumps(data.component_metadata.model_dump()),
                query=data.query
            )

        t2s = Text2SQL(
            dbname=data.dbname, 
            vector_client=vector_client,
            llm=llm, 
            llm_name=llm_name,
            question=query,
            filters=""
        )
        resp = await t2s.sql_query_generator_basic()

        if not resp:
            raise HTTPException(detail = f"Text 2 SQL operation failed question - {query}", status_code=400)
        
        if resp.get("status") == "awaiting_human_input":
            raise HTTPException(detail = f"Text 2 SQL operation failed question - {query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

        sql_query = resp["response"][0]["sql_query"]
        approach = resp["response"][0]["approach"]
        table_details = await get_table_from_sql(client_pool, sql_query)

        table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
        await i_data.add_llm_usage(transaction_id=None, api_endpoint="report_table", **t2s.token_usage.model_dump()) #type: ignore

        if table_status != "success":
            logger.error(f"SQL excetion failed - {repr(table_details.error)}")
            raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
        return {
                "component_id": component_details.id,
                "report_id": component_details.report_id,
                "component_name": component_details.component_name,
                "component_description": component_details.component_description,
                "component_type": component_details.component_type,
                "is_active": component_details.is_active,
                "component_state_id": ct.component_state_id,
                "query": ct.query,
                "table_details": json.loads(ct.table_details) if ct.table_details else None,
                "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
                "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
                "component_output": {
                    "sql": sql_query,
                    "table": table_json,
                    "table_columns": table_columns,
                    "graph": None,
                    "insights": None
                } 
            }
        
    if component_details.component_type == "graph":

        token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0
        }

        if not data.component_metadata.sql and not data.query:
            raise HTTPException(status_code=404, detail="Provide 1 of SQL or query to generate graphs")
        
        if data.component_metadata.sql:
            table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
        else:
            t2s = Text2SQL(
                dbname=data.dbname, 
                vector_client=vector_client,
                llm=llm, 
                llm_name=llm_name,
                question=data.query,
                filters=""
            )
            resp = await t2s.sql_query_generator_basic()
            
            if not resp:
                await i_data.add_llm_usage(api_endpoint="report_graph", **t2s.token_usage.model_dump())
                raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
                
            if resp.get("status") == "awaiting_human_input":
                await i_data.add_llm_usage(api_endpoint="report_graph", **t2s.token_usage.model_dump())
                raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

            sql_query = resp["response"][0]["sql_query"]
            approach = resp["response"][0]["approach"]
            table_details = await get_table_from_sql(client_pool, sql_query)

            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
            token_usage["input_tokens"] += t2s.token_usage.input_tokens
            token_usage["output_tokens"] += t2s.token_usage.output_tokens
            token_usage["cached_tokens"] += t2s.token_usage.cached_tokens
        
        ct = await i_data.add_component_into_transactions(
            component_id=component_details.id,
            modified_by=user_details.id,
            query=data.query,
            component_state_id=component_last_state.component_state_id+1,
            graph_details=json.dumps(data.component_metadata.model_dump())
        )
        
        if table_status != "success":
            logger.error(f"SQL excetion failed - {repr(table_details.error)}")
            raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
        df = pd.DataFrame(table_json) #type: ignore
        
        graph_maker = GraphGenerator(df)
        graph_maker.correct_data_()
        graphs_list = graph_maker.generate_graphs()

        graph_title, token_details = await generate_graph_title(
            user_query=data.query if data.query else "Create title using provided columns",
            df=df,
            db_name=data.dbname,
            llm=llm,
            llm_model=llm_name
        )
        
        token_usage["input_tokens"] += token_details.input_tokens
        token_usage["output_tokens"] += token_details.output_tokens
        token_usage["cached_tokens"] += token_details.cached_tokens
        await i_data.add_llm_usage(api_endpoint="report_graph", llm=llm_name, **token_usage)

        return {
            "component_id": component_details.id,
            "report_id": component_details.report_id,
            "component_name": component_details.component_name,
            "component_description": component_details.component_description,
            "component_type": component_details.component_type,
            "is_active": component_details.is_active,
            "component_state_id": ct.component_state_id,
            "query": ct.query,
            "table_details": json.loads(ct.table_details) if ct.table_details else None,
            "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
            "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
            "component_output": {
                "sql": sql_query if data.query else None,
                "table": table_json,
                "table_columns": table_columns,
                "graph": graphs_list[:1],
                "graph_title": graph_title,
                "insights": None
            } 
        }


    if component_details.component_type == "insights":

        token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0
        }

        if not data.component_metadata.sql and not data.query:
            raise HTTPException(status_code=404, detail="Provide 1 of SQL or query to generate summary")

        if data.component_metadata.sql:
            table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
        else:
            t2s = Text2SQL(
                dbname=data.dbname, 
                vector_client=vector_client,
                llm=llm, 
                llm_name=llm_name,
                question=data.query,
                filters=""
            )
            resp = await t2s.sql_query_generator_basic()
            
            if not resp:
                await i_data.add_llm_usage(api_endpoint="report_insights", **t2s.token_usage.model_dump())
                raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
                
            if resp.get("status") == "awaiting_human_input":
                await i_data.add_llm_usage(api_endpoint="report_insights", **t2s.token_usage.model_dump())
                raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

            sql_query = resp["response"][0]["sql_query"]
            approach = resp["response"][0]["approach"]
            table_details = await get_table_from_sql(client_pool, sql_query)

            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
            token_usage["input_tokens"] += t2s.token_usage.input_tokens
            token_usage["output_tokens"] += t2s.token_usage.output_tokens
            token_usage["cached_tokens"] += t2s.token_usage.cached_tokens
        
        print("=========== TABLE JSON =============")
        print(table_json)
        print("=========== TABLE JSON =============")
        
        ct = await i_data.add_component_into_transactions(
            component_id=component_details.id,
            modified_by=user_details.id,
            query=data.query,
            component_state_id=component_last_state.component_state_id+1,
            insights_details=json.dumps(data.component_metadata.model_dump())
        )

        if table_status != "success":
            logger.error(f"SQL excetion failed - {repr(table_details.error)}")
            raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
        insights_generator = ReportComponent(
            dbname=data.dbname,
            llm=llm, 
            llm_name=llm_name
        )

        inights_metadata = ""
        if data.component_metadata.format:
            inights_metadata = inights_metadata+f"Format: {data.component_metadata.format} \n"
        if data.component_metadata.tone:
            inights_metadata = inights_metadata+f"Tone: {data.component_metadata.tone} \n"
        if data.component_metadata.word_limit:
            inights_metadata = inights_metadata+f"Word Limit: {data.component_metadata.word_limit} \n"
        if data.component_metadata.audience:
            inights_metadata = inights_metadata+f"Audience: {data.component_metadata.audience} \n"
            
        table_summary_json = await insights_generator.generate_insights_from_table(inights_metadata, table_json)
        
        token_usage["input_tokens"] += insights_generator.token_usage.input_tokens
        token_usage["output_tokens"] += insights_generator.token_usage.output_tokens
        token_usage["cached_tokens"] += insights_generator.token_usage.cached_tokens
        await i_data.add_llm_usage(transaction_id=None, api_endpoint="report_insights", **token_usage) #type: ignore
        
        if not table_summary_json:
            raise HTTPException(status_code=400, detail="Not able to generate table summary")
        
        table_summary = table_summary_json["summary"]
        
        return {
            "component_id": component_details.id,
            "report_id": component_details.report_id,
            "component_name": component_details.component_name,
            "component_description": component_details.component_description,
            "component_type": component_details.component_type,
            "is_active": component_details.is_active,
            "component_state_id": ct.component_state_id,
            "query": ct.query,
            "table_details": json.loads(ct.table_details) if ct.table_details else None,
            "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
            "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
            "component_output": {
                "sql": sql_query if data.query else None,
                "table": table_json,
                "table_columns": table_columns,
                "graph": None,
                "insights": table_summary
            } 
        }

    raise HTTPException(detail="Unknown request", status_code=404)



@router.post(f'/report_builder/{VERSION}/reports/chat', status_code=200)
async def report_chats(
    data: ReportChats,
    session: AsyncSession = Depends(get_db_async)
):
    client_pool = client_connection_pool
    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    report_details = await i_data.get_report_details_from_report_id(data.report_id)
    if not report_details:
        raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    

    if not data.query:
        raise HTTPException(detail="No details found to update component", status_code=404)
        
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    vector_connection = get_vector_db()
    vector_client = VectorStore(vector_connection)
    await vector_client.ensure_collection(data.dbname)

    token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0
    }

    rc = ReportComponent(
        dbname=data.dbname,
        llm=llm,
        llm_name=llm_name
    )
    possible_routes = await rc.extract_possible_routes(data.query)
    token_usage["input_tokens"] += rc.token_usage.input_tokens
    token_usage["output_tokens"] += rc.token_usage.output_tokens
    token_usage["cached_tokens"] += rc.token_usage.cached_tokens
    
    if not possible_routes:
        raise HTTPException(status_code=400, detail="Routes were not extracted properly")
    
    t2s_question = possible_routes["table"]["metadata"]["sql_question"] if possible_routes["table"]["is_required"] else data.query
    
    t2s = Text2SQL(
        dbname=data.dbname,
        vector_client=vector_client,
        llm=llm,
        llm_name=llm_name,
        question=t2s_question,
        filters=""
    )

    resp = await t2s.sql_query_generator_basic()
    token_usage["input_tokens"] += t2s.token_usage.input_tokens
    token_usage["output_tokens"] += t2s.token_usage.output_tokens
    token_usage["cached_tokens"] += t2s.token_usage.cached_tokens

    if not resp:
        await i_data.add_llm_usage(api_endpoint="report_chat", **t2s.token_usage.model_dump())
        raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
        
    if resp.get("status") == "awaiting_human_input":
        await i_data.add_llm_usage(api_endpoint="report_chat", **t2s.token_usage.model_dump())
        raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

    sql_query = resp["response"][0]["sql_query"]
    approach = resp["response"][0]["approach"]
    table_details = await get_table_from_sql(client_pool, sql_query)

    table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
    token_usage["input_tokens"] += t2s.token_usage.input_tokens
    token_usage["output_tokens"] += t2s.token_usage.output_tokens
    token_usage["cached_tokens"] += t2s.token_usage.cached_tokens

    components_output = []

    if possible_routes["table"]["is_required"]:
        table_component_details = await i_data.create_report_component(
            report_id=data.report_id,
            component_name=None,
            component_description=None,
            component_type="table",
            created_by=user_details.id
        )

        table_component_metadata = {
            "component_type": "table",
            "sql": sql_query
        } 

        table_component_transaction = await i_data.add_component_into_transactions(
            component_id=table_component_details.id,
            modified_by=user_details.id,
            query=data.query,
            table_details=json.dumps(table_component_metadata)
        ) 

        components_output.append({
            "component_id": table_component_details.id,
            "report_id": table_component_details.report_id,
            "component_name": table_component_details.component_name,
            "component_description": table_component_details.component_description,
            "component_type": "table",
            "is_active": table_component_details.is_active,
            "component_state_id": table_component_transaction.component_state_id,
            "query": table_component_transaction.query,
            "table_details": json.loads(table_component_transaction.table_details),
            "graph_details": None,
            "insights_details": None,
            "component_output": {
                "sql": sql_query,
                "table": table_json,
                "table_columns": table_columns,
                "graph": None,
                "graph_title": None,
                "insights": None
            } 
        })

    if possible_routes["graph"]["is_required"]:
        df = pd.DataFrame(table_json) #type: ignore
        
        graph_maker = GraphGenerator(df)
        graph_maker.correct_data_()
        graphs_list = graph_maker.generate_graphs()

        if graphs_list:
            graph_component_details = await i_data.create_report_component(
                report_id=data.report_id,
                component_name=None,
                component_description=None,
                component_type="graph",
                created_by=user_details.id
            )

            graph_component_metadata = {
                "component_type": "graph",
                "sql": sql_query,
                "title": possible_routes["graph"]["metadata"]["title"],
                "graph_type": graphs_list[0].get("chart_type"),
                "x_axis": possible_routes["graph"]["metadata"].get("x_axis"),
                "y_axis": possible_routes["graph"]["metadata"].get("y_axis"),
                "legend": None,
                "colo_palette": None
            } 

            graph_component_transaction = await i_data.add_component_into_transactions(
                component_id=graph_component_details.id,
                modified_by=user_details.id,
                query=data.query,
                graph_details=json.dumps(graph_component_metadata)
            ) 

            components_output.append({
                "component_id": graph_component_details.id,
                "report_id": graph_component_details.report_id,
                "component_name": graph_component_details.component_name,
                "component_description": graph_component_details.component_description,
                "component_type": "graph",
                "is_active": graph_component_details.is_active,
                "component_state_id": graph_component_transaction.component_state_id,
                "query": graph_component_transaction.query,
                "table_details": None,
                "graph_details": json.loads(graph_component_transaction.graph_details),
                "insights_details": None,
                "component_output": {
                    "sql": sql_query,
                    "table": None,
                    "table_columns": None,
                    "graph": graphs_list[:1],
                    "graph_title": possible_routes["graph"]["metadata"]["title"],
                    "insights": None
                } 
            })


    if possible_routes["insights"]["is_required"]:
        insights_generator = ReportComponent(
            dbname=data.dbname,
            llm=llm, 
            llm_name=llm_name
        )

        inights_metadata = ""

        table_summary_json = await insights_generator.generate_insights_from_table(inights_metadata, table_json)
        
        token_usage["input_tokens"] += insights_generator.token_usage.input_tokens
        token_usage["output_tokens"] += insights_generator.token_usage.output_tokens
        token_usage["cached_tokens"] += insights_generator.token_usage.cached_tokens
        
        if table_summary_json:
            table_summary = table_summary_json["summary"]

            insights_component_details = await i_data.create_report_component(
                report_id=data.report_id,
                component_name=None,
                component_description=None,
                component_type="insights",
                created_by=user_details.id
            )

            insights_component_metadata = {
                "component_type": "insights",
                "sql": sql_query,
                "objective": None,
                "word_limit": possible_routes["insights"]["metadata"].get("word_limit"),
                "tnne": possible_routes["insights"]["metadata"].get("tone"),
                "format": possible_routes["insights"]["metadata"].get("format"),
                "audience": possible_routes["insights"]["metadata"].get("audience")
            } 

            insights_component_transaction = await i_data.add_component_into_transactions(
                component_id=insights_component_details.id,
                modified_by=user_details.id,
                query=data.query,
                insights_details=json.dumps(insights_component_metadata)
            ) 

            components_output.append({
                "component_id": insights_component_details.id,
                "report_id": insights_component_details.report_id,
                "component_name": insights_component_details.component_name,
                "component_description": insights_component_details.component_description,
                "component_type": "insights",
                "is_active": insights_component_details.is_active,
                "component_state_id": insights_component_transaction.component_state_id,
                "query": insights_component_transaction.query,
                "table_details": None,
                "graph_details": None,
                "insights_details": json.loads(insights_component_transaction.insights_details),
                "component_output": {
                    "sql": sql_query,
                    "table": None,
                    "table_columns": None,
                    "graph": None,
                    "graph_title": None,
                    "insights": table_summary
                } 
            })

    await i_data.add_llm_usage(api_endpoint="report_chat", llm=llm_name, **token_usage)

    if not components_output:
        raise HTTPException(status_code=404, detail="Not able to generate any component for the request")

    return components_output
############################

@router.post(f'/report_builder/{VERSION}/reports/generate-dashboard', status_code=200)
async def generate_full_dashboard(
    payload: ReportGeneration,
    session: AsyncSession = Depends(get_db_async)
):
    client_pool = client_connection_pool
    i_data = InternalSQLHelper(session)
    
    # Setup Config, LLM, and Vector Client (same as before)
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    vector_connection = get_vector_db()
    vector_client = VectorStore(vector_connection)
    await vector_client.ensure_collection(payload.dbname)

    storyboard_points = [s for s in payload.selectables if s.field == "storyboard_point" and s.is_selected]

    for point in storyboard_points:
        statement = point.option
        comp_type = point.type
        # comp_type = point.type or "table"

    # 1. Extract only selected storyboard points    
    if not storyboard_points:
        raise HTTPException(status_code=400, detail="No components found to generate.")

    dashboard_output = []
    total_token_usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    
    rc_helper = ReportComponent(payload.dbname, llm, llm_name)

    # 2. Iterate and Generate
    for idx, point in enumerate(storyboard_points):
        statement = point.option
        
        # FIX: Check root level 'type' first (Step 4 format), then fallback to 'metadata'
        raw_type = point.type or (point.metadata.get("type") if point.metadata else "table")

        # is_kpi = raw_type in ["kpi_card", "indicator", "metric_grid"]
                
        # # Map 'indicator' and 'graph' to your GraphGenerator logic
        # final_processing_type = "graph" if raw_type in ["graph", "indicator"] else raw_type
        
        try:
            # A. SQL Generation
            t2s = Text2SQL(dbname=payload.dbname, vector_client=vector_client, llm=llm, llm_name=llm_name, question=statement, filters="")
            resp = await t2s.sql_query_generator_basic()
            
            if not resp or resp.get("status") == "awaiting_human_input":
                continue

            sql_query = resp["response"][0]["sql_query"]
            
            # B. Data Fetching
            table_details = await get_table_from_sql(client_pool, sql_query)
            table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

            if table_status != "success":
                logger.error(f"SQL execution failed for '{statement}': {table_details.error}")
                continue

            # C. Processing based on type
            processed_data = {
                "sql": sql_query,
                "table": table_json,
                "table_columns": table_columns,
                "indicator": None,
                "metric_grid": None,
                "graph": None,
                "insights": None
            }
############################################            
            if raw_type == "kpi_card" or raw_type == "indicator":
                processed_data["indicator"] = rc_helper._process_kpi_logic(table_json, statement)
            elif raw_type == "metric_grid":
                df_grid = pd.DataFrame(table_json)
                num_cols = df_grid.select_dtypes(include=[np.number]).columns.tolist()
                processed_data["metric_grid"] = [
                    rc_helper._process_kpi_logic(df_grid[[col]].to_dict('records'), col) 
                    for col in num_cols
                ]
####################################
            # if raw_type in ["indicator", "kpi_card", "metric_grid"]:
            #     # Default storyboard indicators to include trends
            #     processed_data["indicator"] = rc_helper._process_indicator_logic(table_json, statement, include_trends=True)
            #     final_type = "indicator"
                
            # if final_processing_type == "graph":
            elif raw_type in ["graph", "chart"]:
                df = pd.DataFrame(table_json)
                graph_maker = GraphGenerator(df)
                graph_maker.correct_data_()
                processed_data["graph"] = graph_maker.generate_graphs()[:1]
                
                # Title generation
                graph_title, _ = await generate_graph_title(user_query=statement, df=df, db_name=payload.dbname, llm=llm, llm_model=llm_name)
                processed_data["graph_title"] = graph_title

            # elif final_processing_type == "insights":
            elif raw_type == "insights":
                insights_generator = ReportComponent(dbname=payload.dbname, llm=llm, llm_name=llm_name)
                insight_res = await insights_generator.generate_insights_from_table("Business summary", table_json)
                processed_data["insights"] = insight_res.get("summary")

            # D. Database Persistence
            component_db = await i_data.create_report_component(
                report_id=payload.report_id,
                component_name=f"Component {idx+1}",
                component_description=statement,
                component_type=raw_type, # Store original type (e.g. indicator)
                created_by=1
            )
            
            # Save transaction/state
            await i_data.add_component_into_transactions(
                component_id=component_db.id,
                modified_by=1,
                query=statement,
                component_state_id=1,
                table_details=json.dumps(processed_data) if raw_type in ["table", "kpi_card", "indicator", "metric_grid"] else None,
                graph_details=json.dumps(processed_data) if raw_type in ["graph", "chart"] else None,
                insights_details=json.dumps(processed_data) if raw_type == "insights" else None
            )            #     # Route data to correct column in DB
            #     table_details=json.dumps(processed_data) if final_processing_type == "table" else None,
            #     graph_details=json.dumps(processed_data) if final_processing_type == "graph" else None,
            #     insights_details=json.dumps(processed_data) if final_processing_type == "insights" else None
            # )

            dashboard_output.append({
                "component_id": component_db.id,
                "type": raw_type,
                "statement": statement,
                "data": processed_data
            })

            total_token_usage["input_tokens"] += t2s.token_usage.input_tokens
            total_token_usage["output_tokens"] += t2s.token_usage.output_tokens

        except Exception as e:
            logger.error(f"Failed component {statement}: {str(e)}")
            continue

    return {
        "status": "success",
        "report_id": payload.report_id,
        "components": dashboard_output
    }

# from fastapi import APIRouter, Depends, HTTPException
# from app.models import ResetChat, ReportChats, ReportId, ReportComponentId, UpdateReport, UpdateReportComponentId, ReportGeneration
# from app.logger import get_logger
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.databases.connections import (
#     # get_db_async,
#     # get_nosql_client,
#     # client_connection_pool,
#     # get_vector_db
#     get_db_async,
#     client_pool_manager,
#     get_pool,
#     nosql_client,
#     vector_client, 
#     caching_client
# )
# from app.databases.client_sql.operations import (
#     get_table_from_sql, 
#     get_table_and_status_and_columns, 
#     get_table_from_sql_parallel
# )
# from app.databases.internal_sql_operations import InternalSQLHelper
# from app.databases.internal_nosql_operations import NOSQLHelper
# from app.databases.nosql_schema import Plotly_Graph
# # from app.core.table_from_sql import get_table_from_sql_parallel, get_table_from_sql
# from app.appConfig import settings
# from app.core.graphs.plotly.custom_dashboard import generate_custom_kpi_graphs
# import pandas as pd
# import asyncio
# # from app.core.helper import get_table_and_status_and_columns, log_sql_data, get_drilldown_features
# from app.core.helper import log_sql_data, get_drilldown_features
# import yaml
# import json
# import os
# from app.core.dashboards.introductions import get_column_stats, get_updated_metadata
# from .base_check import perform_base_check
# from app.core.llms import get_llm
# from app.core.dashboards.custom_dashboard import GenerateCustomDashboard
# from app.core.graphs.plotly.base import generate_graphs
# from app.core.graphs.echarts.graphs import GraphGenerator
# from app.core.report_builder.report_component import ReportComponent
# from app.core.text_2_sql.text2sql import Text2SQL
# from app.databases.vector_operations import VectorStore
# from app.core.graphs.echarts.graphs import GraphGenerator, generate_graph_title



# router = APIRouter(prefix="/egai", tags=["Report_Builder"])


# logger = get_logger()

# VERSION = "v1"

# def process_username(user_name: str):
#     user_name = user_name.strip().lower()
#     first_name, last_name = user_name.split(" ")
#     email = f"{user_name[0]}.{user_name[1]}@eclerx.com"
#     return first_name, last_name, email

# @router.post(f'/report_builder/{VERSION}/reports', status_code=200)
# async def create_report(
#     data: ReportId,
#     session: AsyncSession = Depends(get_db_async)
# ): 
#     i_data = InternalSQLHelper(session)
#     user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
#     report_details = await i_data.get_report_details_from_db_id_and_report_name(db_details.id, data.report_name)
#     if not report_details:
#         logger.debug("Report does not exists")
    
#     report_details = await i_data.create_report(
#         data.report_name,
#         data.report_description,
#         user_details.id,
#         db_details.id
#     )

#     if not report_details:
#         logger.error("Report neither retreived nor created successfully")
#         raise HTTPException(detail="Report neither retreived nor created successfully", status_code=400)

#     return {
#         "report_id": report_details.id,
#         "report_name": report_details.report_name,
#         "report_description": report_details.report_description,
#         "dbname": data.dbname
#     }


# @router.get(f'/report_builder/{VERSION}/reports', status_code=200)
# async def get_reports(dbname: str, user_name: str, session: AsyncSession = Depends(get_db_async)):
#     first_name, last_name, email_id = process_username(user_name)

#     i_data = InternalSQLHelper(session)

#     user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     reports = await i_data.get_report_details_from_db_id(db_details.id)
#     report_dict = [{
#         "report_id": r.id,
#         "report_name": r.report_name,
#         "report_description": r.report_description,
#         "dbname": dbname
#     } for r in reports]

#     return report_dict


# @router.get(f'/report_builder/{VERSION}/reports/{{report_id}}', status_code=200)
# async def get_particular_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
#     first_name, last_name, email_id = process_username(user_name)

#     i_data = InternalSQLHelper(session)

#     user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     report_details = await i_data.get_report_details_from_report_id(report_id)
#     if not report_details:
#         raise HTTPException(detail="Report with provided id not found", status_code=404)
    
#     return {
#         "report_id": report_details.id,
#         "report_name": report_details.report_name,
#         "report_description": report_details.report_description,
#         "dbname": dbname
#     }


# @router.delete(f'/report_builder/{VERSION}/reports/{{report_id}}', status_code=204)
# async def soft_delete_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
#     first_name, last_name, email_id = process_username(user_name)

#     i_data = InternalSQLHelper(session)

#     user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     report_details = await i_data.get_report_details_from_report_id(report_id)
#     if not report_details:
#         raise HTTPException(detail="Report with provided id not found", status_code=404)
    
#     delete_status = await i_data.update_report_data(report_id, {"is_active": False})
#     if not delete_status:
#         raise HTTPException(detail="Report was deleted successfully", status_code=404)
#     return    


# @router.put(f'/report_builder/{VERSION}/reports', status_code=201)
# async def update_report(
#     data: UpdateReport,
#     session: AsyncSession = Depends(get_db_async)
# ): 
#     i_data = InternalSQLHelper(session)
#     user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     report_details = await i_data.get_report_details_from_report_id(data.report_id)
#     if not report_details:
#         raise HTTPException(detail="Report with provided id not found", status_code=404)
    
#     update_status = await i_data.update_report_data(
#         data.report_id, 
#         {   
#             "is_active": data.is_active,
#             "report_name": data.report_name,
#             "report_description": data.report_description
#         }
#     )
#     if not update_status:
#         raise HTTPException(detail="Report was NOT updated successfully", status_code=404)

#     report_details = await i_data.get_report_details_from_report_id(data.report_id)
    
#     if not report_details:        
#         logger.warning("Report not found after update")
#         raise HTTPException(detail="Report not found after update", status_code=404)
    
#     return {
#         "report_id": report_details.id,
#         "report_name": report_details.report_name,
#         "report_description": report_details.report_description,
#         "dbname": data.dbname
#     }


# ########################### REPORT COMPONENETS #####################################
# @router.post(f'/report_builder/{VERSION}/reports/components', status_code=201)
# async def create_component(
#     data: ReportComponentId,
#     session: AsyncSession = Depends(get_db_async)
# ): 
#     i_data = InternalSQLHelper(session)
#     user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
    
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
#     report_details = await i_data.get_report_details_from_report_id(data.report_id)
#     if not report_details:
#         raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
#     # component_details = await i_data.get_component_details_from_name_and_report_id(report_details.id, data.component_name)
#     # if component_details:
#     #     raise HTTPException(detail="Component with same name exists for this report", status_code=400)

#     component_details = await i_data.create_report_component(
#         report_id=report_details.id,
#         component_name=data.component_name,
#         component_description=data.component_description,
#         component_type=data.component_metadata.component_type if data.component_metadata else None,
#         created_by=user_details.id
#     )

#     component_type = data.component_metadata.component_type if data.component_metadata else None

#     if not component_details:
#         raise HTTPException(detail="component was not created properly", status_code=400)

#     report_transaction_details = await i_data.add_component_into_transactions(
#         component_details.id,
#         user_details.id,
#         table_details=json.dumps(data.component_metadata.model_dump()) if component_type == "table" else None,
#         graph_details=json.dumps(data.component_metadata.model_dump()) if component_type == "graph" else None,
#         insights_details=json.dumps(data.component_metadata.model_dump()) if component_type == "insights" else None,
#     )

#     if not report_transaction_details:
#         raise HTTPException(detail="component was not added into transactions", status_code=400)
    
#     return {
#         "component_id": component_details.id,
#         "report_id": report_details.id,
#         "component_name": component_details.component_name,
#         "component_description": component_details.component_description,
#         "component_type": component_details.component_type,
#         "is_active": component_details.is_active,
#         "component_state_id": report_transaction_details.component_state_id,
#         "query": report_transaction_details.query,
#         "table_details": json.loads(report_transaction_details.table_details) if report_transaction_details.table_details else None,
#         "graph_details": json.loads(report_transaction_details.graph_details) if report_transaction_details.graph_details else None,
#         "insights_details": json.loads(report_transaction_details.insights_details) if report_transaction_details.insights_details else None
#     }


# @router.get(f'/report_builder/{VERSION}/reports/{{report_id}}/components', status_code=200)
# async def get_all_components_for_report(dbname: str, user_name: str, report_id: int, session: AsyncSession = Depends(get_db_async)):
#     first_name, last_name, email_id = process_username(user_name)

#     i_data = InternalSQLHelper(session)

#     user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     report_details = await i_data.get_report_details_from_report_id(report_id)
#     if not report_details:
#         raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
#     component_details = await i_data.get_component_ids_for_report(report_id)
#     if not component_details:
#         raise HTTPException(detail="Components not found", status_code=404)
    
#     component_list = []

#     for c in component_details:
#         ct = await i_data.get_component_last_state(component_id=c.id)
#         if ct:
#             component_list.append(
#                     {
#                         "component_id": c.id,
#                         "report_id": c.report_id,
#                         "component_name": c.component_name,
#                         "component_description": c.component_description,
#                         "component_type": c.component_type,
#                         "is_active": c.is_active,
#                         "component_state_id": ct.component_state_id,
#                         "query": ct.query,
#                         "table_details": json.loads(ct.table_details) if ct.table_details else None,
#                         "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#                         "insights_details": json.loads(ct.insights_details) if ct.insights_details else None
#                     }
#                 )
#         else:
#             logger.warning(f"Component_transactions not fecthed properly for compnent_id - {c.id}")

#     return component_list


# @router.get(f'/report_builder/{VERSION}/reports/components/{{component_id}}', status_code=200)
# async def get_particular_component(dbname: str, user_name: str, component_id: int, session: AsyncSession = Depends(get_db_async)):
#     first_name, last_name, email_id = process_username(user_name)

#     i_data = InternalSQLHelper(session)

#     user_details = await i_data.get_user_details_from_username(first_name=first_name, last_name=last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

#     component_details = await i_data.get_component_details_from_id(component_id)
#     if not component_details:
#         raise HTTPException(detail="Components not found", status_code=404)
    
#     ct = await i_data.get_component_last_state(component_id=component_details.id)
#     if not ct:
#         logger.error("Component Not found in transactions")
#         raise HTTPException(detail="Component Not found in transactions", status_code=404)

#     return {
#         "component_id": component_details.id,
#         "report_id": component_details.report_id,
#         "component_name": component_details.component_name,
#         "component_description": component_details.component_description,
#         "component_type": component_details.component_type,
#         "is_active": component_details.is_active,
#         "component_state_id": ct.component_state_id,
#         "query": ct.query,
#         "table_details": json.loads(ct.table_details) if ct.table_details else None,
#         "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#         "insights_details": json.loads(ct.insights_details) if ct.insights_details else None
#     }


# @router.post(f'/report_builder/{VERSION}/reports/components/update', status_code=200)
# async def update_report_component(
#     data: UpdateReportComponentId,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     # client_pool = client_connection_pool
#     # i_data = InternalSQLHelper(session)

#     i_data = InternalSQLHelper(session)

#     # 1. NEW WAY TO GET CLIENT POOL
#     fetched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
#     if not fetched_details:
#         raise HTTPException(status_code=404, detail="Dataset and DB Connection not found") 
#     db_details, connection_details = fetched_details
#     client_pool = await get_pool(db_details, connection_details)

#     user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     # db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
#     # if not db_details:
#     #     raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
#     report_details = await i_data.get_report_details_from_report_id(data.report_id)
#     if not report_details:
#         raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    
#     component_details = await i_data.get_component_details_from_id(data.component_id)
#     if not component_details:
#         raise HTTPException(detail="COmponent does not exists nor created successfully", status_code=404)
    
#     if not data.query and not data.component_metadata:
#         raise HTTPException(detail="No details found to update component", status_code=404)
    
#     if data.component_metadata:
#         if data.component_metadata.component_type != component_details.component_type:
#             raise HTTPException(detail="Cannot modify the type of component", status_code=400)
        
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     # vector_connection = get_vector_db()
#     # vector_client = VectorStore(vector_connection)
#     # await vector_client.ensure_collection(data.dbname)
#     # 2. VECTOR CLIENT UPDATE
#     # Using vector_client from connections
#     vector_store_client = VectorStore(vector_client) 
#     await vector_store_client.ensure_collection(data.dbname)

#     component_last_state = await i_data.get_component_last_state(data.component_id)
    
#     if component_details.component_type == "table":
#         if data.component_metadata.sql:
#             table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

#             print("=========== TABLE JSON =============")
#             print(table_json)
#             print("=========== TABLE JSON =============")
            
#             ct = await i_data.add_component_into_transactions(
#                 component_id=component_details.id,
#                 modified_by=user_details.id,
#                 component_state_id=component_last_state.component_state_id+1,
#                 table_details=json.dumps(data.component_metadata.model_dump())
#             )

#             if table_status != "success":
#                 logger.error(f"SQL excetion failed - {repr(table_details.error)}")
#                 raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
            
#             return {
#                 "component_id": component_details.id,
#                 "report_id": component_details.report_id,
#                 "component_name": component_details.component_name,
#                 "component_description": component_details.component_description,
#                 "component_type": component_details.component_type,
#                 "is_active": component_details.is_active,
#                 "component_state_id": ct.component_state_id,
#                 "query": ct.query,
#                 "table_details": json.loads(ct.table_details) if ct.table_details else None,
#                 "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#                 "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
#                 "component_output": {
#                     "sql": None,
#                     "table": table_json,
#                     "table_columns": table_columns,
#                     "graph": None,
#                     "insights": None
#                 } 
#             }

#         if data.component_metadata.columns:
#             query = f"Give me data containing all values from {', '.join(data.component_metadata.columns)}. Use appropriate joins if applicable"
#             if data.component_metadata.grouped:
#                 query = query + " and Group the data long relevant column/s"
#         else:
#             query = data.query

#         ct = await i_data.add_component_into_transactions(
#                 component_id=component_details.id,
#                 modified_by=user_details.id,
#                 component_state_id=component_last_state.component_state_id+1,
#                 table_details=json.dumps(data.component_metadata.model_dump()),
#                 query=data.query
#             )

#         t2s = Text2SQL(
#             dbname=data.dbname, 
#             vector_client=vector_store_client,
#             llm=llm, 
#             llm_name=llm_name,
#             question=query,
#             filters=""
#         )
#         resp = await t2s.sql_query_generator_basic()

#         if not resp:
#             raise HTTPException(detail = f"Text 2 SQL operation failed question - {query}", status_code=400)
        
#         if resp.get("status") == "awaiting_human_input":
#             raise HTTPException(detail = f"Text 2 SQL operation failed question - {query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

#         sql_query = resp["response"][0]["sql_query"]
#         approach = resp["response"][0]["approach"]
#         table_details = await get_table_from_sql(client_pool, sql_query)

#         table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#         await i_data.add_llm_usage(transaction_id=None, api_endpoint="report_table", **t2s.token_usage.model_dump()) #type: ignore

#         if table_status != "success":
#             logger.error(f"SQL excetion failed - {repr(table_details.error)}")
#             raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
#         return {
#                 "component_id": component_details.id,
#                 "report_id": component_details.report_id,
#                 "component_name": component_details.component_name,
#                 "component_description": component_details.component_description,
#                 "component_type": component_details.component_type,
#                 "is_active": component_details.is_active,
#                 "component_state_id": ct.component_state_id,
#                 "query": ct.query,
#                 "table_details": json.loads(ct.table_details) if ct.table_details else None,
#                 "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#                 "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
#                 "component_output": {
#                     "sql": sql_query,
#                     "table": table_json,
#                     "table_columns": table_columns,
#                     "graph": None,
#                     "insights": None
#                 } 
#             }
        
#     if component_details.component_type == "graph":

#         token_usage = {
#             "input_tokens": 0,
#             "output_tokens": 0,
#             "cached_tokens": 0
#         }

#         if not data.component_metadata.sql and not data.query:
#             raise HTTPException(status_code=404, detail="Provide 1 of SQL or query to generate graphs")
        
#         if data.component_metadata.sql:
#             table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#         else:
#             t2s = Text2SQL(
#                 dbname=data.dbname, 
#                 vector_client=vector_store_client,
#                 llm=llm, 
#                 llm_name=llm_name,
#                 question=data.query,
#                 filters=""
#             )
#             resp = await t2s.sql_query_generator_basic()
            
#             if not resp:
#                 await i_data.add_llm_usage(api_endpoint="report_graph", **t2s.token_usage.model_dump())
#                 raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
                
#             if resp.get("status") == "awaiting_human_input":
#                 await i_data.add_llm_usage(api_endpoint="report_graph", **t2s.token_usage.model_dump())
#                 raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

#             sql_query = resp["response"][0]["sql_query"]
#             approach = resp["response"][0]["approach"]
#             table_details = await get_table_from_sql(client_pool, sql_query)

#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#             token_usage["input_tokens"] += t2s.token_usage.input_tokens
#             token_usage["output_tokens"] += t2s.token_usage.output_tokens
#             token_usage["cached_tokens"] += t2s.token_usage.cached_tokens
        
#         ct = await i_data.add_component_into_transactions(
#             component_id=component_details.id,
#             modified_by=user_details.id,
#             query=data.query,
#             component_state_id=component_last_state.component_state_id+1,
#             graph_details=json.dumps(data.component_metadata.model_dump())
#         )
        
#         if table_status != "success":
#             logger.error(f"SQL excetion failed - {repr(table_details.error)}")
#             raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
#         df = pd.DataFrame(table_json) #type: ignore
        
#         graph_maker = GraphGenerator(df)
#         graph_maker.correct_data_()
#         graphs_list = graph_maker.generate_graphs()

#         graph_title, token_details = await generate_graph_title(
#             user_query=data.query if data.query else "Create title using provided columns",
#             df=df,
#             db_name=data.dbname,
#             llm=llm,
#             llm_model=llm_name
#         )
        
#         token_usage["input_tokens"] += token_details.input_tokens
#         token_usage["output_tokens"] += token_details.output_tokens
#         token_usage["cached_tokens"] += token_details.cached_tokens
#         await i_data.add_llm_usage(api_endpoint="report_graph", llm=llm_name, **token_usage)

#         return {
#             "component_id": component_details.id,
#             "report_id": component_details.report_id,
#             "component_name": component_details.component_name,
#             "component_description": component_details.component_description,
#             "component_type": component_details.component_type,
#             "is_active": component_details.is_active,
#             "component_state_id": ct.component_state_id,
#             "query": ct.query,
#             "table_details": json.loads(ct.table_details) if ct.table_details else None,
#             "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#             "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
#             "component_output": {
#                 "sql": sql_query if data.query else None,
#                 "table": table_json,
#                 "table_columns": table_columns,
#                 "graph": graphs_list[:1],
#                 "graph_title": graph_title,
#                 "insights": None
#             } 
#         }


#     if component_details.component_type == "insights":

#         token_usage = {
#             "input_tokens": 0,
#             "output_tokens": 0,
#             "cached_tokens": 0
#         }

#         if not data.component_metadata.sql and not data.query:
#             raise HTTPException(status_code=404, detail="Provide 1 of SQL or query to generate summary")

#         if data.component_metadata.sql:
#             table_details = await get_table_from_sql(client_pool, data.component_metadata.sql, row_limit=1000, query_timeout=20)
#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#         else:
#             t2s = Text2SQL(
#                 dbname=data.dbname, 
#                 vector_client=vector_store_client,
#                 llm=llm, 
#                 llm_name=llm_name,
#                 question=data.query,
#                 filters=""
#             )
#             resp = await t2s.sql_query_generator_basic()
            
#             if not resp:
#                 await i_data.add_llm_usage(api_endpoint="report_insights", **t2s.token_usage.model_dump())
#                 raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
                
#             if resp.get("status") == "awaiting_human_input":
#                 await i_data.add_llm_usage(api_endpoint="report_insights", **t2s.token_usage.model_dump())
#                 raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

#             sql_query = resp["response"][0]["sql_query"]
#             approach = resp["response"][0]["approach"]
#             table_details = await get_table_from_sql(client_pool, sql_query)

#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#             token_usage["input_tokens"] += t2s.token_usage.input_tokens
#             token_usage["output_tokens"] += t2s.token_usage.output_tokens
#             token_usage["cached_tokens"] += t2s.token_usage.cached_tokens
        
#         print("=========== TABLE JSON =============")
#         print(table_json)
#         print("=========== TABLE JSON =============")
        
#         ct = await i_data.add_component_into_transactions(
#             component_id=component_details.id,
#             modified_by=user_details.id,
#             query=data.query,
#             component_state_id=component_last_state.component_state_id+1,
#             insights_details=json.dumps(data.component_metadata.model_dump())
#         )

#         if table_status != "success":
#             logger.error(f"SQL excetion failed - {repr(table_details.error)}")
#             raise HTTPException(detail=f"SQL excetion failed - {repr(table_details.error)}", status_code=400)
        
#         insights_generator = ReportComponent(
#             dbname=data.dbname,
#             llm=llm, 
#             llm_name=llm_name
#         )

#         inights_metadata = ""
#         if data.component_metadata.format:
#             inights_metadata = inights_metadata+f"Format: {data.component_metadata.format} \n"
#         if data.component_metadata.tone:
#             inights_metadata = inights_metadata+f"Tone: {data.component_metadata.tone} \n"
#         if data.component_metadata.word_limit:
#             inights_metadata = inights_metadata+f"Word Limit: {data.component_metadata.word_limit} \n"
#         if data.component_metadata.audience:
#             inights_metadata = inights_metadata+f"Audience: {data.component_metadata.audience} \n"
            
#         table_summary_json = await insights_generator.generate_insights_from_table(inights_metadata, table_json)
        
#         token_usage["input_tokens"] += insights_generator.token_usage.input_tokens
#         token_usage["output_tokens"] += insights_generator.token_usage.output_tokens
#         token_usage["cached_tokens"] += insights_generator.token_usage.cached_tokens
#         await i_data.add_llm_usage(transaction_id=None, api_endpoint="report_insights", **token_usage) #type: ignore
        
#         if not table_summary_json:
#             raise HTTPException(status_code=400, detail="Not able to generate table summary")
        
#         table_summary = table_summary_json["summary"]
        
#         return {
#             "component_id": component_details.id,
#             "report_id": component_details.report_id,
#             "component_name": component_details.component_name,
#             "component_description": component_details.component_description,
#             "component_type": component_details.component_type,
#             "is_active": component_details.is_active,
#             "component_state_id": ct.component_state_id,
#             "query": ct.query,
#             "table_details": json.loads(ct.table_details) if ct.table_details else None,
#             "graph_details": json.loads(ct.graph_details) if ct.graph_details else None,
#             "insights_details": json.loads(ct.insights_details) if ct.insights_details else None,
#             "component_output": {
#                 "sql": sql_query if data.query else None,
#                 "table": table_json,
#                 "table_columns": table_columns,
#                 "graph": None,
#                 "insights": table_summary
#             } 
#         }

#     raise HTTPException(detail="Unknown request", status_code=404)



# @router.post(f'/report_builder/{VERSION}/reports/chat', status_code=200)
# async def report_chats(
#     data: ReportChats,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     # client_pool = client_connection_pool
#     i_data = InternalSQLHelper(session)
#     # 1. GET DYNAMIC POOL
#     fetched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
#     if not fetched_details:
#         raise HTTPException(status_code=404, detail="Dataset Connection not found") 
#     db_details, connection_details = fetched_details
#     client_pool = await get_pool(db_details, connection_details)

#     # 2. VECTOR CLIENT
#     vector_store_client = VectorStore(vector_client)


#     user_details = await i_data.get_user_details_from_username(first_name=data.first_name, last_name=data.last_name)
#     if not user_details:
#         raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

#     db_details = await i_data.get_db_details_from_dbname(db_name=data.dbname)
#     if not db_details:
#         raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
#     report_details = await i_data.get_report_details_from_report_id(data.report_id)
#     if not report_details:
#         raise HTTPException(detail="Report does not exists nor created successfully", status_code=404)
    

#     if not data.query:
#         raise HTTPException(detail="No details found to update component", status_code=404)
        
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     # vector_connection = get_vector_db()
#     # vector_client = VectorStore(vector_connection)
#     # await vector_client.ensure_collection(data.dbname)

#     token_usage = {
#         "input_tokens": 0,
#         "output_tokens": 0,
#         "cached_tokens": 0
#     }

#     rc = ReportComponent(
#         dbname=data.dbname,
#         llm=llm,
#         llm_name=llm_name
#     )
#     possible_routes = await rc.extract_possible_routes(data.query)
#     token_usage["input_tokens"] += rc.token_usage.input_tokens
#     token_usage["output_tokens"] += rc.token_usage.output_tokens
#     token_usage["cached_tokens"] += rc.token_usage.cached_tokens
    
#     if not possible_routes:
#         raise HTTPException(status_code=400, detail="Routes were not extracted properly")
    
#     t2s_question = possible_routes["table"]["metadata"]["sql_question"] if possible_routes["table"]["is_required"] else data.query
    
#     t2s = Text2SQL(
#         dbname=data.dbname,
#         # vector_client=vector_client,
#         vector_client=vector_store_client,
#         llm=llm,
#         llm_name=llm_name,
#         question=t2s_question,
#         filters=""
#     )

#     resp = await t2s.sql_query_generator_basic()
#     token_usage["input_tokens"] += t2s.token_usage.input_tokens
#     token_usage["output_tokens"] += t2s.token_usage.output_tokens
#     token_usage["cached_tokens"] += t2s.token_usage.cached_tokens

#     if not resp:
#         await i_data.add_llm_usage(api_endpoint="report_chat", **t2s.token_usage.model_dump())
#         raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query}", status_code=400)
        
#     if resp.get("status") == "awaiting_human_input":
#         await i_data.add_llm_usage(api_endpoint="report_chat", **t2s.token_usage.model_dump())
#         raise HTTPException(detail = f"Text 2 SQL operation failed question - {data.query} - Provide more inputs to generate query properly - {resp['response']}", status_code=400)

#     sql_query = resp["response"][0]["sql_query"]
#     approach = resp["response"][0]["approach"]
#     table_details = await get_table_from_sql(client_pool, sql_query)

#     table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
#     token_usage["input_tokens"] += t2s.token_usage.input_tokens
#     token_usage["output_tokens"] += t2s.token_usage.output_tokens
#     token_usage["cached_tokens"] += t2s.token_usage.cached_tokens

#     components_output = []

#     if possible_routes["table"]["is_required"]:
#         table_component_details = await i_data.create_report_component(
#             report_id=data.report_id,
#             component_name=None,
#             component_description=None,
#             component_type="table",
#             created_by=user_details.id
#         )

#         table_component_metadata = {
#             "component_type": "table",
#             "sql": sql_query
#         } 

#         table_component_transaction = await i_data.add_component_into_transactions(
#             component_id=table_component_details.id,
#             modified_by=user_details.id,
#             query=data.query,
#             table_details=json.dumps(table_component_metadata)
#         ) 

#         components_output.append({
#             "component_id": table_component_details.id,
#             "report_id": table_component_details.report_id,
#             "component_name": table_component_details.component_name,
#             "component_description": table_component_details.component_description,
#             "component_type": "table",
#             "is_active": table_component_details.is_active,
#             "component_state_id": table_component_transaction.component_state_id,
#             "query": table_component_transaction.query,
#             "table_details": json.loads(table_component_transaction.table_details),
#             "graph_details": None,
#             "insights_details": None,
#             "component_output": {
#                 "sql": sql_query,
#                 "table": table_json,
#                 "table_columns": table_columns,
#                 "graph": None,
#                 "graph_title": None,
#                 "insights": None
#             } 
#         })

#     if possible_routes["graph"]["is_required"]:
#         df = pd.DataFrame(table_json) #type: ignore
        
#         graph_maker = GraphGenerator(df)
#         graph_maker.correct_data_()
#         graphs_list = graph_maker.generate_graphs()

#         if graphs_list:
#             graph_component_details = await i_data.create_report_component(
#                 report_id=data.report_id,
#                 component_name=None,
#                 component_description=None,
#                 component_type="graph",
#                 created_by=user_details.id
#             )

#             graph_component_metadata = {
#                 "component_type": "graph",
#                 "sql": sql_query,
#                 "title": possible_routes["graph"]["metadata"]["title"],
#                 "graph_type": graphs_list[0].get("chart_type"),
#                 "x_axis": possible_routes["graph"]["metadata"].get("x_axis"),
#                 "y_axis": possible_routes["graph"]["metadata"].get("y_axis"),
#                 "legend": None,
#                 "colo_palette": None
#             } 

#             graph_component_transaction = await i_data.add_component_into_transactions(
#                 component_id=graph_component_details.id,
#                 modified_by=user_details.id,
#                 query=data.query,
#                 graph_details=json.dumps(graph_component_metadata)
#             ) 

#             components_output.append({
#                 "component_id": graph_component_details.id,
#                 "report_id": graph_component_details.report_id,
#                 "component_name": graph_component_details.component_name,
#                 "component_description": graph_component_details.component_description,
#                 "component_type": "graph",
#                 "is_active": graph_component_details.is_active,
#                 "component_state_id": graph_component_transaction.component_state_id,
#                 "query": graph_component_transaction.query,
#                 "table_details": None,
#                 "graph_details": json.loads(graph_component_transaction.graph_details),
#                 "insights_details": None,
#                 "component_output": {
#                     "sql": sql_query,
#                     "table": None,
#                     "table_columns": None,
#                     "graph": graphs_list[:1],
#                     "graph_title": possible_routes["graph"]["metadata"]["title"],
#                     "insights": None
#                 } 
#             })


#     if possible_routes["insights"]["is_required"]:
#         insights_generator = ReportComponent(
#             dbname=data.dbname,
#             llm=llm, 
#             llm_name=llm_name
#         )

#         inights_metadata = ""

#         table_summary_json = await insights_generator.generate_insights_from_table(inights_metadata, table_json)
        
#         token_usage["input_tokens"] += insights_generator.token_usage.input_tokens
#         token_usage["output_tokens"] += insights_generator.token_usage.output_tokens
#         token_usage["cached_tokens"] += insights_generator.token_usage.cached_tokens
        
#         if table_summary_json:
#             table_summary = table_summary_json["summary"]

#             insights_component_details = await i_data.create_report_component(
#                 report_id=data.report_id,
#                 component_name=None,
#                 component_description=None,
#                 component_type="insights",
#                 created_by=user_details.id
#             )

#             insights_component_metadata = {
#                 "component_type": "insights",
#                 "sql": sql_query,
#                 "objective": None,
#                 "word_limit": possible_routes["insights"]["metadata"].get("word_limit"),
#                 "tnne": possible_routes["insights"]["metadata"].get("tone"),
#                 "format": possible_routes["insights"]["metadata"].get("format"),
#                 "audience": possible_routes["insights"]["metadata"].get("audience")
#             } 

#             insights_component_transaction = await i_data.add_component_into_transactions(
#                 component_id=insights_component_details.id,
#                 modified_by=user_details.id,
#                 query=data.query,
#                 insights_details=json.dumps(insights_component_metadata)
#             ) 

#             components_output.append({
#                 "component_id": insights_component_details.id,
#                 "report_id": insights_component_details.report_id,
#                 "component_name": insights_component_details.component_name,
#                 "component_description": insights_component_details.component_description,
#                 "component_type": "insights",
#                 "is_active": insights_component_details.is_active,
#                 "component_state_id": insights_component_transaction.component_state_id,
#                 "query": insights_component_transaction.query,
#                 "table_details": None,
#                 "graph_details": None,
#                 "insights_details": json.loads(insights_component_transaction.insights_details),
#                 "component_output": {
#                     "sql": sql_query,
#                     "table": None,
#                     "table_columns": None,
#                     "graph": None,
#                     "graph_title": None,
#                     "insights": table_summary
#                 } 
#             })

#     await i_data.add_llm_usage(api_endpoint="report_chat", llm=llm_name, **token_usage)

#     if not components_output:
#         raise HTTPException(status_code=404, detail="Not able to generate any component for the request")

#     return components_output
# ############################

# @router.post(f'/report_builder/{VERSION}/reports/generate-dashboard', status_code=200)
# async def generate_full_dashboard(
#     payload: ReportGeneration,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     # client_pool = client_connection_pool
#     i_data = InternalSQLHelper(session)
#     # 1. GET DYNAMIC POOL
#     fetched_details = await i_data.get_dataset_and_connection_details(db_name=payload.dbname)
#     if not fetched_details:
#         raise HTTPException(status_code=404, detail="Dataset Connection not found") 
#     db_details, connection_details = fetched_details
#     client_pool = await get_pool(db_details, connection_details)

#     # 2. VECTOR CLIENT
#     vector_store_client = VectorStore(vector_client)


#     # Setup Config, LLM, and Vector Client (same as before)
#     with open("app/clientConfig.yaml", "r") as f:
#         client_config_dict = yaml.safe_load(f)

#     llm_base = client_config_dict[payload.dbname]["LLM"]["SQL"]["BASE"]
#     llm_name = client_config_dict[payload.dbname]["LLM"]["SQL"]["MODEL"]
#     llm = await get_llm(base=llm_base)

#     # vector_connection = get_vector_db()
#     # vector_client = VectorStore(vector_connection)
#     # await vector_client.ensure_collection(payload.dbname)

#     storyboard_points = [s for s in payload.selectables if s.field == "storyboard_point" and s.is_selected]

#     for point in storyboard_points:
#         statement = point.option
#         comp_type = point.type
#         # comp_type = point.type or "table"

#     # 1. Extract only selected storyboard points    
#     if not storyboard_points:
#         raise HTTPException(status_code=400, detail="No components found to generate.")

#     dashboard_output = []
#     total_token_usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}

#     # 2. Iterate and Generate
#     for idx, point in enumerate(storyboard_points):
#         statement = point.option
        
#         # FIX: Check root level 'type' first (Step 4 format), then fallback to 'metadata'
#         raw_type = point.type or (point.metadata.get("type") if point.metadata else "table")
        
#         # Map 'indicator' and 'graph' to your GraphGenerator logic
#         final_processing_type = "graph" if raw_type in ["graph", "indicator"] else raw_type
        
#         try:
#             # A. SQL Generation
#             t2s = Text2SQL(dbname=payload.dbname, vector_client=vector_store_client, llm=llm, llm_name=llm_name, question=statement, filters="")
#             resp = await t2s.sql_query_generator_basic()
            
#             if not resp or resp.get("status") == "awaiting_human_input":
#                 continue

#             sql_query = resp["response"][0]["sql_query"]
            
#             # B. Data Fetching
#             table_details = await get_table_from_sql(client_pool, sql_query)
#             table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)

#             if table_status != "success":
#                 continue

#             # C. Processing based on type
#             processed_data = {
#                 "sql": sql_query,
#                 "table": table_json,
#                 "table_columns": table_columns,
#                 "graph": None,
#                 "insights": None
#             }

#             if final_processing_type == "graph":
#                 df = pd.DataFrame(table_json)
#                 graph_maker = GraphGenerator(df)
#                 graph_maker.correct_data_()
#                 processed_data["graph"] = graph_maker.generate_graphs()[:1]
                
#                 # Title generation
#                 graph_title, _ = await generate_graph_title(user_query=statement, df=df, db_name=payload.dbname, llm=llm, llm_model=llm_name)
#                 processed_data["graph_title"] = graph_title

#             elif final_processing_type == "insights":
#                 insights_generator = ReportComponent(dbname=payload.dbname, llm=llm, llm_name=llm_name)
#                 insight_res = await insights_generator.generate_insights_from_table("Business summary", table_json)
#                 processed_data["insights"] = insight_res.get("summary")

#             # D. Database Persistence
#             component_db = await i_data.create_report_component(
#                 report_id=payload.report_id,
#                 component_name=f"Component {idx+1}",
#                 component_description=statement,
#                 component_type=raw_type, # Store original type (e.g. indicator)
#                 created_by=1
#             )
            
#             # Save transaction/state
#             # await i_data.add_component_into_transactions(
#             #     component_id=component_db.id,
#             #     modified_by=1,
#             #     query=statement,
#             #     component_state_id=1,
#             #     # Route data to correct column in DB
#             #     table_details=json.dumps(processed_data) if final_processing_type == "table" else None,
#             #     graph_details=json.dumps(processed_data) if final_processing_type == "graph" else None,
#             #     insights_details=json.dumps(processed_data) if final_processing_type == "insights" else None
#             # )

#             dashboard_output.append({
#                 "component_id": component_db.id,
#                 "type": raw_type,
#                 "statement": statement,
#                 "data": processed_data
#             })

#             total_token_usage["input_tokens"] += t2s.token_usage.input_tokens
#             total_token_usage["output_tokens"] += t2s.token_usage.output_tokens

#         except Exception as e:
#             logger.error(f"Failed component {statement}: {str(e)}")
#             continue

#     return {
#         "status": "success",
#         "report_id": payload.report_id,
#         "components": dashboard_output
#     }