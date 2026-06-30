from datetime import date, datetime
from bson import ObjectId
import math
import numpy as np
from decimal import Decimal
import pandas as pd
from app.models import ConversationFilter
from typing import Any, List, Optional
import json
import difflib
# from app.databases.client_sql.operations import QueryResult
# from app.databases.internal_sql_operations  import InternalSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
import os
import re
from app.logger import get_logger
from functools import lru_cache
from pathlib import Path
from .prompts import PromptGetter


logger = get_logger(__name__)

#changes made to this file are to be reflected in app/routers/graphs.py as well
def format_graph_axis_title(title):
    """
    Keep already readable titles unchanged.

    Convert CamelCase or PascalCase titles into readable titles.

    Examples:
        DeviceBrowser -> Device Browser
        CheckoutAbandonmentRate -> Checkout Abandonment Rate
        LeadTimeBand -> Lead Time Band

    Already formatted:
        Checkout Abandonment by Device and Browser
        remains unchanged.
    """

    if not isinstance(title, str):
        return title

    title = title.strip()

    if not title:
        return title

    # The title already contains spaces and is considered formatted.
    if " " in title:
        return title

    # Handle acronym-to-word boundaries:
    # MSCChannel -> MSC Channel
    formatted_title = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])",
        " ",
        title
    )

    # Handle lowercase/digit-to-uppercase boundaries:
    # DeviceBrowser -> Device Browser
    # Rate2Value -> Rate2 Value
    formatted_title = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        " ",
        formatted_title
    )

    return formatted_title


def format_plotly_axis_titles(graph):
    """
    Format x-axis and y-axis titles inside a Plotly graph dictionary.
    """

    if not isinstance(graph, dict):
        return graph

    layout = graph.get("layout")

    if not isinstance(layout, dict):
        return graph

    # Covers xaxis, yaxis, xaxis2, yaxis2, etc.
    for axis_name, axis_config in layout.items():
        if not re.fullmatch(r"[xy]axis\d*", axis_name):
            continue

        if not isinstance(axis_config, dict):
            continue

        title_config = axis_config.get("title")

        # Plotly normally stores it as:
        # "title": {"text": "DeviceBrowser"}
        if isinstance(title_config, dict):
            current_title = title_config.get("text")

            if isinstance(current_title, str):
                formatted_title = format_graph_axis_title(current_title)

                print(
                    f"[HELPER AXIS FORMAT] "
                    f"{axis_name}: '{current_title}' -> '{formatted_title}'"
                )

                title_config["text"] = formatted_title

        # Handle older Plotly structures where the title may be a string.
        elif isinstance(title_config, str):
            formatted_title = format_graph_axis_title(title_config)

            print(
                f"[HELPER AXIS FORMAT] "
                f"{axis_name}: '{title_config}' -> '{formatted_title}'"
            )

            axis_config["title"] = formatted_title

    return graph
###changes end


# Percentage-response formatting configuration.
#
# These utilities are intentionally separate from make_json_safe().
# They should be called only when building the final API response so that
# DataFrames, graphs, sorting, aggregation, and calculations remain numeric.
PERCENTAGE_COLUMN_TERMS = (
    "percentage",
    "percent",
    "pct",
    "rate",
    "share",
    "ratio",
    "conversion",
    "abandonment",
    "dropoff",
    "completion",
)

# Common non-percentage fields that may contain words such as "rate".
# Add dataset-specific exclusions here if required.
NON_PERCENTAGE_COLUMN_TERMS = (
    "exchange_rate",
    "interest_rate_amount",
    "room_rate",
    "freight_rate",
    "tax_rate_amount",
    "unit_rate",
    "price_rate",
)


def _normalize_metric_name(column_name: Any) -> str:
    """
    Normalize a response key or column name for percentage detection.

    Examples:
        CheckoutAbandonmentRate -> checkout_abandonment_rate
        Drop-Off Percentage     -> drop_off_percentage
        conversion_pct          -> conversion_pct
    """
    if not isinstance(column_name, str):
        return ""

    normalized_name = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        column_name.strip(),
    )
    normalized_name = re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        normalized_name,
    )

    return normalized_name.lower().strip("_")


def is_percentage_column(column_name: Any) -> bool:
    """
    Return True only when a response field explicitly represents
    a percentage, rate, share, ratio, or pct metric.

    Examples:
        AbandonmentCount         -> False
        AbandonmentRatePercent   -> True
        ConversionRate           -> True
        DropOffPercentage        -> True
        PurchaseShare            -> True
        CompletionCount          -> False
    """
    normalized_name = _normalize_metric_name(column_name)

    if not normalized_name:
        return False

    if any(
        excluded_term in normalized_name
        for excluded_term in NON_PERCENTAGE_COLUMN_TERMS
    ):
        return False

    tokens = set(normalized_name.split("_"))

    percentage_tokens = {
        "percentage",
        "percent",
        "pct",
        "rate",
        "share",
        "ratio",
    }

    return bool(tokens.intersection(percentage_tokens))


def format_percentage_value(value: Any) -> Any:
    """
    Append '%' to a percentage value without multiplying it by 100.

    Examples:
        24.5       -> "24.5%"
        Decimal(5) -> "5%"
        "18.20"    -> "18.2%"
        "42%"      -> "42%"

    Non-numeric values are returned unchanged.
    """
    if value is None or isinstance(value, (bool, np.bool_)):
        return value

    if isinstance(value, str):
        cleaned_value = value.strip()

        if not cleaned_value:
            return value

        if cleaned_value.endswith("%"):
            return cleaned_value

        # Remove comma separators before validating a numeric string.
        numeric_text = cleaned_value.replace(",", "")

        try:
            numeric_value = float(numeric_text)
        except (TypeError, ValueError):
            return value

    elif isinstance(
        value,
        (int, float, Decimal, np.integer, np.floating),
    ):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            return value

    else:
        return value

    if math.isnan(numeric_value) or math.isinf(numeric_value):
        return None

    rounded_value = round(numeric_value, 2)

    if rounded_value == 0:
        rounded_value = 0.0

    if rounded_value.is_integer():
        formatted_value = str(int(rounded_value))
    else:
        formatted_value = (
            f"{rounded_value:.2f}"
            .rstrip("0")
            .rstrip(".")
        )

    return f"{formatted_value}%"


def format_percentage_columns(table_data: Any) -> Any:
    """
    Append '%' to percentage columns in table-style API data.

    Expected input:
        [
            {"LeadTimeBand": "0-7 Days", "ConversionRate": 24.56},
            {"LeadTimeBand": "8-30 Days", "ConversionRate": 31.20},
        ]

    This function returns a new structure and does not mutate the input.
    """
    if not isinstance(table_data, list):
        return table_data

    formatted_rows = []

    for row in table_data:
        if not isinstance(row, dict):
            formatted_rows.append(row)
            continue

        formatted_row = {}

        for column_name, value in row.items():
            if is_percentage_column(column_name):
                formatted_row[column_name] = format_percentage_value(value)
            else:
                formatted_row[column_name] = value

        formatted_rows.append(formatted_row)

    return formatted_rows


def format_percentage_response(data: Any) -> Any:
    """
    Recursively format percentage fields in a final API response payload.

    Use this only immediately before returning the response. Do not use it
    before graph generation, calculations, sorting, aggregation, or database
    persistence because formatted percentage values are strings.

    Example:
        response = format_percentage_response(response)
        return response
    """
    if isinstance(data, list):
        return [
            format_percentage_response(item)
            for item in data
        ]

    if isinstance(data, dict):
        formatted_data = {}

        for key, value in data.items():
            if is_percentage_column(key):
                if isinstance(value, list):
                    formatted_data[key] = [
                        format_percentage_value(item)
                        for item in value
                    ]
                elif isinstance(value, dict):
                    formatted_data[key] = format_percentage_response(value)
                else:
                    formatted_data[key] = format_percentage_value(value)
            else:
                formatted_data[key] = format_percentage_response(value)

        return formatted_data

    return data



def _append_percent_to_plotly_hover(
    hovertemplate: Any,
    axis_variable: str,
    percentage_columns: set[str],
) -> str:
    """
    Add % only to percentage values inside a Plotly hover template.
    """
    axis_formatted_token = f"%{{{axis_variable}:.2f}}%"

    if not isinstance(hovertemplate, str) or not hovertemplate:
        return (
            axis_formatted_token
            + "<extra>%{fullData.name}</extra>"
        )

    updated_hover = re.sub(
        rf"%\{{{re.escape(axis_variable)}(?::[^}}]+)?\}}%?",
        axis_formatted_token,
        hovertemplate,
        count=1,
    )

    for percentage_column in percentage_columns:
        pattern = re.compile(
            rf"({re.escape(percentage_column)}=)"
            rf"(%\{{customdata\[(\d+)\](?::[^}}]+)?\}})%?"
        )

        def replace_customdata(match):
            return (
                f"{match.group(1)}"
                f"%{{customdata[{match.group(3)}]:.2f}}%"
            )

        updated_hover = pattern.sub(
            replace_customdata,
            updated_hover,
        )

    return updated_hover


def format_plotly_percentage_graph(
    graph_item: Any,
    percentage_columns: list[str],
) -> Any:
    """
    Add percentage display formatting to Plotly graph JSON while keeping
    underlying values numeric.

    A global axis suffix is added only when every measure plotted on that
    axis is percentage-based. Mixed percentage/count charts therefore keep
    count values unmodified.
    """
    if not percentage_columns or not isinstance(graph_item, dict):
        return graph_item

    graph_value = graph_item.get("graph")

    if isinstance(graph_value, str):
        try:
            graph_dict = json.loads(graph_value)
            graph_was_string = True
        except (TypeError, ValueError, json.JSONDecodeError):
            return graph_item
    elif isinstance(graph_value, dict):
        graph_dict = graph_value
        graph_was_string = False
    else:
        return graph_item

    if not isinstance(graph_dict, dict):
        return graph_item

    percentage_column_set = {
        str(column_name)
        for column_name in percentage_columns
    }

    traces = graph_dict.get("data", [])
    layout = graph_dict.setdefault("layout", {})

    if not isinstance(traces, list):
        traces = []

    if not isinstance(layout, dict):
        layout = {}
        graph_dict["layout"] = layout

    axis_trace_types = {"x": [], "y": []}

    def trace_is_percentage(trace: dict) -> bool:
        """
        Detect whether the plotted trace itself represents a percentage metric.

        Do not inspect hovertemplate because hovertemplate may contain percentage
        fields only as contextual information, even when the actual plotted trace
        is a count such as CheckoutSessions or AbandonedCheckouts.
        """
        candidates = [
            trace.get("name"),
            trace.get("legendgroup"),
        ]

        title = trace.get("title")

        if isinstance(title, dict):
            candidates.append(title.get("text"))
        elif isinstance(title, str):
            candidates.append(title)

        for candidate in candidates:
            if not isinstance(candidate, str):
                continue

            clean_candidate = re.sub(
                r"<[^>]+>",
                "",
                candidate,
            ).strip()

            if (
                clean_candidate in percentage_column_set
                or is_percentage_column(clean_candidate)
            ):
                return True

        return False

    for trace in traces:
        if not isinstance(trace, dict):
            continue

        trace_type = str(trace.get("type", "")).lower()
        is_percentage_trace = trace_is_percentage(trace)

        # KPI / gauge / indicator
        if trace_type == "indicator":
            title = trace.get("title")
            title_text = ""

            if isinstance(title, dict):
                title_text = str(title.get("text", ""))
            elif isinstance(title, str):
                title_text = title

            if (
                is_percentage_trace
                or is_percentage_column(title_text)
                or any(
                    percentage_column in title_text
                    for percentage_column in percentage_column_set
                )
            ):
                number_config = trace.setdefault("number", {})
                if isinstance(number_config, dict):
                    number_config["suffix"] = "%"
                    number_config.setdefault("valueformat", ".2f")
            continue

        # Pie / donut
        if trace_type == "pie":
            if is_percentage_trace:
                trace["texttemplate"] = "%{label}: %{value:.2f}%"
                trace["hovertemplate"] = (
                    "%{label}: %{value:.2f}%<extra></extra>"
                )
            continue

        orientation = trace.get("orientation")
        value_axis = "x" if orientation == "h" else "y"
        axis_trace_types[value_axis].append(is_percentage_trace)

        if not is_percentage_trace:
            continue

        if value_axis == "x":
            trace["texttemplate"] = "%{x:.2f}%"
            trace["hovertemplate"] = _append_percent_to_plotly_hover(
                trace.get("hovertemplate"),
                axis_variable="x",
                percentage_columns=percentage_column_set,
            )
        else:
            trace["texttemplate"] = "%{y:.2f}%"
            trace["hovertemplate"] = _append_percent_to_plotly_hover(
                trace.get("hovertemplate"),
                axis_variable="y",
                percentage_columns=percentage_column_set,
            )

    # Only percentage-only axes receive a ticksuffix.
    for axis_name, flags in axis_trace_types.items():
        if flags and all(flags):
            axis_config = layout.setdefault(f"{axis_name}axis", {})

            if isinstance(axis_config, dict):
                axis_config["ticksuffix"] = "%"
                axis_config.setdefault("hoverformat", ".2f")

    result_item = dict(graph_item)

    if graph_was_string:
        result_item["graph"] = json.dumps(
            graph_dict,
            ensure_ascii=False,
        )
    else:
        result_item["graph"] = graph_dict

    return result_item

def make_json_safe(data):
    if isinstance(data, list):
        return [make_json_safe(v) for v in data]
    elif isinstance(data, dict):
        return {k: make_json_safe(v) for k, v in data.items()}
    elif isinstance(data, (datetime, date)):
        #################
        try:
            return data.strftime("%Y-%m-%d")
        except:
            return None
        ########################
        # return data.strftime("%Y-%m-%d")
    elif isinstance(data, ObjectId):
        return str(data)
    elif isinstance(data, (float, Decimal, np.floating)):
        if math.isnan(data) or math.isinf(data):
            return None
        return round(float(data), 2)
    elif isinstance(data, (int, np.integer)):
        if pd.isna(data):
            return None
        return int(data)
    else:
        if data is None or (isinstance(data, float) and math.isnan(data)):
            return None
        return data


def bson_to_json_safe(doc):
    if isinstance(doc, list):
        return [bson_to_json_safe(d) for d in doc]
    elif isinstance(doc, dict):
        return {k: bson_to_json_safe(v) for k, v in doc.items()}
    elif isinstance(doc, (datetime, date)):
        return doc.strftime("%Y-%m-%d")
    elif isinstance(doc, ObjectId):
        return str(doc)
    else:
        return doc


def correct_columns_name(column):
    column = column.replace("_", " ")
    column = (
        " ".join([w for w in column.split(" ")])
        if len(column.split(" ")) > 1
        else column
    )
    return column


def serialize_filters(filters: Optional[List[ConversationFilter]] = None):
    if filters:
        payload: dict = {f.col_name: f.selected_values for f in filters}
        payload = dict(sorted(payload.items()))  # sorting the keys
        payload = {
            k: sorted(v) for k, v in sorted(payload.items()) if v
        }  # sorting the values
        base = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return base
    else:
        return ""
    

def get_next_levels(hierarchies, current_column, cutoff=0.6):
    """
    Given a column, return its next drilldown levels from hierarchy dict,
    using fuzzy matching if exact match is not found.
    """
    next_levels = []
    for levels in hierarchies.values():
        # Find best match from this list
        match = difflib.get_close_matches(current_column, levels, n=1, cutoff=cutoff)
        if match:
            idx = levels.index(match[0])
            if idx < len(levels) - 1:
                next_levels.extend(levels[idx+1:])
    return next_levels

# def get_table_and_status_and_columns(table_details: QueryResult):
#     table_status = table_details.status
#     if table_details.columns and table_details.rows:
#         table_columns = {f"column_{k}": v for k, v in enumerate(table_details.columns)}
#         df = pd.DataFrame(table_details.rows, columns=table_details.columns)
#     else:
#         table_columns = {}
#         df = pd.DataFrame()
#     table_json = df.to_dict(orient="records")
#     table_json = make_json_safe(table_json)
#     return table_json, table_status, table_columns


async def log_sql_data(i_data: InternalSQLHelper, query: str, db_id: int, chat_id: str | None, 
                 sql_query: str | None = None, filters_json: str | None = None, 
                 approach: str | None = None, question_type: str = "complete", 
                 raw_response: dict | None = None, 
                 token_usage: dict = {"input_tokens":0, "output_tokens": 0, "cached_tokens":0},
                 resolved_query: str | None = None):
        
        query_details = await i_data.create_or_get_query(query)
        if sql_query:
            sql_details = await i_data.create_or_get_sql(sql_query)
            sql_id = sql_details.id #type: ignore
        else:
            sql_id=None
        
        transaction_details = await i_data.create_transaction(
            db_id,
            query_details.id, #type: ignore
            sql_id=sql_id,
            chat_id=chat_id,
            filters=filters_json,
            approach=approach,
            question_type=question_type,
            raw_response=json.dumps(raw_response),
            resolved_query=resolved_query
        )
        await i_data.add_llm_usage(transaction_id=transaction_details.id, **token_usage) #type: ignore
        return transaction_details.id #type: ignore


def get_drilldown_features(dbname: str, df: pd.DataFrame):
    drilldown_features = []
    json_file = os.path.join("business_data", dbname, "hierarchies.json")
    with open(json_file, "r") as f:
        hierarchies_json = json.load(f)

    cat_cols = df.select_dtypes(include="object").columns.tolist()
    if "Fiscal_Year" in df.columns:
        cat_cols.append("Fiscal_Year")

    if "Comment" in cat_cols or "Raw_Comment" in cat_cols:
        drilldown_features = []
    else:
        hierarchies_exception = []

        for c in cat_cols:
            exep = hierarchies_json["hierarchies"].get(c)
            if exep:
                hierarchies_exception.extend(hierarchies_json["hierarchies"].get(c))

        base_drilldown_features = hierarchies_json["base_hierarchy_features"]
        drilldown_features = sorted(list(set(base_drilldown_features).difference(hierarchies_exception)))

    drilldown_features_mappings_list = [
        {
            "col_name": k,
            "alias": k.replace("_", " ")
        } for k in drilldown_features
    ] 
    return drilldown_features_mappings_list


# @lru_cache(maxsize=20)
def get_system_prompt(db_name: str, prompt_type: str) -> str: 
    """
    Retrieves the system prompt for query understanding. It first checks if there is a custom prompt for the given database name, and if not, it falls back to a default prompt.
    """

    custom_prompt_path = Path("app") / "core" / "prompts" / db_name / f"{prompt_type}.txt"
    
    # loading the default propt defined for dataset
    if custom_prompt_path.exists():
        with open(custom_prompt_path, "r") as f:
            system_prompt = f.read()
        logger.info(f"Using custom system prompt for database {db_name} from {custom_prompt_path}", extra={"event_type": "custom_prompt_used", "db_name": db_name, "prompt_path": custom_prompt_path})
        return system_prompt
    
    else:
        # checking for the default prompt for the prompt type
        default_prompt_path = Path("app") / "core" / "prompts" / f"{prompt_type}.txt"
        if default_prompt_path.exists():
            with open(default_prompt_path, "r") as f:
                system_prompt = f.read()
            logger.info(f"Using default system prompt for database {db_name} from {default_prompt_path}", extra={"event_type": "default_prompt_used", "db_name": db_name, "prompt_path": default_prompt_path})
            return system_prompt
        
        # default prompt does not exists
        try:
            prompt_getter = PromptGetter(db_name)
            system_prompt = prompt_getter.get_prompt(prompt_type)
            logger.info(f"Using system prompt for database {db_name} from PromptGetter for prompt type {prompt_type}", extra={"event_type": "prompt_getter_used", "db_name": db_name, "prompt_type": prompt_type})
            return system_prompt
        except Exception as e:
            logger.error(f"Error retrieving system prompt for database {db_name} and prompt type {prompt_type}: {str(e)}", exc_info=True, extra={"event_type": "system_prompt_retrieval_error", "db_name": db_name, "prompt_type": prompt_type})
            raise