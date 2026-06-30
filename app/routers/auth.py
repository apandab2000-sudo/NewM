from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import FastAPI, HTTPException, Depends, status
from passlib.context import CryptContext
from app.databases.application_sql.services.users import UsersHelper
from app.logger import get_logger
from app.databases.dependencies import get_db_async
from sqlalchemy.ext.asyncio import AsyncSession


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic()


logger = get_logger()


ADMIN_PASSWORD = "Iod@1234"


async def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_async)
):
    users_helper = UsersHelper(session)

    # if "@" in credentials.username:
    #     email_id = credentials.username.lower().strip()
    # else:
    #     user_name = credentials.username.lower().strip().split()
    #     email_id = f"{user_name[0]}.{user_name[1]}@eclerx.com"
    raw_username = credentials.username.lower().strip()

    if "@" in raw_username:
        email_id = raw_username
    else:
        if "." in raw_username:
            user_name = raw_username.split(".")
        else:
            user_name = raw_username.split()

        if len(user_name) < 2:
            raise HTTPException(
                status_code=401,
                detail="Invalid username format. Use full email, firstname.lastname, or firstname lastname"
            )

        email_id = f"{user_name[0]}.{user_name[1]}@eclerx.com"

    user_details = await users_helper.get_user_details_from_email(email_id)
    
    if not user_details:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    user_hashed_password = get_hashed_password(ADMIN_PASSWORD)

    password_verification = pwd_context.verify(credentials.password, user_hashed_password)
    if not password_verification:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return user_details

def get_hashed_password(password: str):
    return pwd_context.hash(password)

async def check_admin(user = Depends(get_current_user)):
    # if user.role not in ("admin", "super_admin"):
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return user

