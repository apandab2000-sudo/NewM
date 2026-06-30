from sqlalchemy.ext.asyncio import AsyncSession
from ..models import DatabaseConnection
from sqlalchemy import select, update
from app.logger import get_logger


logger = get_logger(__name__)


class DataBaseConnectionHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_db_connections(self):
        try:
            stmt = select(
                DatabaseConnection.id, 
                DatabaseConnection.name, 
                DatabaseConnection.description,
                DatabaseConnection.dialect
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error("Error fetching database connections", extra={"event_type": "fetch_db_connections_error", "error": str(e)})
            return []
        
    async def get_db_connection(self, db_conn_id: int):
        try:
            stmt = select(DatabaseConnection).where(DatabaseConnection.id == db_conn_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("Error fetching database connection", extra={"event_type": "fetch_db_connection_error", "db_conn_id": db_conn_id, "error": str(e)})
            return None
        
    async def create_db_connection(self, conn_details: dict, user_id: int):
        try:
            dbc = DatabaseConnection(created_by=user_id, **conn_details)
            self.session.add(dbc)
            await self.session.commit()
            await self.session.refresh(dbc)
            return dbc
        except Exception as e:
            await self.session.rollback()
            logger.error("Error creating database connection", extra={"event_type": "create_db_connection_error", "error": str(e), "user_id": user_id,})
            return None

    async def update_db_connection(self, db_conn_id: int, details: dict):
        try:
            stmt = update(DatabaseConnection).where(DatabaseConnection.id==db_conn_id).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.warning("Database connection not modified", extra={"event_type": "update_db_connection_error", "db_conn_id": db_conn_id, "error": str(e)})
            await self.session.rollback()
            return False

    async def get_db_connection_by_uid_host_port(self, username: str, host: str, port: int):
        try:
            stmt = select(DatabaseConnection).where(
                DatabaseConnection.username == username,
                DatabaseConnection.host == host,
                DatabaseConnection.port == port
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("Error fetching database connection by UID, host, and port", extra={"event_type": "fetch_db_connection_by_details_error", "username": username, "host": host, "port": port, "error": str(e)})
            return None