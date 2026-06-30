from fastapi import APIRouter, Depends, HTTPException
from app.models import ResetChat, DashboardToConversation, CustomDashboard
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.dependencies import (
    get_db_async,
    get_vector_client,
    get_nosql_client,
    get_pool,
)
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from app.databases.application_nosql.models import Plotly_Graph
# from app.core.table_from_sql import get_table_from_sql_parallel
from app.appConfig import settings
from app.core.graphs.plotly.custom_dashboard import generate_custom_kpi_graphs
import pandas as pd
import asyncio
from app.core.helper import (
    log_sql_data,
    get_drilldown_features,
    format_percentage_columns,
    is_percentage_column,
    format_plotly_percentage_graph,
)
import yaml
import json
import os
from app.core.dashboards.introductions import get_column_stats, get_updated_metadata
from .base_check import perform_base_check
from app.core.llms import get_llm
from app.core.dashboards.custom_dashboard import GenerateCustomDashboard
from app.core.graphs.plotly.base import generate_graphs
from app.core.graphs.echarts.graphs import GraphGenerator
from app.databases.client_sql.operations import get_table_from_sql, get_table_from_sql_parallel, get_table_and_status_and_columns
from app.databases.vector.operations import VectorStore

router = APIRouter(prefix="/egai", tags=["Dashboards"])


logger = get_logger()


@router.post('/auto_dashboard', status_code=200) # Base Dashboards for HPE
async def custom_kpi_setup(
    data: ResetChat,
    session: AsyncSession = Depends(get_db_async)
): 
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)
    # Database Connections
    # client_pool = client_connection_pool
    # nosql_client = get_nosql_client()
    nosql_helper = NOSQLHelper()

    # user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    # if not user_details:
    #     raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    # db_details = await i_data.create_or_get_db(db_name=data.dbname)
    # if not db_details:
    #     raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    dashboards_data = await i_data.get_dashboards_data_by_dbid(db_details.id)
    if not dashboards_data:
        logger.error(f"No daashboard queries found for {data.dbname}")
        raise HTTPException(status_code=404, detail=f"No daashboard queries found for {data.dbname}")

    sql_queries = [s.sql_code for s in dashboards_data]
    query_results = await get_table_from_sql_parallel(
        client_pool, 
        data.dbname,
        sql_queries, 
        settings.client_connection_pool_per_worker,
        row_limit=None,
        query_timeout=300
    )

    print('sql_queries...........', sql_queries)

    results = []

    with open("app/clientConfig.yaml", 'r') as f:
        config_dict = yaml.safe_load(f)

    graph_type = config_dict[data.dbname]["GRAPH_TYPE"]

    for dd, qr in zip(dashboards_data, query_results):
        if not qr:
            continue
        
        user_query = dd.query
        table_json, table_status, table_columns = get_table_and_status_and_columns(qr)
        
        if table_status!="success": # case where query has resulted in error
            logger.warning(f"Results not fetched for query - {dd.query}")
            continue
        
        if not table_json: # case where query has resulted no data (Empty data)
            logger.warning(f"No data foun for query - {dd.query}")
            continue
        
        df = pd.DataFrame(table_json) # type: ignore
        graph_details = {"graph_type": dd.graph_type, "graph_label": dd.graph_label}
        
        try:
            if graph_type == "echarts": 
                graph_maker = GraphGenerator(df)
                graph_maker.correct_data_()
                graph_list = graph_maker.generate_graphs()

                results.append({
                    "user_query": user_query,
                    "sql": qr.sql,
                    "table": table_json,
                    "table_columns": table_columns,
                    "chart_type": "auto",
                    "chart_sub_type": "auto",
                    "echarts": graph_list[0],
                    "graph_title": dd.graph_label,
                    "status": 200,
                    "status_message": "Success",
                    "approach": dd.approach
                })

            else:
                graph_list, user_query = await asyncio.to_thread(generate_custom_kpi_graphs, user_query, df, graph_details)


                percentage_columns = [
                    str(column_name)
                    for column_name in df.columns
                    if is_percentage_column(column_name)
                ]

                graph_list = [
                    format_plotly_percentage_graph(
                        graph_item,
                        percentage_columns,
                    )
                    for graph_item in graph_list
                ]
                results.append({
                    "user_query": user_query,
                    "sql": qr.sql,
                    "table": table_json,
                    "table_columns": table_columns,
                    "chart_type": "auto",
                    "chart_sub_type": "auto",
                    "plotlycharts": graph_list[0],
                    "graph_title": None,
                    "status": 200,
                    "status_message": "Success",
                    "approach": dd.approach
                })
    

        except Exception as e:
            logger.warning(f"Graph not generated successfully for query - {dd.query} - {repr(e)}")
                        
    new_results = []
    
    ############# BELOW CODE NEEDS TO BE OPTIMIZED - IT SHOULD BE BULK INSERT #############
    for r in results:
        transaction_id = await log_sql_data(
            i_data, 
            query=r["user_query"],
            db_id=db_details.id,
            chat_id=None,
            sql_query=r["sql"],
            approach=r["approach"],
            filters_json=None,
            raw_response=None,
            question_type="complete"
        )
        r["query_key"] = str(transaction_id)

        await nosql_helper.record_table(
            transaction_id=transaction_id, 
            table=r["table"],
            approach=r["approach"]
        )

        plotly_graphs = []
        
        graph_to_append = Plotly_Graph(
                graph_id=r["echarts"]["graph_id"],
                plotly_code=r["echarts"]["graph"],
                chart_type=r["echarts"]["type"]
            ) if graph_type == "echarts" else Plotly_Graph(
                graph_id=r["plotlycharts"]["graph_id"],
                plotly_code=r["plotlycharts"]["graph"],
                chart_type=r["plotlycharts"]["type"]
            )

        plotly_graphs.append(graph_to_append)
        
        await nosql_helper.record_graph(
            transaction_id=int(r["query_key"]),
            graphs=plotly_graphs
        )

        # Return a formatted copy while preserving the numeric table used for
        # storage, graph generation, sorting, and calculations.
        response_result = r.copy()
        response_result["table"] = format_percentage_columns(
            r["table"]
        )
        new_results.append(response_result)
    ############################ OPTIMIZE ABOVE CODE ####################################

    if not new_results:
        logger.error(f"Not abale to generate any response for {data.dbname}")
        raise HTTPException(status_code=404, detail=f"Not abale to generate any response for {data.dbname}")
    
    return {
        "data": new_results,
        "parent_id": "",
        "status_message": "Success",
        "status": 200
    }



@router.post("/setup_introduction_page", status_code=200)
async def create_base_introduction_page(
    data: ResetChat,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    # user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    # if not user_details:
    #     raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    # db_details = await i_data.create_or_get_db(db_name=data.dbname)
    # if not db_details:
    #     raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    introduction_meta_base_path = f"business_data/{data.dbname}"
    check_path_existance = os.path.exists(introduction_meta_base_path)
    if not check_path_existance:
        os.makedirs(introduction_meta_base_path, exist_ok=True)

    with open("app/clientConfig.yaml") as f:
        config_dict = yaml.safe_load(f)

    available_tables = config_dict[data.dbname]["DATABASE"]["available_tables"]
    
    check_file_existance = os.path.exists(introduction_meta_base_path+"/introduction_meta.json")
    
    if not check_file_existance:
        output_format = [
            {
                "row_num": 1,
                "columns": [
                    {
                        "query_key": "",
                        "type": "text",
                        "space_occupy": 12,
                        "height": 185,
                        "text_data": "",
                        "plotlycharts": "",
                        "insight": "",
                        "header": data.dbname.replace("_", " ")
                    }
                ]
            },
            {
                "row_num": 2,
                "columns": [
                    {
                        "query_key": "",
                        "type": "text",
                        "space_occupy": 12,
                        "height": 360,
                        "text_data": "",
                        "plotlycharts": "",
                        "insight": "",
                        "header": "Key Definitions and Formulas"
                    }
                ]
            }
        ]

        sql_query_table_mappings = [
            {
                "table": t,
                "sql_query": f"SELECT TOP 100 * FROM {t}"
            }
            for t in available_tables
        ]

        sql_queries = [s["sql_query"] for s in sql_query_table_mappings]
        # base_tables = await get_table_from_sql_parallel(client_pool, sql_queries)
        base_tables = await get_table_from_sql_parallel(
            client_pool, 
            data.dbname,
            sql_queries, 
            settings.client_connection_pool_per_worker,
        )
        results = [get_table_and_status_and_columns(b) for b in base_tables]

        columns_metadata = []
        for t, r in zip(available_tables, results):
            if r[1] =="success":
                results = await get_column_stats(data.dbname, client_pool, t, r[2])
                cm = {"table_name": t,"columns": results} 
                columns_metadata.append(cm)

        tables_output_format = [
            {
                "row_num": i+1+len(output_format),
                "columns": [
                    {
                        "query_key": "",
                        "type": "table",
                        "space_occupy": 12,
                        "height": 300,
                        "text_data": "",
                        "plotlycharts": "",
                        "insight": "",
                        "header": t.replace("_"," "),
                        "about_this_data": "",
                        "metadata":[],
                        "table": []
                    }
                ]
            }  for i, t in enumerate(available_tables)
        ]
        output_format = output_format+tables_output_format

        complete_json = {
            "output": output_format,
            "sql_queries": sql_query_table_mappings,
            "columns_metadata": columns_metadata
        }
    
        with open(f"{introduction_meta_base_path}/introduction_meta.json", "w") as f:
            json.dump(complete_json, f, indent=2, separators=(',', ':'))

        return complete_json
    return {}


@router.post('/hpe_custom_dashboard', status_code=200) # Introduction Page for HPE
async def get_introduction_page(
    data: ResetChat,
    session: AsyncSession = Depends(get_db_async)
): 
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    # user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    # if not user_details:
    #     raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    # db_details = await i_data.create_or_get_db(db_name=data.dbname)
    # if not db_details:
    #     raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    with open(f"business_data/{data.dbname}/introduction_meta.json") as f:
        introduction_meta = json.load(f)

    # sql_query_table_mappings = introduction_meta["sql_queries"]
    # sql_queries = [s["sql_query"] for s in sql_query_table_mappings]

    sql_queries = []
    with open(f"business_data/{data.dbname}/tables/tables.json") as f:
        tables = json.load(f)
    
    for t in tables:
        cols = ", ".join(t["columns"])                    
        sql_queries.append(f"SELECT TOP 50 {cols} FROM {t['name']}")

    # base_tables = await get_table_from_sql_parallel(client_pool, sql_queries, row_limit=100) 
    base_tables = await get_table_from_sql_parallel(
        client_pool, 
        data.dbname,
        sql_queries, 
        settings.client_connection_pool_per_worker,
        row_limit=100
    )
    results = [get_table_and_status_and_columns(b) if b else ([], "error", {}) for b in base_tables]
    
    output = introduction_meta["output"]
    intro_text = output[:2]

    columns_metadata = introduction_meta["columns_metadata"]

    with open("app/clientConfig.yaml") as f:
        config_dict = yaml.safe_load(f)


    tables_data = []
    for part, r in zip(output[2:], results):

        # part["columns"][0]["metadata"] = await get_updated_metadata(
        #     data.dbname, client_pool, cm["table_name"], r[2], introduction_meta
        # ) #cm["columns"]

            #         {
            #     "column_name": c,
            #     "description": None,
            #     "numeric_stats": numeric_stats,
            #     "categorical_stats": categorical_stats,
            #     "unique_external_ref": unique_external_ref,
            #     "comment_stats": None
            # }

        # if r[1] != "success":
        # logger.warning(f"Data not fetched for table - {cm['table_name']}")

        # part["columns"][0]["metadata"] = []

        part["columns"][0]["metadata"] = []
        
        try:
            part["columns"][0]["metadata"] = [cm for cm in columns_metadata if cm["table_name"] == part["columns"][0]["table_name"]][0]["columns"]
        except Exception as e:
            logger.warning(f"Metadata not found for table - {part['columns'][0]['header']} - {str(e)}")
        
        part["columns"][0]["about_this_data"] = part["columns"][0]["about_this_data"].format(last_refresh_date=config_dict[data.dbname]["DATA_REFRESH"]["LAST_REFRESH_DATE"])
        part["columns"][0]["table"] = (
            format_percentage_columns(r[0])
        )
        part["columns"][0]["table_columns"] = r[2]
        tables_data.append(part)
    
    return {
        "data": intro_text+tables_data,
        "status_message": 200,
        "status": "Success"
    }


@router.post('/getLastRefreshDate', status_code=200)
async def getLastRefreshDate(data: ResetChat):
    try:
        with open("app/clientConfig.yaml", 'r') as f:
            config_content = f.read()
            config_dict = yaml.safe_load(config_content)

        last_refresh_date = config_dict[data.dbname]["LAST_REFRESH_DATE"]
        
        logger.info("Health check Successful")
        return {"status": 200, "status_message": "success", "last_refresh_date": last_refresh_date}
    except Exception as e:
        logger.error("Error in get_last_refresh_date: %s", str(e), exc_info=True)
        raise HTTPException(detail="failure", status_code=400)
    


@router.post("/navigation/dashboardToConversation", status_code=201)
async def navigate_dashboard_to_conversation(
    data: DashboardToConversation,
    session: AsyncSession = Depends(get_db_async)
): 
    # Database Connections
    # client_pool = client_connection_pool
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    # nosql_client = get_nosql_client()
    nosql_helper = NOSQLHelper()

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
        logger.error("Dashboard question not found with provided Query Key")
        raise HTTPException(detail="Dashboard question not found with provided Query Key", status_code=404)

    transaction_details_nosql = await nosql_helper.get_transaction(data.transaction_id)

    if not transaction_details_nosql:
        raise HTTPException(detail="Data was not stored in NOSQL database properly", status_code=404)

    if not transaction_details_nosql:
        raise HTTPException(detail="Table data was not stored in NOSQL database properly", status_code=404)
    
    table_keys = transaction_details_nosql.table[0].keys()
    table_columns = {f"column_{k}": v for k, v in enumerate(table_keys)}

    query_details = await i_data.get_query_details_from_query_id(query_id=transaction_details.query_id)
    if not query_details:
        raise HTTPException(detail="Query not saved properly", status_code=400)
    
    sql_details = await i_data.get_sql_details_from_id(sql_id=transaction_details.sql_id)
    if not sql_details:
        raise HTTPException(detail="SQL not saved properly", status_code=400)
    
    # Transaction
    new_transaction_details = await i_data.create_transaction(
        db_id=db_details.id,
        query_id=query_details.id,
        sql_id=sql_details.id,
        chat_id=data.chat_id,
        filters="",
        approach=transaction_details.approach,
        question_type="complete",
        raw_response=json.dumps(
            {
                "sql_query": sql_details.sql_code, 
                "approach": transaction_details.approach
            }
        )
    )

    await nosql_helper.record_table(
        new_transaction_details.id, 
        transaction_details_nosql.table, 
        new_transaction_details.approach
    )

    # Graphs
    graphs_list = []
    if transaction_details_nosql.graphs:
        await nosql_helper.record_graph(
            transaction_id=new_transaction_details.id,
            graphs=transaction_details_nosql.graphs
        )
        for graph in transaction_details_nosql.graphs:
            graphs_list.append({
                "type": graph.chart_type,
                "graph_id": graph.graph_id,
                "graph": graph.plotly_code,
            })

    drilldown_features_mappings_list = get_drilldown_features(
        data.dbname, 
        pd.DataFrame(transaction_details_nosql.table)
    )

    # Keep the copied/stored table numeric and format only the API response.
    response_table = format_percentage_columns(
        transaction_details_nosql.table
    )

    return {
        "query_key": str(new_transaction_details.id),
        "user_query": query_details.user_query,
        "sql": sql_details.sql_code,
        "table": response_table,
        "table_columns": table_columns,
        "plotlycharts": graphs_list,
        "drilldown_features": drilldown_features_mappings_list,
        "insights": [],
        "consolidated_insights": "",
        "suggestions": [],
        "status": 200,
        "status_message": "Success",
        "approach":transaction_details.approach
    }


@router.post('/customized_dashboard', status_code=200)
async def generate_custom_dashboard(
    data: CustomDashboard,
    session: AsyncSession = Depends(get_db_async)
):
    # Database Connections
    # client_pool = client_connection_pool
    i_data = InternalSQLHelper(session)

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    # user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    # if not user_details:
    #     raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    # db_details = await i_data.create_or_get_db(db_name=data.dbname)
    # if not db_details:
    #     raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)
    
    with open("app/clientConfig.yaml", "r") as f:
        client_config_dict = yaml.safe_load(f)

    llm_base = client_config_dict[data.dbname]["LLM"]["SQL"]["BASE"]
    llm_name = client_config_dict[data.dbname]["LLM"]["SQL"]["MODEL"]
    llm = await get_llm(base=llm_base)

    graph_type = client_config_dict[data.dbname]["GRAPH_TYPE"]

    vector_client = await get_vector_client()
    vector_db = VectorStore(vector_client)
    await vector_db.ensure_collection(data.dbname)

    cust_dash = GenerateCustomDashboard(
        data.dbname,
        llm, 
        llm_name,
        data.user_query,
        vector_client = vector_db
    )

    resp_sqls = await cust_dash.get_custom_dashboard_queries()

    await i_data.add_llm_usage(
        api_endpoint="custom_dashboard", 
        llm=llm_name, 
        **cust_dash.token_usage.model_dump()
    )
    
    if not resp_sqls:
        raise HTTPException(status_code=400, detail="queries not generated successfully")
    
    sqls = resp_sqls["sql_queries"]
    sql_queries = [i["sql"] for i in sqls]

    # query_results = await get_table_from_sql_parallel(
    #     client_pool,
    #     sql_queries
    # )
    query_results = await get_table_from_sql_parallel(
        client_pool, 
        data.dbname, 
        sql_queries, 
        settings.client_connection_pool_per_worker
    )

    kpi_view_questions = []
    analytical_view_questions = []

    for r, qr in zip(sqls, query_results):
        if not qr:
            logger.warning(f"Data not fetched for query - {r['sql']}")
            continue
        table_json, table_status, table_columns = get_table_and_status_and_columns(qr)
        
        if table_json and table_status=="success":
            df = pd.DataFrame(table_json)


            percentage_columns = [
                str(column_name)
                for column_name in df.columns
                if is_percentage_column(column_name)
            ]
            if graph_type == "echarts":
                graph_maker = GraphGenerator(df)
                graph_maker.correct_data_()
                graph_list = graph_maker.generate_graphs()
                
                if r["query_type"] == "kpi_view":
                    kpi_view_questions.append({
                        "user_query": r["title"],
                        "sql": r["sql"],
                        "table_columns": table_columns,
                        "table": format_percentage_columns(table_json),
                        "chart_type": "auto",
                        "chart_sub_type": "auto",
                        "echarts": graph_list[0] if graph_list else "",
                        "graph_title": r["title"],
                        "insights": "",
                        "consolidated_insights": ""
                    })
                    
                else:
                    analytical_view_questions.append({
                        "user_query": r["title"],
                        "sql": r["sql"],
                        "table_columns": table_columns,
                        "table": format_percentage_columns(table_json),
                        "chart_type": "auto",
                        "chart_sub_type": "auto",
                        "echarts": graph_list[0] if graph_list else "",
                        "graph_title": r["title"],
                        "insights": "",
                        "consolidated_insights": ""
                    })
            else:
                graph_list, token_usage_dict = await generate_graphs(
                    user_query=r["title"], 
                    df=df, 
                    db_name=data.dbname, 
                    llm = llm_name, 
                    al_graph_title=r["title"]
                )
                

                graph_list = [
                    format_plotly_percentage_graph(
                        graph_item,
                        percentage_columns,
                    )
                    for graph_item in graph_list
                ]
                if r["query_type"] == "kpi_view":
                    kpi_view_questions.append({
                        "user_query": r["title"],
                        "sql": r["sql"],
                        "table_columns": table_columns,
                        "table": format_percentage_columns(table_json),
                        "chart_type": "auto",
                        "chart_sub_type": "auto",
                        "plotlycharts": graph_list[0] if len(graph_list) >= 1 else "",
                        "graph_title": None,
                        "insights": "",
                        "consolidated_insights": ""
                    })
                    
                else:
                    analytical_view_questions.append({
                        "user_query": r["title"],
                        "sql": r["sql"],
                        "table_columns": table_columns,
                        "table": format_percentage_columns(table_json),
                        "chart_type": "auto",
                        "chart_sub_type": "auto",
                        "plotlycharts": graph_list[0] if len(graph_list) >= 1 else "",
                        "graph_title": None,
                        "insights": "",
                        "consolidated_insights": ""
                    })

    return {
        "status_message": "Success",
        "status": "200",
        "time_stamp":"current_time",
        "categories_dict": [],
        'user_query' : data.user_query,
        "custom_query_key": "1",
        'question': {
            "numeric_question": kpi_view_questions,
            "graph_question": analytical_view_questions
        }
    }













