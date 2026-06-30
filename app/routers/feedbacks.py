from fastapi import APIRouter, HTTPException, Depends
from app.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.dependencies import get_db_async
from app.models import PositiveFeedback, NegativeFeedback
from app.databases.application_sql.operations import InternalSQLHelper
import json

router = APIRouter(prefix="/egai", tags=["Feedback"])

logger = get_logger()


@router.post("/positiveFeedback", status_code=201)
async def record_positive_feedback(
    data: PositiveFeedback,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    transaction_details = await i_data.get_transaction_details_from_id(transaction_id=data.transaction_id)

    if not transaction_details:
        raise HTTPException(detail="Invalid transaction details", status_code=404)

    await i_data.update_transaction(
        transaction_id=data.transaction_id,
        details={"validated_transaction": True}
    )

    return {
        "comments": "Feedback recorded",
        "status": 201,
        "status_message": "Success"
    }


@router.post("/feedback/negativeFeedback", status_code=201)
async def record_negative_feedback(
    data: NegativeFeedback,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    feedback_list_str = json.dumps(data.feedback_list)

    try:
        await i_data.update_transaction(data.transaction_id, {"comments": feedback_list_str})
        return {
            "comments": "Feedback recorded",
            "status": 201,
            "status_message": "Success"
        }
    except Exception as e:
        logger.warning(repr(e))
        raise HTTPException(detail="feedback not recorded promperly", status_code=400)