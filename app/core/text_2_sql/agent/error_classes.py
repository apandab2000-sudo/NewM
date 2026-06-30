
class QueryUnderstandingError(Exception):
    """Raised when query understanding fails"""
    ...


class QueryValidationError(Exception):
    """Raised when query validation fails"""
    ...


class QueryResolutionError(Exception):
    """Raised when query resolution fails"""
    ...


class NLUExtractionError(Exception):
    """Raised when NLU extraction fails"""
    ...


class SchemaRetrievalError(Exception):
    """Raised when schema retrieval fails"""
    ...


class QueryPlanningError(Exception):
    """Raised when query planning fails"""
    ...


class SQLGenerationError(Exception):
    """Raised when SQL generation fails"""
    ...


class SQLExecutionError(Exception):
    """Raised when SQL execution fails"""
    ...