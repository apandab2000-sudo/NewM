from sqlalchemy.ext.asyncio import AsyncSession
from ..models import TRANSACTION
from sqlalchemy import select, update
from app.logger import get_logger


logger = get_logger(__name__)


class TransactionsHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_transaction_record(
        self, 
        chat_id: str,
        query_id: int,
        sql_id: int,
               
    ):
        ...
