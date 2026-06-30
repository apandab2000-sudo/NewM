from prometheus_client import Gauge, Counter, Histogram

# API MIDDLEWARE
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "Request latency",
    ["endpoint"]
)

# Pool metrics
POOL_SIZE = Gauge(
    "db_pool_size",
    "Configured pool size",
    ["db_connection_id"]
)

POOL_CHECKED_OUT = Gauge(
    "db_pool_checked_out",
    "Connections currently checked out",
    ["db_connection_id"]
)

POOL_CHECKED_IN = Gauge(
    "db_pool_checked_in",
    "Connections currently idle",
    ["db_connection_id"]
)

POOL_OVERFLOW = Gauge(
    "db_pool_overflow",
    "Current overflow connections",
    ["db_connection_id"]
)

# Query metrics
QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Query execution duration",
    ["db_name"]
)

TOTAL_QUERY_HITS = Counter(
    "db_query_calls_total",
    "Total Queries Requested",
    ["db_name"]
)

QUERY_SUCCESS = Counter(
    "db_query_success_total",
    "Total Sucessful Queries",
    ["db_name"]
)

QUERY_TIMEOUTS = Counter(
    "db_query_timeouts_total",
    "Total query timeouts",
    ["db_name"]
)

QUERY_ERRORS = Counter(
    "db_query_errors_total",
    "Total query errors",
    ["db_name"]
)

DB_REPLACE_CACHE_HITS = Counter(
    "cache_hits_instead_db_total",
    "Total results retreived from cache instead of Database hit",
    ["db_name", "endpoint"]
)


TEXT2SQL_INVALID_HITS = Counter(
    "text_to_sql_invalid_total",
    "Total invalid requests for text to sql",
    ["db_name"]
)


TEXT2SQL_HITS = Counter(
    "text_to_sql_questions_total",
    "Total requests for text to sql",
    ["db_name"]
)


TEXT2SQL_FIRST_SUCCESS = Counter(
    "text_to_sql_questions_first_success_total",
    "Total first time successful requests for text to sql",
    ["db_name"]
)


TEXT2SQL_SECOND_SUCCESS = Counter(
    "text_to_sql_questions_second_success_total",
    "Total second time successful requests for text to sql",
    ["db_name"]
)


TEXT2SQL_ERRORS = Counter(
    "text_to_sql_questions_errors_total",
    "Total error requests for text to sql",
    ["db_name"]
)


SUGGESTIONS_HITS = Counter(
    "suggestion_calls_total",
    "Total suggestions calls",
    ["db_name"]
)

SUGGESTIONS_GENERATED_PER_QUESTION = Counter(
    "suggestion_generated_per_question_total",
    "Total suggestions generated per question",
    ["db_name"]
)


SUGGESTIONS_ERRORS = Counter(
    "no_suggestions_generated_total",
    "No suggestions generated for the questions",
    ["db_name"]
)


GRAPH_HITS = Counter(
    "grpahs_calls_total",
    "Total graphs calls",
    ["db_name"]
)


GRAPHS_GENERATED_PER_QUESTION = Counter(
    "graphs_generated_per_question_total",
    "Total graphs generated per question",
    ["db_name"]
)


GRAPHS_ERRORS = Counter(
    "no_graphs_generated_total",
    "No graphs generated for the questions",
    ["db_name"]
)

INSIGHTS_HITS = Counter(
    "insights_calls_total",
    "Total insights calls",
    ["db_name"]
)

INSIGHTS_GENERATED_FOR_QUESTION = Counter(
    "insights_generated_for_question_total",
    "Insights generated for each question",
    ["db_name"]
)


INSIGHTS_GENERATION_ERRORS = Counter(
    "no_insights_generated_total",
    "No Insights generated for the questions",
    ["db_name"]
)