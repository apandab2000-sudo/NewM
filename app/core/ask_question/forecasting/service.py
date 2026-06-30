import re
from typing import Any, Literal

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from app.core.ask_question.forecasting.forecasting import FutureValues, predict_future_values
from app.core.ask_question.forecasting.models import ForecastResult
from app.core.ask_question.forecasting.errors import ForecastNotPossible
from app.api_models.graphs import EditGraph
from app.core.ask_question.forecasting.chart import build_forecast_plotly_chart
from app.core.graphs.plotly.helper import color_palette as default_color_palette


TIME_COLUMN_HINTS = ("date", "year", "month", "quarter", "week")
IGNORED_QUERY_TOKENS = {"for", "the", "by", "in", "next", "last", "of"}
FORECAST_MARKER_COLUMN = "is_forecasted"


# Legacy behavior: forecasting.py reads the time unit directly from the question.
# Problem: phrases like "fiscal year quarter wise" can be read as yearly instead of quarterly.
# Fix here: rewrite fiscal-quarter phrases into simple quarter wording before forecasting.
def _normalize_forecast_question(query: str) -> str:
    normalized = re.sub(r"\bfiscal\s+year\s+quarter\s+wise\b", "quarter wise", query, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfiscal\s+year\s+quarters?\b", "quarters", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfiscal\s+quarters?\b", "quarters", normalized, flags=re.IGNORECASE)
    return normalized


# Legacy behavior: forecasting.py detects the date column only after its own preprocessing.
# Problem: editGraph sends raw graph tables, and forecasting fails if the time column is not obvious.
# Fix here: identify date/year/month/quarter/week columns before reshaping the graph table.
def _split_column_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token and token not in IGNORED_QUERY_TOKENS
    }


def _is_time_column(df: pd.DataFrame, column: str) -> bool:
    lowered = column.lower()
    if not any(hint in lowered for hint in TIME_COLUMN_HINTS):
        return False

    if is_datetime64_any_dtype(df[column]):
        return True

    parsed = pd.to_datetime(df[column], errors="coerce")
    return parsed.notna().sum() == df[column].notna().sum() and parsed.notna().any()


def _select_time_column(df: pd.DataFrame) -> str:
    for column in df.columns:
        if column != FORECAST_MARKER_COLUMN and _is_time_column(df, column):
            return column
    raise ForecastNotPossible("No usable date, year, month, quarter, or week column found.")


# Legacy behavior: forecasting.py accepts only one numeric metric column.
# Problem: editGraph tables can include many metrics, such as current value, previous value,
# YoY change, and percent change.
# Fix here: score the numeric columns against the current and previous user questions,
# then forecast only the requested metric.
def _score_value_column(column: str, query: str, previous_user_query: str) -> int:
    question = f"{query} {previous_user_query}".lower()
    question_tokens = _split_column_tokens(question)
    column_tokens = _split_column_tokens(column)

    score = len(column_tokens & question_tokens)
    normalized_column = re.sub(r"[^a-z0-9]+", "", column.lower())
    normalized_question = re.sub(r"[^a-z0-9]+", "", question)
    if normalized_column and normalized_column in normalized_question:
        score += 10

    compact_question = question.replace(" ", "_")
    if column.lower() in compact_question:
        score += 5

    if "percent" in column_tokens and "percent" not in question_tokens and "%" not in question:
        score -= 2

    return score


def _numeric_columns(df: pd.DataFrame, excluded_columns: set[str]) -> list[str]:
    numeric_columns = []
    for column in df.columns:
        if column in excluded_columns:
            continue

        numeric_series = pd.to_numeric(df[column], errors="coerce")
        if numeric_series.notna().any():
            numeric_columns.append(column)

    return numeric_columns


def _select_value_column(df: pd.DataFrame, time_column: str, query: str, previous_user_query: str) -> str:
    numeric_columns = _numeric_columns(df, {time_column, FORECAST_MARKER_COLUMN})

    if not numeric_columns:
        raise ForecastNotPossible("Forecast requires a numeric metric column.")
    if len(numeric_columns) == 1:
        return numeric_columns[0]

    scored_columns = [
        (_score_value_column(column, query, previous_user_query), column)
        for column in numeric_columns
    ]
    scored_columns.sort(key=lambda item: item[0], reverse=True)
    best_score, best_column = scored_columns[0]
    if best_score <= 0:
        raise ForecastNotPossible("Forecast requires the requested metric to match one numeric column.")
    if len(scored_columns) > 1 and scored_columns[1][0] == best_score:
        tied_columns = ", ".join(column for score, column in scored_columns if score == best_score)
        raise ForecastNotPossible(f"Forecast metric is ambiguous. Matching columns: {tied_columns}")

    return best_column


# Legacy behavior: forecasting.py expects a simple table: time column, optional category,
# and one numeric value column.
# Problem: editGraph passes the original graph table, which can contain extra metrics and null rows.
# Fix here: keep only the selected time/category/value columns and remove rows with empty metric values.
def _categorical_columns(df: pd.DataFrame, excluded_columns: set[str]) -> list[str]:
    return [
        column
        for column in df.columns
        if column not in excluded_columns
        and not pd.to_numeric(df[column], errors="coerce").notna().any()
    ]


def _prepare_forecast_table(
    table: list[dict[str, Any]],
    query: str,
    previous_user_query: str,
) -> list[dict[str, Any]]:
    df = pd.DataFrame(table)
    if df.empty:
        raise ForecastNotPossible("Forecast could not be generated for an empty table.")

    time_column = _select_time_column(df)
    value_column = _select_value_column(df, time_column, query, previous_user_query)
    categorical_columns = _categorical_columns(df, {time_column, value_column})

    forecast_columns = [time_column]
    if categorical_columns:
        forecast_columns.append(categorical_columns[0])
    forecast_columns.append(value_column)

    prepared = df.loc[:, forecast_columns].copy()
    prepared = prepared[pd.to_numeric(prepared[value_column], errors="coerce").notna()]
    if prepared.empty:
        raise ForecastNotPossible(f"No non-empty values found for {value_column}.")

    return prepared.to_dict(orient="records")


# Legacy behavior: forecasting.py returns a pandas DataFrame.
# Problem: pandas Timestamp values are not ideal for the JSON graph API response.
# Fix here: convert datetime columns to string values before returning records.
def _normalize_forecast_table(forecast_df: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = forecast_df.copy()
    for column in normalized.columns:
        if is_datetime64_any_dtype(normalized[column]):
            normalized[column] = normalized[column].dt.strftime("%Y-%m-%d")

    return normalized.to_dict(orient="records")


def _actual_rows(forecast_df: pd.DataFrame) -> pd.DataFrame:
    if FORECAST_MARKER_COLUMN not in forecast_df.columns:
        return forecast_df
    return forecast_df[forecast_df[FORECAST_MARKER_COLUMN] == False]


def _is_regular_time_series(df: pd.DataFrame, time_column: str) -> bool:
    if df.shape[0] < 3:
        return False

    parsed_dates = pd.to_datetime(df[time_column], errors="coerce")
    if parsed_dates.notna().sum() != df[time_column].notna().sum() or parsed_dates.notna().sum() < 3:
        return False

    deltas = parsed_dates.sort_values().diff().dropna().dt.days.abs()
    if deltas.empty:
        return False

    median_delta = deltas.median()
    if median_delta == 0:
        return False

    return bool((deltas - median_delta).abs().le(max(1, median_delta * 0.15)).all())


def _forecast_confidence(
    forecast_df: pd.DataFrame,
    time_column: str,
    value_column: str,
    forecast_rows: int,
) -> Literal["low", "medium", "high"]:
    actual_df = _actual_rows(forecast_df)
    actual_count = actual_df.shape[0]

    if actual_count <= 2:
        return "low"

    value_series = pd.to_numeric(actual_df[value_column], errors="coerce")
    if value_series.notna().sum() < 3 or value_series.nunique(dropna=True) <= 1:
        return "low"

    horizon_ratio = forecast_rows / max(actual_count, 1)
    if horizon_ratio > 0.75:
        return "low"

    category_columns = _categorical_columns(actual_df, {time_column, value_column, FORECAST_MARKER_COLUMN})
    if category_columns and actual_df.groupby(category_columns[0]).size().min() <= 2:
        return "low"

    if actual_count >= 8 and horizon_ratio <= 0.35 and _is_regular_time_series(actual_df, time_column):
        return "high"

    return "medium"


# Public graph-edit forecast entry point.
# Legacy forecasting.py still generates the forecast values.
# This adapter only prepares editGraph input for that legacy function and wraps its output
# with metadata needed by the graph response.
def build_forecast(query: str, previous_user_query: str, table: list[dict[str, Any]]) -> ForecastResult:
    normalized_query = _normalize_forecast_question(query)
    if not FutureValues(table=table, user_query=previous_user_query).check_forecasting_related(normalized_query):
        raise ForecastNotPossible("Unsupported graph edit request")

    forecast_table = _prepare_forecast_table(
        table=table,
        query=normalized_query,
        previous_user_query=previous_user_query,
    )

    try:
        forecast_df = predict_future_values(
            table=forecast_table,
            user_query=previous_user_query,
            asked_question=normalized_query,
        )
    except Exception as e:
        raise ForecastNotPossible(f"Forecast could not be generated: {e}") from e

    if forecast_df is None or forecast_df.empty:
        raise ForecastNotPossible("Forecast could not be generated for this table.")

    if FORECAST_MARKER_COLUMN not in forecast_df.columns:
        raise ForecastNotPossible("Forecast output did not include forecast markers.")

    time_column = _select_time_column(forecast_df)
    value_column = _select_value_column(forecast_df, time_column, normalized_query, previous_user_query)
    forecast_rows = forecast_df[forecast_df[FORECAST_MARKER_COLUMN] == True].shape[0]
    confidence = _forecast_confidence(
        forecast_df=forecast_df,
        time_column=time_column,
        value_column=value_column,
        forecast_rows=forecast_rows,
    )

    return ForecastResult(
        table=_normalize_forecast_table(forecast_df),
        time_column=time_column,
        value_column=value_column,
        periods=max(1, int(forecast_rows)),
        confidence=confidence,
        warning=None,
    )



def _forecast_title(previous_user_query: str | None) -> str:
    if previous_user_query:
        cleaned_query = " ".join(previous_user_query.split())
        if cleaned_query:
            return f"{cleaned_query.title()} Forecast"
    return "Forecast"


# Converts the EditGraph API request into a forecast graph response.
def build_edit_graph_response(data: EditGraph) -> dict:
    previous_user_query = data.previous_user_query or data.query
    forecast_result = build_forecast(
        query=data.query,
        previous_user_query=previous_user_query,
        table=data.table,
    )

    graph = build_forecast_plotly_chart(
        forecast_result=forecast_result,
        graph_id=int(data.graph_id),
        title=_forecast_title(previous_user_query),
        color_palette = data.color_palette or default_color_palette,
    )

    return {
        "status": 200,
        "status_message": "Success",
        "chart_type": data.chart_type,
        "chart_sub_type": data.chart_sub_type,
        "plotlycharts": [graph],
        "drilldown_features": [],
    }
