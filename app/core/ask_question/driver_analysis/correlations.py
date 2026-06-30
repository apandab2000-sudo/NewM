from pathlib import Path
from typing import Any
import json, re, time

import pandas as pd
from scipy.stats import chi2_contingency

# from app.core.ask_question.driver_analysis.correlation_config import (
#     CATEGORICAL_TYPES, DIMENSION_TERMS, MAX_CORRELATION_AGE_DAYS, METRIC_TERMS,
#     MIN_CORRELATION_ROWS, MIN_CORRELATION_SCORE, NOISY_TERMS, NUMERIC_TYPES,
#     ON_DEMAND_MAX_DRIVERS, ON_DEMAND_MAX_METRICS, ON_DEMAND_SAMPLE_SIZE,
#     REQUIRED_CORRELATION_COLUMNS,
# )
from app.databases.client_sql.operations import get_table_and_status_and_columns, get_table_from_sql
from app.logger import get_logger


logger = get_logger(__name__)


correlation_config = None


def load_correlation_config() -> dict[str, Any]:
    global correlation_config
    with open(Path("app") / "core" / "ask_question" / "driver_analysis" / "correlation_config.json", encoding="utf-8") as f:
        correlation_config = json.load(f)
    return correlation_config
    
# Build correlation datasets for requested tables and persist them to corr_datasets.

async def generate_correlation_datasets(dbname: str, client_pool, tables: list[str] | None = None, table_sql_names: dict[str, str] | None = None, target_metric: str | None = None, query: str | None = None, sql: str | None = None, dialect: str = "mssql", sample_size: int = 5000, max_metrics: int = 12, max_drivers: int = 25, top_drivers_per_metric: int = 0) -> dict[str, Any]:
    out_dir, generated = Path("business_data") / dbname / "corr_datasets", []
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, columns in _pick_tables(_table_columns(dbname), tables).items():
        numeric, categorical = _split(columns)
        numeric, categorical = _rank(numeric, columns, query, sql, True)[:max_metrics], _rank(categorical, columns, query, sql, False)[:max_drivers]
        where, sql_table = _where(sql or ""), (table_sql_names or {}).get(table, table)
        logger.info("Preparing correlation generation for table", extra={"event_type": "correlation_generation_table_prepared", "dbname": dbname, "table": table, "column_count": len(columns), "metric_count": len(numeric), "driver_count": len(categorical), "has_context_filter": bool(where)})
        pairs = await _pairs(dbname, client_pool, sql_table, numeric, categorical, dialect, sample_size, where)
        logger.info("Correlation pairs generated for table", extra={"event_type": "correlation_generation_pairs_scored", "dbname": dbname, "table": table, "pair_count": len(pairs)})
        if pairs:
            file_path = out_dir / f"overall_{table}.csv"
            pd.DataFrame(pairs).to_csv(file_path, index=False)
            generated.append({"table": table, "file": str(file_path), "pairs": len(pairs), "metrics": len(numeric), "drivers": len(categorical)})
    return {"generated_files": generated}


# Ensure correlation CSV exists and is usable for the current table/metric context.
async def ensure_correlation_dataset(dbname: str, client_pool, table: str, table_sql_name: str | None = None, metric: str | None = None, query: str | None = None, sql: str | None = None, dialect: str = "mssql") -> dict[str, Any]:
    
    correlation_config = load_correlation_config()
    
    file_path = Path("business_data") / dbname / "corr_datasets" / f"overall_{table}.csv"
    
    if is_correlation_file_usable(
        file_path=file_path, 
        metric=metric, 
        min_rows=correlation_config["ON_DEMAND_MIN_ROWS"], 
        max_age_days=correlation_config["ON_DEMAND_MAX_AGE_DAYS"]
    ):
        logger.info("Correlation file is usable", extra={"event_type": "correlation_file_valid", "dbname": dbname, "table": table, "file": str(file_path)})
        return {"status": "exists", "file": str(file_path)}
    logger.info("Generating missing or stale correlation file", extra={"event_type": "correlation_generation_started", "dbname": dbname, "table": table, "file": str(file_path)})
    
    result = await generate_correlation_datasets(dbname, client_pool, [table], {table: table_sql_name} if table_sql_name else None, query=query, sql=sql, dialect=dialect, sample_size=correlation_config["ON_DEMAND_SAMPLE_SIZE"], max_metrics=correlation_config["ON_DEMAND_MAX_METRICS"], max_drivers=correlation_config["ON_DEMAND_MAX_DRIVERS"])
    
    if is_correlation_file_usable(
        file_path=file_path, 
        metric=metric, 
        min_rows=correlation_config["ON_DEMAND_MIN_ROWS"], 
        max_age_days=correlation_config["ON_DEMAND_MAX_AGE_DAYS"]
    ):
        logger.info("Correlation file generated successfully", extra={"event_type": "correlation_generation_completed", "dbname": dbname, "table": table, "file": str(file_path)})
        return {"status": "generated", "file": str(file_path), **result}
    logger.warning("Correlation file is still unusable after generation", extra={"event_type": "correlation_generation_failed", "dbname": dbname, "table": table, "file": str(file_path)})
    
    return {"status": "failed", "file": str(file_path), **result}


# Check freshness, shape, and optional metric presence in a correlation CSV.
def is_correlation_file_usable(file_path: Path, metric: str, min_rows: int, max_age_days: int ) -> bool:
    if not file_path.exists() or time.time() - file_path.stat().st_mtime > max_age_days * 86400:
        return False
    try:
        corr_df = pd.read_csv(file_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return False
    return correlation_config["REQUIRED_CORRELATION_COLUMNS"].issubset(corr_df.columns) and corr_df.shape[0] >= min_rows and (not metric or _has_metric(corr_df, metric))


# Generate and score all pairwise metric-driver combinations.
async def _pairs(dbname: str, pool, table: str, numeric: list[str], categorical: list[str], dialect: str, limit: int, where: str | None) -> list[dict[str, Any]]:
    types, columns, rows = ({c: "numeric" for c in numeric} | {c: "categorical" for c in categorical}), list(dict.fromkeys(numeric + categorical)), []
    for i, left in enumerate(columns):
        for right in columns[i + 1:]:
            score = _score(await _sample(dbname, pool, table, left, right, dialect, limit, where), types[left], types[right])
            if score["correlation"] >= correlation_config["MIN_CORRELATION_SCORE"]:
                rows.append({"column_1": left, "column_2": right, **score})
    return sorted(rows, key=lambda row: row["correlation"], reverse=True)


# Run sampling SQL and return raw pair values for scoring.
async def _sample(dbname: str, pool, table: str, left: str, right: str, dialect: str, limit: int, where: str | None) -> list[dict[str, Any]]:
    result = await get_table_from_sql(pool, dbname, _sql(table, left, right, dialect, limit, where), row_limit=limit)
    rows, status, _ = get_table_and_status_and_columns(result)
    return rows if status == "success" else []


# Compute a normalized correlation score across numeric/categorical pair types.
def _score(rows: list[dict[str, Any]], left_type: str, right_type: str) -> dict[str, float]:
    if len(rows) < 3:
        return _row(0, 0)
    df, kind = pd.DataFrame(rows), _kind(left_type, right_type)
    left, right = _find(df.columns, "left_value"), _find(df.columns, "right_value")
    if not left or not right:
        return _row(0, 0)
    if kind == "numeric_numeric":
        clean = df[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
        raw = 0 if _weak(clean, left, right) else float(clean[left].corr(clean[right], method="spearman"))
        return _row(abs(raw), raw)
    if kind == "categorical_categorical":
        clean = df[[left, right]].dropna()
        if _weak(clean, left, right):
            return _row(0, 0)
        cross = pd.crosstab(clean[left], clean[right])
        n, denom = int(cross.to_numpy().sum()), int(cross.to_numpy().sum()) * (min(cross.shape) - 1)
        score = float((chi2_contingency(cross, correction=False)[0] / denom) ** 0.5) if denom else 0
        return _row(score, score)
    num, cat = (left, right) if left_type == "numeric" else (right, left)
    clean = df[[num, cat]].dropna().copy()
    clean[num] = pd.to_numeric(clean[num], errors="coerce")
    clean = clean.dropna()
    if _weak(clean, num, cat):
        return _row(0, 0)
    mean, total = clean[num].mean(), ((clean[num] - clean[num].mean()) ** 2).sum()
    grouped = clean.groupby(cat)[num].agg(["mean", "count"])
    score = float((grouped["count"] * (grouped["mean"] - mean) ** 2).sum() / total) if total else 0
    return _row(score, score)


# Load table-column metadata from introduction_meta or schema fallback.
def _table_columns(dbname: str) -> dict[str, list[dict[str, Any]]]:
    meta = Path("business_data") / dbname / "introduction_meta.json"
    if meta.exists():
        tables = {t.get("table_name"): t.get("columns", []) for t in json.loads(meta.read_text(encoding="utf-8")).get("columns_metadata", []) if t.get("table_name")}
        if any(_numeric(c) for cols in tables.values() for c in cols):
            return tables
    schema = Path("app") / "core" / "schema_strings" / f"{dbname}.txt"
    if not schema.exists():
        return {}
    text, out = schema.read_text(encoding="utf-8"), {}
    matches = list(re.finditer(r"^\s*TABLE\s+\**([\w]+)\**", text, flags=re.IGNORECASE | re.MULTILINE))
    for i, match in enumerate(matches):
        start, end = text.find("(", match.end()), matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if start != -1 and start < end:
            out[match.group(1)] = [{"column_name": p[0], "data_type": p[1]} for p in (line.strip().strip(",").split() for line in text[start + 1:end].splitlines()) if len(p) >= 2 and not p[0].startswith(("--", ")"))]
    return out


# Keep only requested tables while tolerating case/format differences.
def _pick_tables(table_columns: dict[str, list[dict[str, Any]]], tables: list[str] | None) -> dict[str, list[dict[str, Any]]]:
    if not tables:
        return table_columns
    lookup = {_norm(table): table for table in table_columns}
    return {table: table_columns.get(lookup.get(_norm(table), table), []) for table in tables}


# Classify columns into numeric metrics and categorical drivers.
def _split(columns: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    numeric, categorical = [], []
    for col in columns:
        name = col.get("column_name")
        if name and not _noisy(name):
            (numeric if _numeric(col) else categorical if _categorical(col) else []).append(name)
    return numeric, categorical


# Rank candidates by query/sql context relevance and configured terms.
def _rank(names: list[str], columns: list[dict[str, Any]], query: str | None, sql: str | None, metric: bool) -> list[str]:
    context, terms = _norm(f"{query or ''} {sql or ''}"), correlation_config["METRIC_TERMS"] if metric else correlation_config["DIMENSION_TERMS"]
    return sorted(names, key=lambda n: (100 if _norm(n) in context else 0) + (20 if any(t in _norm(n) for t in terms) else 0), reverse=True)


# Build dialect-aware SQL for sampling a pair of columns.
def _sql(table: str, left: str, right: str, dialect: str, limit: int, where: str | None) -> str:
    table, left, right = _quote(table, dialect), _quote(left, dialect), _quote(right, dialect)
    filters = f"{left} IS NOT NULL AND {right} IS NOT NULL" + (f" AND ({where})" if where else "")
    return f"SELECT {left} AS left_value, {right} AS right_value FROM {table} WHERE {filters} LIMIT {limit}" if dialect.lower() in {"postgres", "postgresql", "pgsql", "mysql"} else f"SELECT TOP {limit} {left} AS left_value, {right} AS right_value FROM {table} WHERE {filters}"


# Extract a top-level WHERE clause for context-aware correlation sampling.
def _where(sql: str) -> str | None:
    match = re.search(r"\bwhere\b\s+(.+?)(?:\bgroup\s+by\b|\border\s+by\b|\bhaving\b|\boffset\b|\bfetch\b|\)\s+\w+\s*(?:order\s+by|$)|$)", sql, flags=re.IGNORECASE | re.DOTALL)
    clause = " ".join(match.group(1).split()).strip().rstrip(";") if match else ""
    return None if not clause or re.search(r"\b(select|from|join)\b", clause, flags=re.IGNORECASE) else clause


# Quote identifiers based on SQL dialect while preserving already-quoted names.
def _quote(identifier: str, dialect: str) -> str:
    if any(mark in identifier for mark in ("[", '"', "`")):
        return identifier
    if "." in identifier:
        return ".".join(_quote(part, dialect) for part in identifier.split("."))
    return f'"{identifier}"' if dialect.lower() in {"postgres", "postgresql", "pgsql"} else f"`{identifier}`" if dialect.lower() == "mysql" else f"[{identifier}]"


# Clamp and round score payloads for stable downstream usage.
def _row(correlation: float, raw: float) -> dict[str, float]:
    raw = 0.0 if pd.isna(raw) else float(raw)
    return {"correlation": round(max(0.0, min(1.0, correlation)), 4), "raw_correlation": round(raw, 4)}


# Verify whether a cached correlation dataset includes the requested metric.
def _has_metric(corr_df: pd.DataFrame, metric: str) -> bool:
    key = _norm(metric)
    return any(key in _norm(v) or _norm(v) in key for v in pd.concat([corr_df["column_1"], corr_df["column_2"]]).dropna().unique())


# Reject low-signal samples with too few rows or too little variance.
def _weak(df: pd.DataFrame, left: str, right: str) -> bool:
    return df.shape[0] < 3 or df[left].nunique() < 2 or df[right].nunique() < 2


# Resolve feature-pair category for scoring branch selection.
def _kind(left: str, right: str) -> str:
    return "numeric_numeric" if left == right == "numeric" else "categorical_categorical" if left == right == "categorical" else "numeric_categorical"


# Determine numeric columns from metadata hints and type names.
def _numeric(column: dict[str, Any]) -> bool:
    dtype = str(column.get("data_type") or column.get("type") or "").lower()
    return bool(column.get("numeric_stats")) or any(t in dtype for t in correlation_config["NUMERIC_TYPES"])


# Determine categorical columns from metadata hints and type names.
def _categorical(column: dict[str, Any]) -> bool:
    dtype = str(column.get("data_type") or column.get("type") or "").lower()
    return bool(column.get("categorical_stats")) or any(t in dtype for t in correlation_config["CATEGORICAL_TYPES"])


# Filter out technical/noisy columns from driver candidacy.
def _noisy(name: str) -> bool:
    key = _norm(name)
    return any(key == term or key.endswith(term) for term in correlation_config["NOISY_TERMS"])


# Find a target column name by normalized comparison.
def _find(columns, target: str) -> str | None:
    return next((column for column in columns if _norm(column) == _norm(target)), None)


# Normalize names for case/format-insensitive matching.
def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())
