import sqlglot
import sqlglot.expressions as exp
from pydantic import BaseModel
from typing import Any
from app.logger import get_logger


logger = get_logger(__name__)


class ParsedFilter(BaseModel):
    table_name: str             # e.g. "dbo.Sales" or "Sales"
    column_name: str            # e.g. "region"
    operator: str               # e.g. "=", "LIKE", "BETWEEN", ">", "IN"
    value: Any                  # single value, list (IN), or dict (BETWEEN)
    raw_expression: str         # original SQL fragment for debugging


class WhereClauseParseResult(BaseModel):
    filters: list[ParsedFilter]
    tables: list[str]           # all tables referenced in the query
    parse_success: bool
    error: str | None = None


def parse_where_clause_filters(sql: str, dialect: str = "tsql") -> dict:
    """
    Parses a SQL query and extracts all WHERE clause filter conditions
    into structured ParsedFilter objects.

    Handles:
      - Equality:        col = 'value'
      - LIKE:            col LIKE '%value%'
      - BETWEEN:         col BETWEEN x AND y
      - IN:              col IN ('a', 'b', 'c')
      - Comparisons:     col > x, col <= x
      - IS NULL:         col IS NULL
      - NOT conditions:  col NOT LIKE, col NOT IN, col NOT BETWEEN
      - Aliases:         resolves table aliases to real table names
      - Multi-table:     JOIN queries with aliased tables

    Args:
        sql:     The full SQL query string
        dialect: SQL dialect for sqlglot parser (default: "tsql" for MSSQL)

    Returns:
        WhereClauseParseResult with structured filters and table list
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as e:
        logger.error(f"sqlglot failed to parse SQL: {e}")
        return WhereClauseParseResult(
            filters=[],
            tables=[],
            parse_success=False,
            error=f"SQL parse error: {str(e)}"
        ).model_dump()

    # ── 1. Build alias → real table name map ──────────────────────────────────
    alias_map: dict[str, str] = {}
    tables_found: list[str] = []

    for table_expr in parsed.find_all(exp.Table):
        real_name = table_expr.name
        schema = table_expr.args.get("db")
        full_name = f"{schema.name}.{real_name}" if schema else real_name

        if full_name not in tables_found:
            tables_found.append(full_name)

        alias = table_expr.alias
        if alias:
            alias_map[alias] = full_name
        else:
            alias_map[real_name] = full_name

    # ── 2. Find the WHERE clause ───────────────────────────────────────────────
    where_clause = parsed.find(exp.Where)
    if not where_clause:
        logger.info("No WHERE clause found in query")
        return WhereClauseParseResult(
            filters=[],
            tables=tables_found,
            parse_success=True,
            error=None
        ).model_dump()

    # ── 3. Walk the WHERE tree and extract conditions ─────────────────────────
    filters: list[ParsedFilter] = []
    _extract_conditions(where_clause, alias_map, filters, sql)

    return WhereClauseParseResult(
        filters=filters,
        tables=tables_found,
        parse_success=True,
        error=None
    ).model_dump()


def _resolve_column(column_expr: exp.Column, alias_map: dict[str, str]) -> tuple[str, str]:
    """Returns (table_name, column_name) resolving aliases."""
    col_name = column_expr.name
    table_alias = column_expr.table

    if table_alias:
        table_name = alias_map.get(table_alias, table_alias)
    elif len(alias_map) == 1:
        # Single table query — assign automatically
        table_name = next(iter(alias_map.values()))
    else:
        table_name = "unknown"

    return table_name, col_name


def _extract_literal_value(node: exp.Expression, dialect: str = "tsql") -> Any:
    """Safely extracts Python value from a sqlglot literal node."""
    if isinstance(node, exp.Literal):
        if node.is_number:
            raw = node.this
            return float(raw) if "." in raw else int(raw)
        return node.this  # string value without quotes
    elif isinstance(node, exp.Null):
        return None
    elif isinstance(node, exp.Boolean):
        return node.this
    else:
        return node.sql(dialect=dialect)  # fallback to raw SQL string


def _extract_conditions(
    node: exp.Expression,
    alias_map: dict[str, str],
    filters: list[ParsedFilter],
    original_sql: str,
    dialect: str = "tsql"  # tsql for MSSQL , for oracle use "oracle"
) -> None:
    """
    Recursively walks the WHERE expression tree and appends
    ParsedFilter objects to `filters` for each leaf condition.
    """

    # AND / OR → recurse into both sides
    if isinstance(node, (exp.And, exp.Or, exp.Where)):
        for child in node.args.values():
            if isinstance(child, exp.Expression):
                _extract_conditions(child, alias_map, filters, original_sql, dialect)
        return

    # ── EQ:  col = 'value' ────────────────────────────────────────────────────
    if isinstance(node, exp.EQ):
        left, right = node.left, node.right
        if isinstance(left, exp.Column):
            table, col = _resolve_column(left, alias_map)
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator="=",
                value=_extract_literal_value(right, dialect=dialect),
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── NEQ: col != 'value' or col <> 'value' ────────────────────────────────
    if isinstance(node, exp.NEQ):
        left, right = node.left, node.right
        if isinstance(left, exp.Column):
            table, col = _resolve_column(left, alias_map)
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator="!=",
                value=_extract_literal_value(right, dialect=dialect),
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── LIKE / NOT LIKE ───────────────────────────────────────────────────────
    if isinstance(node, exp.Like):
        left, right = node.this, node.args.get("expression")
        if isinstance(left, exp.Column):
            table, col = _resolve_column(left, alias_map)
            raw_pattern = _extract_literal_value(right, dialect=dialect)
            # Strip SQL wildcards to get the core search term
            clean_value = str(raw_pattern).strip("%").strip()
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator="LIKE",
                value=clean_value,
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    if isinstance(node, exp.ILike):
        # Same as LIKE but case-insensitive — treat identically for MSSQL
        left, right = node.this, node.args.get("expression")
        if isinstance(left, exp.Column):
            table, col = _resolve_column(left, alias_map)
            clean_value = str(_extract_literal_value(right, dialect=dialect)).strip("%").strip()
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator="LIKE",
                value=clean_value,
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── BETWEEN / NOT BETWEEN ─────────────────────────────────────────────────
    if isinstance(node, exp.Between):
        col_expr = node.this
        low = node.args.get("low")
        high = node.args.get("high")
        if isinstance(col_expr, exp.Column):
            table, col = _resolve_column(col_expr, alias_map)
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator="BETWEEN",
                value={
                    "low": _extract_literal_value(low, dialect=dialect),
                    "high": _extract_literal_value(high, dialect=dialect)
                },
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── IN / NOT IN ───────────────────────────────────────────────────────────
    if isinstance(node, exp.In):
        col_expr = node.this
        if isinstance(col_expr, exp.Column):
            table, col = _resolve_column(col_expr, alias_map)
            in_values = [
                _extract_literal_value(v, dialect=dialect)
                for v in node.args.get("expressions", [])
            ]
            op = "NOT IN" if node.args.get("not") else "IN"
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator=op,
                value=in_values,
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── GT / GTE / LT / LTE ──────────────────────────────────────────────────
    comparison_map = {
        exp.GT:  ">",
        exp.GTE: ">=",
        exp.LT:  "<",
        exp.LTE: "<=",
    }
    for expr_type, op_symbol in comparison_map.items():
        if isinstance(node, expr_type):
            left, right = node.left, node.right
            if isinstance(left, exp.Column):
                table, col = _resolve_column(left, alias_map)
                filters.append(ParsedFilter(
                    table_name=table,
                    column_name=col,
                    operator=op_symbol,
                    value=_extract_literal_value(right, dialect=dialect),
                    raw_expression=node.sql(dialect=dialect)
                ))
            return

    # ── IS NULL / IS NOT NULL ─────────────────────────────────────────────────
    if isinstance(node, exp.Is):
        left = node.this
        right = node.args.get("expression")
        if isinstance(left, exp.Column):
            table, col = _resolve_column(left, alias_map)
            op = "IS NOT NULL" if node.args.get("not") else "IS NULL"
            filters.append(ParsedFilter(
                table_name=table,
                column_name=col,
                operator=op,
                value=None,
                raw_expression=node.sql(dialect=dialect)
            ))
        return

    # ── Fallback: recurse for anything else (subqueries, CASE, etc.) ──────────
    for child in node.args.values():
        if isinstance(child, exp.Expression):
            _extract_conditions(child, alias_map, filters, original_sql, dialect)