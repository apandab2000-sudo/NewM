from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ShareConversation, DeleteConversation, DeleteUserQuestion
from app.logger import get_logger
from app.databases.dependencies import (
    get_db_async, 
    get_vector_client,
    get_nosql_client,
    get_pool,
)
from app.databases.client_sql.operations import get_table_from_sql, get_table_and_status_and_columns, get_table_from_sql_parallel
from app.databases.application_nosql.operations import NOSQLHelper
from app.databases.application_sql.operations import InternalSQLHelper
import uuid
import copy
# from app.core.table_from_sql import get_table_from_sql
# from app.core.helper import get_table_and_status_and_columns

router = APIRouter(prefix="/egai", tags=["Conversations"])

logger = get_logger()


@router.post("/navigation/shareConversation", status_code=201)
async def share_conversation(
    data: ShareConversation,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    # nosql_client = get_nosql_client()
    nosql_helper = NOSQLHelper()

    transactions_list = await i_data.get_all_transaction_by_chat_id(data.chat_id)
    
    if not transactions_list:
        raise HTTPException(detail="No Transactions forund", status_code=404)
    
    db_details = await i_data.get_db_details_from_dbname(data.dbname)
    
    no_sql_transaction_details_list = []
    for t in transactions_list:
        nt = await nosql_helper.get_transaction(t.id)
        no_sql_transaction_details_list.append(nt)

    final_output = []
    for user in data.target_users:
        user_details = await i_data.get_user_details_from_username(user.first_name, user.last_name)
        
        if not user_details:
            logger.warning("Conversaton cannot be shared with non-existing user")
            continue
        
        chat_id = str(uuid.uuid4()) + "-" + str(user_details.id) + "-" + str(db_details.id)
        chat_details = await i_data.create_or_get_chat(
            chat_id=chat_id, user_id=user_details.id, db_id=db_details.id
        )

        transactions_list_for_user = copy.deepcopy(transactions_list)
        new_transactions_list_for_user = []
        for t in transactions_list_for_user:
            t = t.to_dict()
            t["chat_id"] = chat_id
            del t["id"]
            new_transactions_list_for_user.append(t)
        
        new_transaction_details = await i_data.create_transactions_bulk(new_transactions_list_for_user)

        if not new_transaction_details:
            logger.error("new transactions not created properly")

        new_no_sql_transaction_details_list = []
        for nt, t in zip(no_sql_transaction_details_list, new_transaction_details):
            new_nt = {
                "transaction_id": t.id,
                "table": nt.table,
                "approach": nt.approach,
                "graphs": nt.graphs,
                "suggestions": nt.suggestions,
                "insights": nt.insights
            }
            new_no_sql_transaction_details_list.append(new_nt)

        await nosql_helper.record_transactions_bulk(new_no_sql_transaction_details_list)
        final_output.append({"user_name": user.user_name, "chat_id": chat_id})

    return {
        "data": final_output, 
        "status": 200, 
        "status_message": "Success"
    }


@router.post('/deleteConversation', status_code=200)
async def delete_conversation(
    data: DeleteConversation,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    transactions_details_list = await i_data.get_all_transaction_by_chat_id(data.chat_id)

    if not transactions_details_list:
        raise HTTPException(detail="No Transactions forund", status_code=404)
    
    for t in transactions_details_list:
        await i_data.update_transaction(
            transaction_id=t.id,
            details={"is_deleted": True}
        )

    return {
        "status": 200,
        "status_message": "Conversation have been deleted."
    }



@router.post('/deleteUserQuestion', status_code=200)
async def delete_user_question(
    data: DeleteUserQuestion,
    session: AsyncSession = Depends(get_db_async)
):  
    i_data = InternalSQLHelper(session)

    transactons_details = await i_data.get_transaction_details_from_id(data.transaction_id)

    await i_data.update_transaction(
            transaction_id=transactons_details.id,
            details={"is_deleted": True}
        )

    return {
        "status": 200,
        "status_message": "Transaction have been deleted successfully."
    }


@router.post('/refreshUserQuestion', status_code=200)
async def refresh_user_question(
    data: DeleteUserQuestion,
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)
    # nosql_client = get_nosql_client()
    # nosql_helper = NOSQLHelper()
    # client_pool = client_connection_pool

    fectched_details = await i_data.get_dataset_and_connection_details(db_name=data.dbname)
    if not fectched_details:
        raise HTTPException(status_code=404, detail="Dataset and DB COnnection not found") 
    
    db_details, connection_details = fectched_details
    client_pool = await get_pool(db_details, connection_details)

    transactons_details = await i_data.get_transaction_details_from_id(data.transaction_id)

    if not transactons_details:
        logger.error("Invalid transaction details")
        raise HTTPException(detail="Invalid transaction details", status_code=404)
    
    if transactons_details.sql_id:
        sql_details = await i_data.get_sql_details_from_id(transactons_details.sql_id)
        if sql_details:
            sql_code = sql_details.sql_code
            query_results = await get_table_from_sql(client_pool, data.dbname, sql_details.sql_code)
            table_json, table_status, table_columns = get_table_and_status_and_columns(query_results)
        else:
            sql_code = None
            table_json = []
            table_columns = {}
    else:
        sql_code = None
        table_json = []
        table_columns = {}

    if not sql_details:
        logger.warning("SQL not found")
    
    return {
        "query_key": str(transactons_details.id),
        'status': 200,
        'status_message': 'Success',
        'multiple_response': False,
        "sql": sql_code,
        "table_columns": table_columns,
        "table": table_json,
        "approach": transactons_details.approach,
        "sql_response": sql_code
    }