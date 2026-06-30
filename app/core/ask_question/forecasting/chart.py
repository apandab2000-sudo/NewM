import json

import pandas as pd
import plotly.graph_objects as go

from app.core.ask_question.forecasting.models import ForecastResult
from app.core.graphs.plotly.helper import color_palette as default_color_palette


# Converts pandas values into JSON-safe values for Plotly.
def _json_safe_values(series: pd.Series) -> list:
    values = []
    for value in series.tolist():
        if pd.isna(value):
            values.append(None)
        elif isinstance(value, pd.Timestamp):
            values.append(value.strftime("%Y-%m-%d"))
        elif hasattr(value, "isoformat"):
            values.append(value.isoformat())
        else:
            values.append(value)
    return values


# Builds the Plotly chart payload with actual and forecast lines.
def build_forecast_plotly_chart(
    forecast_result: ForecastResult,
    graph_id: int = 0,
    title: str = "Forecast",
    color_palette: list[str] = default_color_palette,
) -> dict:
    df = pd.DataFrame(forecast_result.table)
    actual_df = df[df["is_forecasted"] == False]
    forecast_df = df[df["is_forecasted"] == True]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=_json_safe_values(actual_df[forecast_result.time_column]),
            y=_json_safe_values(actual_df[forecast_result.value_column]),
            mode="lines+markers",
            name="Actual",
            line={"color": color_palette[0], "width": 2},
            marker={"color": color_palette[0], "size": 7},
        )
    )

    if not forecast_df.empty:
        bridge_df = pd.concat([actual_df.tail(1), forecast_df], ignore_index=True)
        fig.add_trace(
            go.Scatter(
                x=_json_safe_values(bridge_df[forecast_result.time_column]),
                y=_json_safe_values(bridge_df[forecast_result.value_column]),
                mode="lines+markers",
                name="Forecast",
                line={"color": color_palette[0], "width": 2, "dash": "dash"},
                marker={"color": color_palette[0], "size": 7},
            )
        )

    fig.update_layout(
        template="simple_white",
        height=350,
        margin={"l": 20, "r": 20, "b": 0, "t": 0, "pad": 0},
        title={
            "text": title,
            "x": 0,
            "y": 0.96,
            "font": {"color": "#1E78B4", "size": 2},
            "xanchor": "left",
        },
        font={"family": "open sans, Helvetica Neue, Helvetica, Arial, sans-serif"},
        legend={
            "orientation": "h",
            "xref": "container",
            "yref": "container",
            "font": {"size": 12},
        },
        xaxis_title=forecast_result.time_column,
        yaxis_title=forecast_result.value_column,
    )
    fig.update_xaxes(tickfont={"size": 12}, type="category")
    fig.update_yaxes(tickfont={"size": 12})

    return {
        "type": "Forecast",
        "graph_id": graph_id,
        "graph": json.dumps(fig.to_plotly_json(), default=str),
    }
