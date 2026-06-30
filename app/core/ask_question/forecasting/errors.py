# Custom exceptions returned as clean graph edit API errors.
class GraphEditError(Exception):
    """Base error for graph edit operations."""


class ForecastNotPossible(GraphEditError):
    """Raised when a table cannot support a forecast."""
