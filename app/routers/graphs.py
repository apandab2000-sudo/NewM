from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
import yaml
import json

# from app.models import GetGraph
from app.api_models.graphs import GetGraph, EditGraph
from app.logger import get_logger
from app.core.helper import (
    serialize_filters,
    get_drilldown_features,
    format_plotly_axis_titles,
    is_percentage_column,
)
from app.core.llms import get_llm

# from app.databases.internal_nosql_operations import NOSQLHelper
from app.databases.application_nosql.operations import NOSQLHelper

# from app.databases.internal_sql_operations import InternalSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
from app.core.graphs.plotly.base import generate_graphs
from app.core.graphs.echarts.graphs import GraphGenerator
from app.databases.application_nosql.models import Plotly_Graph
from app.core.graphs.echarts.graphs import generate_graph_title
from app.core.prometheus_metrics import (
    GRAPHS_GENERATED_PER_QUESTION,
    GRAPHS_ERRORS,
    GRAPH_HITS,
)
from app.databases.dependencies import get_db_async, get_nosql_client
from app.core.ask_question.edit_graph.intent import detect_edit_graph_intent
from app.core.ask_question.forecasting.service import build_edit_graph_response
from app.core.ask_question.forecasting.errors import (
    ForecastNotPossible,
    GraphEditError,
)


router = APIRouter(prefix="/egai", tags=["Graphs"])
logger = get_logger()



def normalize_percentage_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert percentage strings received from table APIs back to numeric values.

    Examples:
        "24.5%" -> 24.5
        "1,250%" -> 1250.0

    Only columns identified as percentage metrics are processed. This keeps
    graph generation, sorting, aggregation, and Plotly/ECharts calculations
    numeric even when the table API response contains display-formatted values.
    """
    normalized_df = df.copy()

    for column_name in normalized_df.columns:
        if not is_percentage_column(column_name):
            continue

        normalized_df[column_name] = pd.to_numeric(
            normalized_df[column_name]
            .astype(str)
            .str.strip()
            .str.replace("%", "", regex=False)
            .str.replace(",", "", regex=False),
            errors="coerce",
        )

    return normalized_df


def get_percentage_columns(df: pd.DataFrame) -> list[str]:
    """
    Return percentage-based columns present in a DataFrame.
    """
    return [
        str(column_name)
        for column_name in df.columns
        if is_percentage_column(column_name)
    ]


def apply_plotly_percentage_formatting(
    graph: dict,
    percentage_columns: list[str],
) -> dict:
    """
    Add '%' display formatting to Plotly axes and trace tooltips while keeping
    the underlying graph values numeric.
    """
    if not isinstance(graph, dict) or not percentage_columns:
        return graph

    percentage_column_set = set(percentage_columns)
    layout = graph.setdefault("layout", {})

    if not isinstance(layout, dict):
        return graph

    traces = graph.get("data", [])

    if not isinstance(traces, list):
        traces = []

    percentage_on_x = False
    percentage_on_y = False

    for trace in traces:
        if not isinstance(trace, dict):
            continue

        trace_name = str(trace.get("name", ""))
        orientation = trace.get("orientation")
        x_values = trace.get("x")
        y_values = trace.get("y")

        x_axis_name = str(trace.get("xaxis", "x"))
        y_axis_name = str(trace.get("yaxis", "y"))

        xaxis_layout_key = (
            "xaxis"
            if x_axis_name == "x"
            else f"xaxis{x_axis_name.removeprefix('x')}"
        )
        yaxis_layout_key = (
            "yaxis"
            if y_axis_name == "y"
            else f"yaxis{y_axis_name.removeprefix('y')}"
        )

        xaxis_title = (
            layout.get(xaxis_layout_key, {})
            .get("title", {})
        )
        yaxis_title = (
            layout.get(yaxis_layout_key, {})
            .get("title", {})
        )

        if isinstance(xaxis_title, dict):
            xaxis_title = str(xaxis_title.get("text", ""))
        else:
            xaxis_title = str(xaxis_title or "")

        if isinstance(yaxis_title, dict):
            yaxis_title = str(yaxis_title.get("text", ""))
        else:
            yaxis_title = str(yaxis_title or "")

        trace_is_percentage = any(
            is_percentage_column(candidate)
            or candidate in percentage_column_set
            for candidate in (
                trace_name,
                xaxis_title,
                yaxis_title,
            )
            if candidate
        )

        # Horizontal bars commonly place the metric on x; most other charts
        # place the metric on y.
        if trace_is_percentage:
            if orientation == "h":
                percentage_on_x = True
                trace.setdefault(
                    "hovertemplate",
                    "%{x:.2f}%<extra>%{fullData.name}</extra>",
                )
            else:
                percentage_on_y = True
                trace.setdefault(
                    "hovertemplate",
                    "%{y:.2f}%<extra>%{fullData.name}</extra>",
                )

        # A percentage field may be directly represented by an axis title even
        # when the trace name is generic.
        if is_percentage_column(xaxis_title):
            percentage_on_x = True

        if is_percentage_column(yaxis_title):
            percentage_on_y = True

        # Pie/donut values are generally stored under values rather than x/y.
        value_field = trace.get("valueField")
        if (
            trace.get("type") == "pie"
            and (
                trace_is_percentage
                or (
                    isinstance(value_field, str)
                    and is_percentage_column(value_field)
                )
            )
        ):
            trace.setdefault(
                "hovertemplate",
                "%{label}: %{value:.2f}%<extra></extra>",
            )
            trace.setdefault(
                "texttemplate",
                "%{label}: %{value:.2f}%",
            )

        # Silence unused local references while retaining explicit inspection
        # points for differing Plotly trace structures.
        _ = x_values, y_values

    if percentage_on_x:
        xaxis = layout.setdefault("xaxis", {})
        if isinstance(xaxis, dict):
            xaxis["ticksuffix"] = "%"
            xaxis["hoverformat"] = ".2f"

    if percentage_on_y:
        yaxis = layout.setdefault("yaxis", {})
        if isinstance(yaxis, dict):
            yaxis["ticksuffix"] = "%"
            yaxis["hoverformat"] = ".2f"

    return graph


def apply_echarts_percentage_formatting(
    graph_item,
    percentage_columns: list[str],
):
    """
    Add percentage display formatters to ECharts option dictionaries.

    The function leaves unknown graph structures unchanged.
    """
    if not percentage_columns:
        return graph_item

    if not isinstance(graph_item, dict):
        return graph_item

    graph_value = graph_item.get("graph", graph_item)

    if isinstance(graph_value, str):
        try:
            graph_value = json.loads(graph_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return graph_item

    if not isinstance(graph_value, dict):
        return graph_item

    option = graph_value.get("option", graph_value)

    if not isinstance(option, dict):
        return graph_item

    series_list = option.get("series", [])
    if not isinstance(series_list, list):
        series_list = [series_list]

    has_horizontal_bar = any(
        isinstance(series, dict)
        and series.get("type") == "bar"
        and series.get("encode", {}).get("x") in percentage_columns
        for series in series_list
    )

    target_axis_key = "xAxis" if has_horizontal_bar else "yAxis"
    target_axis = option.get(target_axis_key)

    if isinstance(target_axis, list):
        for axis in target_axis:
            if isinstance(axis, dict):
                axis.setdefault("axisLabel", {})["formatter"] = "{value}%"
    elif isinstance(target_axis, dict):
        target_axis.setdefault("axisLabel", {})["formatter"] = "{value}%"

    tooltip = option.setdefault("tooltip", {})
    if isinstance(tooltip, dict):
        tooltip.setdefault("valueFormatter", "function (value) { return value + '%'; }")

    for series in series_list:
        if not isinstance(series, dict):
            continue

        if series.get("type") == "pie":
            label = series.setdefault("label", {})
            if isinstance(label, dict):
                label.setdefault("formatter", "{b}: {c}%")

    if "graph" in graph_item:
        graph_item["graph"] = graph_value
        return graph_item

    return graph_value


@router.post("/getGraph", status_code=200)
async def get_graph(
    data: GetGraph,
    session: AsyncSession = Depends(get_db_async),
):
    GRAPH_HITS.labels(data.dbname).inc()
    i_data = InternalSQLHelper(session)

    await get_nosql_client()
    nosql_helper = NOSQLHelper()

    raw_df = pd.DataFrame(data.table)  # type: ignore

    # Table APIs may return percentage values as strings such as "24.5%".
    # Convert them back to numeric values before any graph processing.
    df = normalize_percentage_dataframe(raw_df)
    df_copy = df.copy()
    percentage_columns = get_percentage_columns(df)

    print(
        "[GRAPH PERCENTAGE COLUMNS]",
        percentage_columns,
    )
    filters_json = serialize_filters(data.filters)

    transaction_details = await i_data.get_transaction_details_from_id(
        data.transaction_id
    )
    if not transaction_details:
        raise HTTPException(
            detail="Transaction details not found",
            status_code=404,
        )

    resolved_query = (
        transaction_details.resolved_query
        if transaction_details.resolved_query
        else data.query
    )

    with open("app/clientConfig.yaml", "r") as file:
        config_dict = yaml.safe_load(file)

    llm_base = config_dict[data.dbname]["LLM"]["GRAPH"]["BASE"]
    llm_name = config_dict[data.dbname]["LLM"]["GRAPH"]["MODEL"]
    llm = await get_llm(base=llm_base)

    graph_type = config_dict[data.dbname]["GRAPH_TYPE"]

    if (
        df.shape[0] <= 1
        or df.shape[1] <= 1
        or df.shape[1] > 6
    ):
        logger.warning(
            f"Graphs are not possible for this type of table - {df.shape}"
        )
        raise HTTPException(
            detail=(
                "Graphs are not possible for this type of table "
                f"- {df.shape}"
            ),
            status_code=404,
        )

    graph_title = None

    if graph_type == "echarts":
        graph_maker = GraphGenerator(df)
        graph_maker.correct_data_()
        graphs_list = graph_maker.generate_graphs()

        graph_title, token_usage = await generate_graph_title(
            resolved_query,
            df,
            data.dbname,
            llm,
            llm_name,
        )

        graphs_list = [
            apply_echarts_percentage_formatting(
                graph_item,
                percentage_columns,
            )
            for graph_item in graphs_list
        ]

        await i_data.add_llm_usage(
            data.transaction_id,
            "graph",
            llm_name,
            **token_usage.model_dump(),
        )

    else:
        graphs_list, token_usage = await generate_graphs(
            user_query=resolved_query,
            df=df,
            db_name=data.dbname,
            llm=llm,  # type: ignore
            filters=filters_json,
            llm_model=llm_name,
        )

        await i_data.add_llm_usage(
            data.transaction_id,
            "graph",
            llm_name,
            **token_usage.model_dump(),
        )

    if not graphs_list:
        GRAPHS_ERRORS.labels(data.dbname).inc()
        logger.warning(
            "Graphs were not generated successfully for the table "
            f"{df.shape}, {df.columns}"
        )
        raise HTTPException(
            detail=(
                "Graphs were not generated successfully for the table"
            ),
            status_code=404,
        )

    GRAPHS_GENERATED_PER_QUESTION.labels(
        data.dbname
    ).inc(len(graphs_list))

    logger.info(
        f"Graph generated successfully for data "
        f"{df.shape}, {df.columns}"
    )

    # Format Plotly axis titles before storing and returning them.
    if graph_type != "echarts":
        for graph_item in graphs_list:
            try:
                graph_json = graph_item.get("graph")

                print(
                    "[AXIS FORMAT] Processing graph:",
                    graph_item.get("graph_id"),
                )

                if isinstance(graph_json, str):
                    parsed_graph = json.loads(graph_json)

                    print(
                        "[AXIS FORMAT] Before xaxis:",
                        parsed_graph.get("layout", {})
                        .get("xaxis", {})
                        .get("title", {}),
                    )
                    print(
                        "[AXIS FORMAT] Before yaxis:",
                        parsed_graph.get("layout", {})
                        .get("yaxis", {})
                        .get("title", {}),
                    )

                    parsed_graph = format_plotly_axis_titles(
                        parsed_graph
                    )
                    parsed_graph = apply_plotly_percentage_formatting(
                        parsed_graph,
                        percentage_columns,
                    )

                    print(
                        "[AXIS FORMAT] After xaxis:",
                        parsed_graph.get("layout", {})
                        .get("xaxis", {})
                        .get("title", {}),
                    )
                    print(
                        "[AXIS FORMAT] After yaxis:",
                        parsed_graph.get("layout", {})
                        .get("yaxis", {})
                        .get("title", {}),
                    )

                    graph_item["graph"] = json.dumps(
                        parsed_graph,
                        ensure_ascii=False,
                    )

                elif isinstance(graph_json, dict):
                    formatted_graph = format_plotly_axis_titles(
                        graph_json
                    )
                    graph_item["graph"] = (
                        apply_plotly_percentage_formatting(
                            formatted_graph,
                            percentage_columns,
                        )
                    )

                else:
                    logger.warning(
                        "Unsupported Plotly graph format",
                        extra={
                            "event_type": (
                                "unsupported_plotly_graph_format"
                            ),
                            "graph_id": graph_item.get("graph_id"),
                            "graph_value_type": (
                                type(graph_json).__name__
                            ),
                        },
                    )

            except Exception as error:
                logger.exception(
                    "Unable to format graph axis titles",
                    extra={
                        "event_type": (
                            "graph_axis_title_format_error"
                        ),
                        "graph_id": graph_item.get("graph_id"),
                        "error": str(error),
                    },
                )

    plotly_graphs = []

    for graph_item in graphs_list:
        plotly_graphs.append(
            Plotly_Graph(
                graph_id=graph_item["graph_id"],
                plotly_code=graph_item["graph"],
                chart_type=graph_item["type"],
            )
        )

    # Store the same formatted graph JSON that is returned by the API.
    await nosql_helper.record_graph(
        transaction_id=data.transaction_id,
        graphs=plotly_graphs,
    )

    try:
        drilldown_features_mappings_list = get_drilldown_features(
            data.dbname,
            df_copy,
        )
    except Exception as error:
        logger.error(
            "Error during fetching drilldown features",
            extra={
                "event_type": "drilldown_features_error",
                "error": str(error),
            },
            exc_info=True,
        )
        drilldown_features_mappings_list = []

    if graph_type == "echarts":
        return {
            "status": 200,
            "status_message": "Success",
            "chart_type": "auto",
            "chart_sub_type": "auto",
            "echarts": graphs_list,
            "graph_title": graph_title,
            "drilldown_features": (
                drilldown_features_mappings_list
            ),
        }

    # Final verification that the formatted titles are in the response.
    for graph_item in graphs_list:
        try:
            graph_value = graph_item.get("graph")
            debug_graph = (
                json.loads(graph_value)
                if isinstance(graph_value, str)
                else graph_value
            )

            print(
                "[FINAL RESPONSE AXIS TITLES]",
                {
                    "graph_id": graph_item.get("graph_id"),
                    "xaxis": (
                        debug_graph.get("layout", {})
                        .get("xaxis", {})
                        .get("title", {})
                        .get("text")
                    ),
                    "yaxis": (
                        debug_graph.get("layout", {})
                        .get("yaxis", {})
                        .get("title", {})
                        .get("text")
                    ),
                },
            )
        except Exception as error:
            print(
                "[FINAL RESPONSE AXIS ERROR]",
                graph_item.get("graph_id"),
                str(error),
            )

    return {
        "status": 200,
        "status_message": "Success",
        "chart_type": "auto",
        "chart_sub_type": "auto",
        "plotlycharts": graphs_list,
        "graph_title": None,
        "drilldown_features": drilldown_features_mappings_list,
    }


@router.post("/editGraph", status_code=200)
async def edit_graph(
    data: EditGraph,
    db_session: AsyncSession = Depends(get_db_async),
):
    intent = detect_edit_graph_intent(data.query)

    try:
        if intent == "forecast":
            return build_edit_graph_response(data)

        raise HTTPException(
            detail=(
                "The graph edit request could not be processed."
            ),
            status_code=400,
        )
    except ForecastNotPossible as error:
        raise HTTPException(
            detail=str(error),
            status_code=400,
        )
    except GraphEditError as error:
        raise HTTPException(
            detail=str(error),
            status_code=400,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected error while processing graph edit"
        )
        raise HTTPException(
            detail="editGraph request could not be processed",
            status_code=500,
        )
