import re
from typing import Literal


EditGraphIntent = Literal["forecast", "driver_analysis", "next_question"]


FORECAST_TERMS = (
    "forecast",
    "predict",
    "prediction",
    "projection",
    "project",
    "estimate future",
    "future value",
    "future trend",
    "time series",
)

DRIVER_ANALYSIS_TERMS = (
    "driver",
    "drivers",
    "drive",
    "drives",
    "driving",
    "drove",
    "driver analysis",
    "key factor",
    "key factors",
    "contributing factor",
    "contributing factors",
    "cause",
    "causes",
    "caused",
    "root cause",
    "reason",
    "reasons",
    "why",
    "impact",
    "influence",
    "correlation",
    "correlated",
    "explain change",
    "explain variance",
)

# NEXT_QUESTION_TERMS = (
#     "also",
#     "what about",
#     "how about",
#     "same for",
#     "instead",
#     "now show",
#     "show instead",
#     "change to",
#     "filter to",
#     "compare with",
#     "compare to",
#     "can you also",
#     "next question",
# )

FUTURE_PERIOD_PATTERN = re.compile(
    r"\b(next|coming|upcoming|following)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(day|days|week|weeks|month|months|quarter|quarters|year|years)\b",
    flags=re.IGNORECASE,
)


def detect_edit_graph_intent(query: str) -> EditGraphIntent:
    normalized_query = " ".join(query.lower().split())

    has_future_period = bool(FUTURE_PERIOD_PATTERN.search(normalized_query))
    has_forecast_term = any(term in normalized_query for term in FORECAST_TERMS)
    has_driver_term = any(term in normalized_query for term in DRIVER_ANALYSIS_TERMS)
    # has_next_question_term = any(term in normalized_query for term in NEXT_QUESTION_TERMS)

    if has_forecast_term or has_future_period:
        return "forecast"
    if has_driver_term:
        return "driver_analysis"
    else:
        return "next_question"
