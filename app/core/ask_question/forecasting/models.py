from typing import Any, Literal

from pydantic import BaseModel

# Data shape passed between forecasting and chart-building code.
class ForecastResult(BaseModel):
    table: list[dict[str, Any]]
    time_column: str
    value_column: str
    periods: int
    confidence: Literal["low", "medium", "high"]
    warning: str | None = None
