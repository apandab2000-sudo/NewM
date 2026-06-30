from sqlalchemy.ext.asyncio import AsyncSession
from ..models import CHAT, DATASET, USER, DatabaseConnection
from sqlalchemy import select, update, text
from app.logger import get_logger
from sqlalchemy import func
import uuid


logger = get_logger(__name__)


class ChatsHelper:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create_chat_id(self, user_id: int, dataset_id: int) -> str:
         chat_id = str(uuid.uuid4()) + "-" + str(user_id) + "-" + str(dataset_id)

         try:
            new_chat = CHAT(chat_id=chat_id, user_id=user_id, db_id=dataset_id)
            self.db_session.add(new_chat)
            await self.db_session.commit()
            await self.db_session.refresh(new_chat)
            return chat_id
         except Exception as e:
            logger.error(f"Error creating chat ID: {e}", extra={"event_type": "chat_id_creation_error", "error": str(e)})
            raise
         
    async def get_chat_details(self, chat_id: str):
        try:
            stmt = select(CHAT, DATASET, USER, DatabaseConnection).\
                    join(USER, USER.id == CHAT.user_id).\
                    join(DATASET, DATASET.id == CHAT.db_id).\
                    join(DatabaseConnection, DatabaseConnection.id == DATASET.connection_id).\
                    where(CHAT.chat_id == chat_id)
            result = await self.db_session.execute(stmt)
            return result.one_or_none()
        except Exception as e:
            logger.error(f"Error fetching chat details: {e}", extra={"event_type": "chat_details_fetch_error", "chat_id": chat_id, "error": str(e)})
            raise