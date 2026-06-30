from typing import Any
import re

from app.core.ask_question.driver_analysis.correlations import ensure_correlation_dataset
from app.core.ask_question.driver_analysis.driver_analysis import DriverAnalysis


async def run_driver_analysis(
    dbname: str,
    llm,
    client_pool,
    query: str,
    sql: str,
    table: list[dict[str, Any]],
):
    """Run post-table driver analysis for a successful Text2SQL response."""
    # Functionality: orchestrates correlation lookup, follow-up SQL execution, and compact response shaping.
    if not sql or not sql.strip():
        return {"drivers": [], "message": "SQL is required for driver analysis"}

    if not table:
        return {"drivers": [], "message": "Table data is required for driver analysis"}

    driver = DriverAnalysis(
        client=dbname,
        llm=llm,
        client_db=client_pool,
        table=table,
        user_query=query,
        sql_code=sql,
    )

    source_table = driver.get_available_table_in_sql_query()
    if not source_table:
        return {"drivers": [], "message": "No source table found for driver analysis"}

    sql_features = await driver.get_features_from_sql()
    primary_metric = _first_value(sql_features.get("aggregated_features", []))
    correlation_status = await ensure_correlation_dataset(
        dbname=dbname,
        client_pool=client_pool,
        table=source_table,
        table_sql_name=_extract_source_table_reference(sql) or source_table,
        metric=primary_metric,
        query=query,
        sql=sql,
        dialect=driver.db_dialect,
    )

    corr_df = await driver.get_correlated_dataframe()
    if corr_df is None or corr_df.empty:
        if correlation_status.get("status") == "failed":
            return {
                "drivers": [],
                "warning": "Correlation data is unavailable or could not be generated for this table.",
            }
        return {"drivers": [], "message": "No correlation drivers found for this query"}

    existing_dimensions = _extract_existing_dimensions(sql)
    driver_requests = _build_driver_requests(query, corr_df, existing_dimensions)
    if not driver_requests:
        return {"drivers": [], "message": "No non-redundant correlation drivers found for this query"}

    driver_results = await driver.get_sql_from_queries([request["question"] for request in driver_requests])

    result_by_question = {result["user_query"]: result for result in driver_results}
    drivers = []
    for request in driver_requests:
        result = result_by_question.get(request["question"])
        if not result:
            continue

        cleaned_data = _clean_driver_rows(result.get("sql_table", []), request["driver"])
        if not cleaned_data:
            continue

        drivers.append({
            "metric": request["metric"],
            "driver": request["driver"],
            "correlation": request["correlation"],
            "data": cleaned_data,
        })

    return {"drivers": drivers}


def _build_driver_requests(
    query: str,
    corr_df,
    existing_dimensions: set[str],
) -> list[dict[str, Any]]:
    """Convert correlation rows into concise follow-up business questions."""
    # Functionality: prepares one driver-analysis request per non-redundant correlated feature.
    requests = []
    for _, row in corr_df.iterrows():
        primary_feature = row.get("column_1")
        driver_feature = row.get("column_2")
        if _normalize_name(driver_feature) in existing_dimensions:
            continue
        if primary_feature and driver_feature:
            requests.append({
                "metric": primary_feature,
                "driver": driver_feature,
                "correlation": row.get("correlation"),
                "question": f"Show {primary_feature} by {driver_feature} for {query}",
            })
    return requests


def _extract_existing_dimensions(sql: str) -> set[str]:
    """Find dimensions already fixed or grouped in the original SQL."""
    # Functionality: collects original SQL dimensions so repeated drivers can be skipped.
    dimensions = set()
    dimensions.update(_extract_group_by_dimensions(sql))
    dimensions.update(_extract_filter_dimensions(sql))
    return {_normalize_name(dimension) for dimension in dimensions if dimension}


def _extract_group_by_dimensions(sql: str) -> set[str]:
    # Functionality: extracts identifiers listed in the SQL GROUP BY clause.
    match = re.search(r"\bgroup\s+by\s+(.+?)(?:\border\s+by\b|\bhaving\b|\)|$)", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return set()
    return {_clean_sql_identifier(part) for part in match.group(1).split(",")}


def _extract_filter_dimensions(sql: str) -> set[str]:
    # Functionality: extracts identifiers constrained in the SQL WHERE clause.
    return {
        _clean_sql_identifier(match)
        for match in re.findall(r"\bwhere\b.+?\b([A-Za-z_][\w\.\[\]]*)\s*(?:=|in\b|like\b)", sql, flags=re.IGNORECASE | re.DOTALL)
    }


def _extract_source_table_reference(sql: str) -> str | None:
    match = re.search(r"\bfrom\s+([\w\.\[\]\"]+)", sql, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _clean_sql_identifier(identifier: str) -> str:
    # Functionality: normalizes SQL identifiers by removing aliases, qualifiers, and brackets.
    identifier = identifier.strip()
    identifier = re.sub(r"\bas\b\s+[A-Za-z_][\w\[\]]*$", "", identifier, flags=re.IGNORECASE).strip()
    return identifier.split(".")[-1].strip("[] ")


def _normalize_name(value: Any) -> str:
    # Functionality: creates a case-insensitive comparable feature name.
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _first_value(values: list[Any]) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None


def _clean_driver_rows(rows: list[dict[str, Any]], driver_feature: str) -> list[dict[str, Any]]:
    """Remove noisy rows and keep only response data useful to the UI."""
    # Functionality: removes empty driver values, null fields, ignored fields, and zero-only rows.
    cleaned_rows = []
    normalized_driver = driver_feature.lower()
    for row in rows:
        driver_key = _find_row_key(row, normalized_driver)
        if driver_key and row.get(driver_key) in (None, ""):
            continue

        cleaned_row = {}
        for key, value in row.items():
            if _is_ignored_signal_key(key):
                continue
            if value is None:
                continue
            cleaned_row[key] = value

        if cleaned_row and not _is_zero_signal_row(cleaned_row, driver_key):
            cleaned_rows.append(cleaned_row)
    return cleaned_rows


def _is_zero_signal_row(row: dict[str, Any], driver_key: str | None) -> bool:
    """Drop rows whose analytical metric values are all zero."""
    # Functionality: identifies rows where all analytical numeric values are zero.
    signal_values = []
    for key, value in row.items():
        if driver_key and key == driver_key:
            continue
        if _is_ignored_signal_key(key):
            continue
        if isinstance(value, (int, float)):
            signal_values.append(value)

    return bool(signal_values) and all(value == 0 for value in signal_values)


def _is_ignored_signal_key(key: str) -> bool:
    # Functionality: detects time or previous-period columns that should not count as metric signals.
    normalized_key = key.lower()
    return any(
        token in normalized_key
        for token in ("date", "time", "year", "quarter", "month", "week", "day", "prev", "previous", "prior")
    )


def _find_row_key(row: dict[str, Any], normalized_key: str) -> str | None:
    # Functionality: finds the actual row key matching a driver name case-insensitively.
    for key in row:
        if key.lower() == normalized_key:
            return key
    return None
