import pandas as pd
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.dependencies import get_db_async
# from app.databases.internal_sql_operations import AdminSQLHelper # Import the class above
from app.databases.application_sql.operations import AdminSQLHelper
from app.core.graphs.plotly.plotly_graphs_2d import get_2d_bar_chart, get_2d_line_chart, get_2d_pie_chart
from app.models import UserName, AdminDashboardRequest, FilterValueRequest

from typing import Literal, List, Dict
from fastapi import HTTPException, status

router = APIRouter(prefix="/egai/admin", tags=["Admin Dashboard"])

def to_dict(fig):
    return fig.to_json() if fig else None


ENDPOINT_ALIASES = {
    "custom_dashboard": "Custom Dashboard",
    "table": "Data Table Generation",
    "graph": "Graph",
    "insights": "Business Insights",
    "suggestions": "AI Suggestions"
}

@router.post("/admin_dashboard_filters")
async def get_filter_values(payload: FilterValueRequest, db: AsyncSession = Depends(get_db_async)):
    # 1. Authorize Admin
    helper = await authorize_admin(payload, db)
    
    # 2. Validation & Fetching
    # Since we use Literal, Pydantic handles basic "random string" rejection.
    # We add extra logic here for specific handling.
    
    result_list = []
    
    if payload.filter_type == "user_name":
        values = await helper.get_distinct_users()
        result_list = [{"label": v.title(), "value": v} for v in values]
        
    elif payload.filter_type == "db_name":
        values = await helper.get_distinct_datasets()
        result_list = [{"label": v.upper(), "value": v} for v in values]
        
    elif payload.filter_type == "api_name":
        raw_values = await helper.get_distinct_api_endpoints()
        # Apply Aliases here
        for rv in raw_values:
            label = ENDPOINT_ALIASES.get(rv.lower(), rv.replace("_", " ").title())
            result_list.append({"label": label, "value": rv})

    # 3. Final Check: If DB returned nothing (rare but possible)
    if not result_list:
        return {
            "filter_type": payload.filter_type,
            "values": [],
            "message": "No values found in database"
        }

    return {
        "filter_type": payload.filter_type,
        "values": sorted(result_list, key=lambda x: x["label"])
    }



def apply_custom_layout(fig, title_text, show_legend=True):
    """
    Applies the standardized corporate styling to any Plotly figure.
    """
    if fig is None:
        return None

    fig.update_layout(
        template="simple_white",
        margin=dict(l=0, r=0, b=0, t=10, pad=0),
        height=350,
        font=dict(
            family="open sans, Helvetica Neue, Helvetica, Arial, sans-serif"
            # color=color_palette[0]
        ),
        title=dict(
            x=0,
            y=0.96,
            font_color="#1E78B4",
            xanchor="left",
            font_size=2,
            font_weight=800
        ),
        legend_grouptitlefont=dict(
            size=12.8,
            weight=600
        ),
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            xref="container",
            yref="container",
            yanchor="auto",
            xanchor="auto",
            #                     y=-0.4,
            #                     xanchor="left",
            font_size=12,
            font_weight=400
        ),
        xaxis_title=dict(
            font_size=12.8,
            font_weight=400
        ),
        yaxis_title=dict(
            font_size=12.8,
            font_weight=400
        ),
        barcornerradius="5%",
        bargroupgap=0.2
    )
    fig.update_xaxes(tickfont=dict(size=12))
    fig.update_yaxes(tickfont=dict(size=12))
    
    return fig

def format_graph_response(kpi_name, title, df, plotly_func, **kwargs):
    """
    Standardized formatter with an extra check for zero-value data.
    """
    is_empty = df is None or df.empty
    
    # Aggregation check: If df has rows, are all the values 0?
    if not is_empty:
        # Get all columns that are numbers (int, float)
        num_cols = df.select_dtypes(include=['number']).columns
        if len(num_cols) > 0:
            # If the total sum of all numeric columns is 0, treat it as empty
            if df[num_cols].sum().sum() == 0:
                is_empty = True

    if is_empty:
        return {
            "kpi_name": kpi_name,
            "graph_title": title,
            "graph": "",
            "message": "no data available"
        }
    
    try:
        # Generate the base graph
        fig = plotly_func(df, **kwargs)
        
        # Auto Legend Logic
        auto_show_legend = True if plotly_func.__name__ == "get_2d_pie_chart" else False
        fig = apply_custom_layout(fig, title_text=title, show_legend=auto_show_legend)
        
        return {
            "kpi_name": kpi_name,
            "graph_title": title,
            "graph": fig.to_json(),
            "message": ""
        }
    except Exception as e:
        return {
            "kpi_name": kpi_name,
            "graph_title": title,
            "graph": "",
            "message": f"error: {str(e)}"
        }

async def get_safe_df(coro, columns):
    """ Executes the DB call and ensures the resulting DF has the required columns """
    data = await coro
    df = pd.DataFrame(data)
    if df.empty:
        # Re-create empty DF with headers to prevent KeyError in plotly functions
        return pd.DataFrame(columns=columns)
    return df


async def authorize_admin(payload: UserName, db: AsyncSession):
    """
    Helper function to authenticate and authorize based on your UserName model.
    """
    helper = AdminSQLHelper(db)
    
    # 1. Authentication/Registration logic
    user_details = await helper.create_or_get_user(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email_id=payload.email_id
    )

    if not user_details:
        raise HTTPException(
            detail="User does not exist nor was created successfully", 
            status_code=status.HTTP_404_NOT_FOUND
        )

    # Role-based Authorization
    if user_details.role not in ["admin", "super_admin"]:
        raise HTTPException(
            detail=f"Access denied. User '{payload.user_name}' has role '{user_details.role}' and cannot view admin dashboards.", 
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    return helper

@router.post("/overall_performance")
async def overall_performance(payload: AdminDashboardRequest, db: AsyncSession = Depends(get_db_async)):
    helper = await authorize_admin(payload, db)
    fltr = payload.filters

    # Data Fetching
    summary = await helper.get_overall_summary_kpis(fltr)
    
    df_chats = await get_safe_df(helper.get_chats_over_time(fltr), ["date", "count"])
    df_models = await get_safe_df(helper.get_llm_model_distribution(fltr), ["llm", "count"])
    df_tokens = await get_safe_df(helper.get_tokens_over_time(fltr), ["date", "total_tokens"])
    df_tokens_model = await get_safe_df(helper.get_tokens_by_model_time(fltr), ["date", "llm", "total_tokens"])
    df_cache = await get_safe_df(helper.get_cache_split(fltr), ["metric", "value"])
    df_qtypes = await get_safe_df(helper.get_question_type_distribution(fltr), ["question_type", "count"])

    return {
        "summary_kpis": [
            {"kpi_name": "total_users", "label": "Total Users", "value": summary["total_users"]},
            {"kpi_name": "total_chats", "label": "Total Chats", "value": summary["total_chats"]},
            {"kpi_name": "total_transactions", "label": "Total Transactions", "value": summary["total_transactions"]},
            {"kpi_name": "total_llm_calls", "label": "LLM Calls", "value": summary["total_llm_calls"]},
            {"kpi_name": "total_tokens", "label": "Tokens Used", "value": summary["total_tokens"]},
        ],
        "charts": [
            # PASS THE FUNCTION NAME (get_2d_line_chart), DO NOT CALL IT HERE
            format_graph_response("chats_over_time", "Chats Over Time", df_chats, 
                                  get_2d_line_chart, num_cols=["count"], date_cols=["date"]),
            
            format_graph_response("llm_calls_by_model", "LLM Calls by Model", df_models, 
                                  get_2d_bar_chart, num_cols=["count"], cat_cols=["llm"]),
            
            format_graph_response("tokens_over_time", "Total Token Usage Over Time", df_tokens, 
                                  get_2d_line_chart, num_cols=["total_tokens"], date_cols=["date"]),
            
            format_graph_response("token_usage_by_model_time", "Token Usage by Model Over Time", df_tokens_model, 
                                  get_2d_line_chart, num_cols=["total_tokens"], date_cols=["date"]),
            
            format_graph_response("cached_vs_non_cached", "Cached vs Non-Cached Token Usage", df_cache, 
                                  get_2d_pie_chart, numerical_columns=["value"], categorical_columns=["metric"]),
            
            format_graph_response("question_type_dist", "Question Type Distribution", df_qtypes, 
                                  get_2d_pie_chart, numerical_columns=["count"], categorical_columns=["question_type"]),
        ]
    }

@router.post("/user_dataset_analytics")
async def user_dataset_analytics(payload: AdminDashboardRequest, db: AsyncSession = Depends(get_db_async)):
    helper = await authorize_admin(payload, db)
    fltr = payload.filters

    # Data Fetching with safe column injection
    df_roles = await get_safe_df(helper.get_user_role_distribution(fltr), ["role", "count"])
    df_signups = await get_safe_df(helper.get_user_signup_trend(fltr), ["date", "count"])
    df_dau = await get_safe_df(helper.get_daily_active_users(fltr), ["date", "active_users"])
    df_chats_user = await get_safe_df(helper.get_chats_per_user(fltr), ["email_id", "chat_count"])
    df_ds_usage = await get_safe_df(helper.get_dataset_usage_stats(fltr), ["db_name", "transaction_count"])
    # df_token_dist = await get_safe_df(helper.get_token_dist_per_tx(fltr), ["transaction_id", "total_tokens"])

    return {
        "charts": [
            format_graph_response("users_by_role", "Users by Role Distribution", df_roles, 
                                  get_2d_pie_chart, numerical_columns=["count"], categorical_columns=["role"]),
            
            format_graph_response("user_signups", "User Signups Over Time", df_signups, 
                                  get_2d_line_chart, num_cols=["count"], date_cols=["date"]),
            
            format_graph_response("dau_trend", "Daily Active Users (DAU)", df_dau, 
                                  get_2d_line_chart, num_cols=["active_users"], date_cols=["date"]),
            
            format_graph_response("chats_per_user", "Total Chats per User", df_chats_user, 
                                  get_2d_bar_chart, num_cols=["chat_count"], cat_cols=["email_id"]),
            
            format_graph_response("ds_transactions", "Transactions per Dataset", df_ds_usage, 
                                  get_2d_bar_chart, num_cols=["transaction_count"], cat_cols=["db_name"]),
            
            # format_graph_response("token_distribution_hist", "Token Usage Distribution", df_token_dist, 
            #                       get_2d_histogram, num_cols=["total_tokens"]),
        ]
    }
