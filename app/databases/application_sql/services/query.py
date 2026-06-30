from sqlalchemy.ext.asyncio import AsyncSession
from ..models import QUERY
from sqlalchemy import select, update
from app.logger import get_logger


logger = get_logger(__name__)


class UsersHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_query_details(self, query_id: int):
        try:
            stmt = select(QUERY).where(QUERY.id == query_id)
            result = await self.session.execute(stmt)
            query = result.scalar_one_or_none()
            return query
        except Exception as e:
            logger.error("Error fetching query details", extra={"event_type": "fetch_query_details_error", "query_id": query_id, "error": str(e)})
            return None

    async def create_query_record(self, user_query: str):
        try:
            new_query = QUERY(user_query=user_query)
            self.session.add(new_query)
            await self.session.commit()
            await self.session.refresh(new_query)
            return new_query.id
        except Exception as e:
            logger.error("Error creating query record", extra={"event_type": "create_query_record_error", "user_query": user_query, "error": str(e)})
            return None