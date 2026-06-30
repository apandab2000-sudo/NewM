from app.logger import get_logger
from typing import List, Dict, Any
from abc import ABC, abstractmethod
from app.core.llm_connections.base import LLMBase, TokenUsage


logger = get_logger(__name__)


class BaseAgent(ABC):
    def __init__(
        self, 
        name: str, 
        llm: LLMBase, 
        model: str, 
        dialect: str = "mssql"
    ):
        self.name = name
        self.llm = llm
        self.model = model
        self.dialect = dialect
        self.token_usage = TokenUsage()
 
    @abstractmethod
    async def _run(self, messages: List[Dict], system: str = "") -> Dict[str, Any]:
        """Calls the LLM and returns parsed JSON response."""
        raise NotImplementedError("Subclasses must implement _run")