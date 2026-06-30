from sqlalchemy.ext.asyncio import AsyncSession
from ..models import USER
from sqlalchemy import select, update
from app.logger import get_logger


logger = get_logger(__name__)


class UsersHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_details_from_email(self, email_id: str):
        try:
            stmt = select(USER).where(USER.email_id == email_id)
            result = await self.session.execute(stmt)
            user = result.scalar_one_or_none()
            return user
        except Exception as e:
            logger.error("Error fetching user details", extra={"event_type": "fetch_user_details_error", "email_id": email_id, "error": str(e)})
            return None
