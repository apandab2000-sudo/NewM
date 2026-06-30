from fastapi import HTTPException

async def perform_base_check(i_data, first_name, last_name, email_id, dbname, chat_id):
    user_details = await i_data.create_or_get_user(first_name=first_name, last_name=last_name, email_id=email_id)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)

    db_details = await i_data.create_or_get_db(db_name=dbname)
    if not db_details:
        raise HTTPException(detail="dataset does not exists nor created successfully", status_code=404)

    chat_details = await i_data.get_chat_details_from_chatid(chat_id)
    if not chat_details:
        raise HTTPException(detail="Chat does not exists nor created successfully", status_code=404)
    
    return user_details, db_details, chat_details
