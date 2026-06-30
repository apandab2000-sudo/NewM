from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from app.core.chat_interface.introduction_text import IntroductionText
from app.core.chat_interface.prompt_suggestions import PromptSuggestions
from app.logger import get_logger
from app.models import ReseChatWIthAddOns,  UpdateFiltersInput
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.dependencies import get_db_async, get_pool, client_pool_manager
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.application_sql.services.users import UsersHelper
from app.databases.application_sql.services.chats import ChatsHelper
from app.core.chat_interface.filters import ChatFilters
from app.api_models.chats import UpdateFiltersRequest, FiltersResponse 


router = APIRouter(prefix="/egai", tags=["Chat"])


logger = get_logger(__name__)


@router.get(
    "/chat/id",
    summary="Get Chat ID. Chat ID can be used to uniquely define a conversation.",
    description="Get a unique chat ID for the conversation. This can be used to track and manage conversations.",
    response_description="Unique chat ID",
    responses={
        200: {"description": "Successfully retrieved chat ID"},
        500: {"description": "Failed to generate chat ID"},
        404: {"description": "User or dataset not found"}
    },
    status_code=200,
)
async def get_chat_id(
    user_name: str = Query(..., description="Full name of the user in 'First Last' format"),
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    db_session=Depends(get_db_async)
):
    users_helper = UsersHelper(db_session)
    dataset_helper = DatasetHelper(db_session)
    chats_helper = ChatsHelper(db_session)

    user_name = user_name.split(" ")
    email_id = f"{user_name[0]}.{user_name[1]}@eclerx.com"

    user = await users_helper.get_user_details_from_email(email_id)
    if not user:
        raise HTTPException(status_code=404, detail="User with provided email does not exist")

    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset with provided name does not exist")
    
    # inserting chat_id into database
    try:
        chat_id = await chats_helper.create_chat_id(user.id, dataset.id)
        return {
            "message": "Chat ID successfully generated",
            "chat_id": chat_id
        }
    except Exception as e:
        logger.error(f"Error generating chat ID: {e}", extra={"event_type": "chat_id_generation_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to generate chat ID")


@router.get(
    "/chat/filters",
    summary="Get available filters for a dataset",
    description="Retrieve available filters for a given dataset. These filters can be used to refine the conversation context.",
    response_description="List of available filters",
    responses={
        200: {"description": "Successfully retrieved filters"},
        500: {"description": "Failed to retrieve filters"},
        404: {"description": "Dataset not found"}
    },
    status_code=200, 
    response_model=FiltersResponse
)
async def get_filters(
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    use_cache: bool = Query(True, description="Whether to use cached filters if available"),
    db_session=Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)
    
    dataset, connection = await dataset_helper.get_dataset_and_connection_details(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    client_pool = await get_pool(dataset, connection)

    try:
        chat_filters = ChatFilters(dbname, client_pool)
        filters_info = await chat_filters.get_filters(use_cache=use_cache)
        return {
            "filters": filters_info
        }
    except Exception as e:
        logger.error(f"Error retrieving filters: {e}", extra={"event_type": "filters_retrieval_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to retrieve filters")


@router.post(
    "/chat/filters", 
    summary="Update selected filters for a dataset",
    description="Update the selected filters for a given dataset. This will refine the conversation context based on the selected filters.",
    response_description="Updated list of filters based on selection",
    responses={
        200: {"description": "Successfully updated filters"},
        500: {"description": "Failed to update filters"},
        404: {"description": "Dataset not found"}
    },
    status_code=200
)
async def update_filters(
    payload: UpdateFiltersRequest,
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    use_cache: bool = Query(True, description="Whether to use cached filters if available"),
    db_session = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)
    dataset, connection = await dataset_helper.get_dataset_and_connection_details(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset with provided name does not exist")
    
    if not connection:
        raise HTTPException(status_code=404, detail="Database connection for the dataset not found")

    client_pool = await get_pool(dataset, connection)

    try:
        chat_filters = ChatFilters(dbname, client_pool)
        filters_info = await chat_filters.update_filters_with_selection(payload.filters, use_cache)
        return {
            "filters": filters_info
        }
    except Exception as e:
        logger.error(f"Error updating filters: {e}", extra={"event_type": "filters_update_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to update filters")


@router.get(
    "/chat/prompt-suggestions",
    summary="Get prompt suggestions for a dataset",
    description="Retrieve prompt suggestions for a given dataset. These suggestions can help users formulate their queries more effectively.",
    response_description="List of prompt suggestions",
    responses={
        200: {"description": "Successfully retrieved prompt suggestions"},
        500: {"description": "Failed to retrieve prompt suggestions"},
        404: {"description": "Dataset not found"}
    },
    status_code=200
)
async def get_prompt_suggestions(
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    use_cache: bool = Query(True, description="Whether to use cached prompt suggestions if available"),
    db_session=Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)
    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset with provided name does not exist")
    
    try:
        prompt_suggestions_obj = PromptSuggestions(dbname)
        prompt_suggestions = prompt_suggestions_obj.get(use_cache=use_cache)
        return {
            "prompt_suggestions": prompt_suggestions
        }
    except Exception as e:
        logger.error(f"Error retrieving prompt suggestions: {e}", extra={"event_type": "prompt_suggestions_retrieval_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to retrieve prompt suggestions")


@router.get(
    "/chat/introduction-text",
    summary="Get introduction text for a dataset",
    description="Retrieve introduction text for a given dataset. This text can provide an overview or context about the dataset to the users.",
    response_description="Introduction text for the dataset",
    responses={
        200: {"description": "Successfully retrieved introduction text"},
        500: {"description": "Failed to retrieve introduction text"},
        404: {"description": "Dataset not found"}
    },
    status_code=200
)
async def get_introduction_text(
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    db_session=Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)
    dataset = await dataset_helper.get_dataset_by_name(dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset with provided name does not exist")
    
    try:
        introduction_text_obj = IntroductionText(dbname)
        db_description = introduction_text_obj.get()
        return {
            "introduction_text": db_description
        }
    except Exception as e:
        logger.error(f"Error retrieving introduction text: {e}", extra={"event_type": "introduction_text_retrieval_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to retrieve introduction text")



@router.post("/resetChat", status_code=200, deprecated=True)
async def reset_chat(
    data: ReseChatWIthAddOns, 
    db_session: AsyncSession = Depends(get_db_async)
):    
    dataset_helper = DatasetHelper(db_session)
    users_helper = UsersHelper(db_session)
    chats_helper = ChatsHelper(db_session)

    dataset, connection = await dataset_helper.get_dataset_and_connection_details(data.dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    client_pool = await get_pool(dataset, connection)

    user = await users_helper.get_user_details_from_email(data.email_id)
    if not user:
        raise HTTPException(status_code=404, detail="User with provided email does not exist")

    try:
        chat_id = await chats_helper.create_chat_id(user.id, dataset.id)
    except Exception as e:
        raise HTTPException(
            detail="Chat does not exists nor created successfully", status_code=404
        )

    chat_filters = ChatFilters(data.dbname, client_pool)
    try:
        filters_info = await chat_filters.get_filters(use_cache=data.use_filters_cache)
    except Exception as e:
        filters_info = []
        logger.warning(f"Failed to retrieve chat filters: {e}", extra={"event_type": "chat_filters_retrieval_error", "error": str(e)})

    try:
        prompt_suggestions_obj = PromptSuggestions(data.dbname)
        prompt_suggestions = prompt_suggestions_obj.get(use_cache=data.use_prompt_suggestions_cache)
    except Exception as e:
        prompt_suggestions = []
        logger.warning(f"Failed to retrieve prompt suggestions: {e}", extra={"event_type": "prompt_suggestions_retrieval_error", "error": str(e)})

    try:
        introduction_text_obj = IntroductionText(data.dbname)
        db_description = introduction_text_obj.get()
    except Exception as e:
        db_description = ""
        logger.warning(f"Failed to retrieve introduction text: {e}", extra={"event_type": "introduction_text_retrieval_error", "error": str(e)})
 
    return {
        "chat_id": chat_id,
        "filters": filters_info,
        "queries": prompt_suggestions,
        "db_description": db_description,
        "status": 200,
        "status_message": "Success",
    }


@router.post("/update_filters", status_code=200, deprecated=True)
async def update_filters(
    data: UpdateFiltersInput, db_session: AsyncSession = Depends(get_db_async)
):
    dataset_helper = DatasetHelper(db_session)

    dataset, connection = await dataset_helper.get_dataset_and_connection_details(data.dbname)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    client_pool = await get_pool(dataset, connection)

    try:
        chat_filters = ChatFilters(data.dbname, client_pool)
        filters_info = await chat_filters.update_filters_with_selection(data.filters)
    except Exception as e:
        filters_info = []
        logger.warning(f"Failed to update chat filters: {e}", extra={"event_type": "chat_filters_update_error", "error": str(e)})

    return {
        "chat_id": data.chat_id,
        "filters": filters_info,
        "status": 200,
        "status_message": "Success",
    }


@router.post('/autoComplete', deprecated=True, status_code=200)
async def auto_suggest(db_session: AsyncSession = Depends(get_db_async)):
    return {"data": [], "status": 200, "status_message": "Success"}


@router.get(
    '/chat/autoComplete',
    summary="Get auto-suggestions for user queries",
    description="Retrieve auto-suggestions for user queries based on the dataset. This can help users formulate their queries more effectively.",
    response_description="List of auto-suggestions for user queries",
    responses={
        200: {"description": "Successfully retrieved auto-suggestions"},
        500: {"description": "Failed to retrieve auto-suggestions"},
        404: {"description": "Dataset not found"}
    },
    status_code=200
)
async def get_auto_suggestions(
    dbname: str = Query(..., description="Name of the dataset to be used in the conversation"),
    use_cache: bool = Query(True, description="Whether to use cached auto-suggestions if available"),
    db_session: AsyncSession = Depends(get_db_async)
):
    # Functionality not implemented yet, returning empty list for now
    return {"auto_suggestions": []}

