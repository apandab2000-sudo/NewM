from app.core.llm_connections.base import LLMBase
from app.databases.vector.operations import VectorStore
import re
from app.logger import get_logger


logger = get_logger(__name__)


MAX_QUERY_LENGTH = 500
MIN_QUERY_LENGTH = 5
# PROPER_NOUN_PATTERN = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
SQL_INJECTION_PATTERNS = [
    r';\s*(DROP|DELETE|TRUNCATE|ALTER)',
    r'--\s*',
    r'/\*.*\*/',
    r'xp_',
    r'sp_',
]
IRRELEVANCE_KEYWORDS = {
    'weather', 'sports', 'news', 'music', 'movie', 'recipe', 
    'joke', 'holiday', 'traffic'
}

# special_keywords = {
#     'graph': 'graphs',
#     'chart': 'graphs',
#     'plot': 'graphs',
#     'suggest': 'suggestions',
#     'recommendation': 'suggestions',
#     'insight': 'insights',
#     'analyze': 'insights',
#     "predist": "predictions",
#     "forecast": "predictions",
#     "what if": "predictions"
# }


class UserQueryValidator:
    def __init__(self, dbname: str, llm: LLMBase, vector_db: VectorStore):
        self.dbname = dbname
        self.llm = llm
        self.vector_db = vector_db

    def run(self, user_query: str) -> bool:
        try:
            if not user_query or len(user_query) < MIN_QUERY_LENGTH:
                return {"is_valid": False, "reason": f"Query is too short. Minimum length is {MIN_QUERY_LENGTH} characters."}
            
            if len(user_query) > MAX_QUERY_LENGTH:
                return {"is_valid": False, "reason": f"Query is too long. Maximum length is {MAX_QUERY_LENGTH} characters."}
            
            if any(keyword in user_query.lower() for keyword in IRRELEVANCE_KEYWORDS):
                return {"is_valid": False, "reason": "Query contains irrelevant keywords."}
            
            for pattern in SQL_INJECTION_PATTERNS:
                if re.search(pattern, user_query, re.IGNORECASE):
                    return {"is_valid": False, "reason": "Query contains potentially malicious patterns."}
            
            # for keyword, category in special_keywords.items():
            #     if keyword in user_query.lower():
            #         return {"is_valid": False, "reason": f"Query seems to be asking for {category} which is not supported by this endpoint.", "special_handling": category}
            
            return {"is_valid": True, "reason": "Query is valid."}
       
        except Exception as e:
            logger.error(f"Error during query validation: {e}", extra={"event_type": "query_validation_error", "user_query": user_query, "error": str(e)})
            return {"is_valid": False, "reason": f"An error occurred during query validation - {str(e)}"}
        
    def get_validation_error_response(self, user_query: str, invalid_reason: str) -> str:
        return f"Your query '{user_query}' is invalid. Reason: {invalid_reason}. Please modify it and try again."