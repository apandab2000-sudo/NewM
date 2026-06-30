from sqlalchemy.ext.asyncio import AsyncSession
from .models import USER, TRANSACTION, DATASET, LLM_USAGE, CHAT, QUERY, SQL, CustomDashboards, MLModels, Reports, ReportComponents, ReportTransactions, MLModelUsage, ReportChat, ReportWorkflow, DatabaseConnection
from sqlalchemy import func, cast, Date, desc, select, and_, update
from app.logger import get_logger


logger = get_logger()


class InternalSQLHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    ################################## USER ################################################
    async def get_user_details_from_username(self, first_name: str, last_name: str):
        stmt = select(USER).where(
            and_(USER.first_name == first_name, USER.last_name == last_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, first_name: str, last_name: str, email_id: str):
        try:
            new_user = USER(
                first_name=first_name, last_name=last_name, email_id=email_id
            )
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)
            return new_user
        except Exception as e:
            await self.session.rollback()
            logger.error(f"User was not saved properly:\n{repr(e)}")
            return None

    async def create_or_get_user(self, first_name: str, last_name: str, email_id: str):
        user_details = await self.get_user_details_from_username(first_name, last_name)
        if not user_details:
            return await self.create_user(first_name, last_name, email_id)
        return user_details

    ###################################### DATASET ################################################
    async def get_db_details_from_dbname(self, db_name: str):
        stmt = select(DATASET).where(DATASET.db_name == db_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_dataset(self, db_name: str):
        try:
            new_db = DATASET(db_name=db_name)
            self.session.add(new_db)
            await self.session.commit()
            await self.session.refresh(new_db)
            return new_db
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Dataset was not created properly:\n{repr(e)}")
            return None
        
    async def create_dataset_self_serve(self, details: dict):
        new_db = DATASET(**details)
        self.session.add(new_db)
        await self.session.commit()
        await self.session.refresh(new_db)
        return new_db

    async def create_or_get_db(self, db_name: str):
        db_details = await self.get_db_details_from_dbname(db_name)
        if not db_details:
            return await self.create_dataset(db_name)
        return db_details
    
    async def get_dataset_details_from_dbname(self, db_name: str):
        stmt = (
            select(DATASET)
            .where(DATASET.db_name == db_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_dataset_details_all(self):
        stmt = select(DATASET)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_dataset_details(self, db_name: str, details: dict):
        try:
            stmt = update(DATASET).where(DATASET.db_name==db_name).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.warning(f"Dataset not modified for connection id - {db_name} - {repr(e)}")
            await self.session.rollback()
            return False
        
    async def get_dataset_and_connection_details(self, db_name: str):
        stmt = (
            select(DATASET, DatabaseConnection)
            .join(DatabaseConnection, DatabaseConnection.id == DATASET.connection_id)
            .where(DATASET.db_name == db_name)
        )
        result = await self.session.execute(stmt)
        return result.one_or_none()

    ##################################### CHAT ###########################################
    async def get_chat_details_from_chatid(self, chat_id: str):
        stmt = select(CHAT).where(CHAT.chat_id == chat_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_chat(self, chat_id: str, user_id: int, db_id: int, is_report: bool | None = None):
        try:
            new_chat = CHAT(chat_id=chat_id, user_id=user_id, db_id=db_id, is_report=is_report)
            self.session.add(new_chat)
            await self.session.commit()
            await self.session.refresh(new_chat)
            return new_chat
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Chat was not created properly:\n{repr(e)}")
            return None

    async def create_or_get_chat(self, chat_id: str, user_id: int, db_id: int, is_report: bool | None = None):
        chat_details = await self.get_chat_details_from_chatid(chat_id)
        if not chat_details:
            return await self.create_chat(chat_id, user_id, db_id, is_report)
        return chat_details

    ################################## QUERY ##############################################
    async def get_query_details_from_query(self, user_query: str):
        stmt = select(QUERY).where(QUERY.user_query == user_query)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_query_details_from_query_id(self, query_id: int):
        stmt = select(QUERY).where(QUERY.id == query_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_query(self, user_query: str, is_followup: bool = False):
        try:
            new_query = QUERY(user_query=user_query, is_followup=is_followup)
            self.session.add(new_query)
            await self.session.commit()
            await self.session.refresh(new_query)
            return new_query
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Query was not created properly:\n{repr(e)}")
            return None

    async def create_or_get_query(self, user_query: str, is_followup: bool = False):
        query_details = await self.get_query_details_from_query(user_query)
        if not query_details:
            return await self.create_query(user_query, is_followup)
        return query_details

    #################################### SQL ##########################################
    async def get_sql_details_from_sql(self, sql_code: str):
        stmt = select(SQL).where(SQL.sql_code == sql_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_sql_details_from_id(self, sql_id: int):
        stmt = select(SQL).where(SQL.id == sql_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_sql(self, sql_code: str):
        try:
            new_sql = SQL(sql_code=sql_code)
            self.session.add(new_sql)
            await self.session.commit()
            await self.session.refresh(new_sql)
            return new_sql
        except Exception as e:
            await self.session.rollback()
            logger.error(f"SQL was not created properly:\n{repr(e)}")
            return None

    async def create_or_get_sql(self, sql_code: str):
        sql_details = await self.get_sql_details_from_sql(sql_code)
        if not sql_details:
            return await self.create_sql(sql_code)
        return sql_details

    ########################################## TRANSACTIONS #############################################
    async def get_last_transaction_by_chat_id(
        self, chat_id: str, rolling_window: int = 1
    ):
        stmt = (
            select(
                QUERY.user_query,
                TRANSACTION.question_type,
                TRANSACTION.approach,
                SQL.sql_code,
                TRANSACTION.filters,
                TRANSACTION.raw_response
            )
            .join(TRANSACTION.sql, isouter=True)
            .join(TRANSACTION.query, isouter=True)
            .where(TRANSACTION.chat_id == chat_id)
            .where(TRANSACTION.question_type.notin_(["error", "chitchat"]))
            .where(TRANSACTION.is_deleted==False)
            .order_by(TRANSACTION.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        result = result.mappings().all()
        return result[:rolling_window][::-1]
    
    async def get_all_transaction_by_chat_id(self, chat_id: str):
        stmt = select(TRANSACTION).where(TRANSACTION.chat_id == chat_id)
        result = await self.session.execute(stmt)
        result = result.scalars().all()
        return result

    async def get_transaction_details_from_id(self, transaction_id: int):
        stmt = select(TRANSACTION).where(TRANSACTION.id == transaction_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_transaction(
        self,
        db_id: int,
        query_id: int,
        sql_id: int | None,
        chat_id: str | None,
        parent_transaction_id: int | None = None,
        validated_transaction: bool = False,
        comments: str | None = None,
        feedback: str | None = None,
        filters: str | None = None,
        approach: str | None = None,
        question_type: str | None = None,
        raw_response: str | None = None,
        resolved_query: str | None = None
    ):
        try:
            new_transaction = TRANSACTION(
                db_id=db_id,
                query_id=query_id,
                sql_id=sql_id,
                chat_id=chat_id,
                parent_transaction_id=parent_transaction_id,
                validated_transaction=validated_transaction,
                comments=comments,
                feedback=feedback,
                filters=filters,
                approach=approach,
                question_type=question_type,
                raw_response=raw_response,
                resolved_query=resolved_query
            )
            self.session.add(new_transaction)
            await self.session.commit()
            await self.session.refresh(new_transaction)
            return new_transaction
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Transaction was not created properly:\n{repr(e)}")
            return None

    async def create_transactions_bulk(
        self,
        transactions_data: list[dict]
    ):
        try:
            # Create TRANSACTION objects from the data
            new_transactions = [
                TRANSACTION(**transaction_data) 
                for transaction_data in transactions_data
            ]
            
            # Add all objects to session
            self.session.add_all(new_transactions)
            
            # Commit once for all insertions
            await self.session.commit()
            
            # Refresh all objects to get their IDs and updated fields
            for transaction in new_transactions:
                await self.session.refresh(transaction)
            
            logger.info(f"Successfully created {len(new_transactions)} transactions")
            return new_transactions
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Bulk transaction creation failed:\n{repr(e)}")
            return None

    async def get_sql_and_query_from_transaction(self, transaction_id: int):
        stmt = (
            select(
                QUERY.user_query,
                SQL.sql_code,
                QUERY.id.label("query_id"),
                SQL.id.label("sql_id"),
                TRANSACTION.approach,
            )
            .join(TRANSACTION.query)
            .join(TRANSACTION.sql)
            .where(TRANSACTION.id == transaction_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_transaction(self, transaction_id: int, details: dict):
        try:
            stmt = update(TRANSACTION).where(TRANSACTION.id == transaction_id).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()

    ############################# LLM USGAE #############################################
    async def add_llm_usage(
        self,
        transaction_id: int | None = None,
        api_endpoint: str = "table",
        llm: str = "gpt-4.1",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
    ):
        try:
            new_usage = LLM_USAGE(
                transaction_id=transaction_id,
                api_endpoint=api_endpoint,
                llm=llm,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
            )
            self.session.add(new_usage)
            await self.session.commit()
            await self.session.refresh(new_usage)
            return new_usage
        except Exception as e:
            await self.session.rollback()
            print(repr(e))
            return None

    ########################################## CUSTOM DASHBOARDS #############################################
    async def get_dashboards_data_by_dbid(self, db_id: int):
        stmt = select(CustomDashboards).where(CustomDashboards.db_id==db_id)
        result = await self.session.execute(stmt)
        result = result.scalars().all()
        return result  

    #################################### ML Models ##########################################
    async def get_model_details_from_id(self, model_id: int):
        stmt = select(MLModels).where(MLModels.id==model_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_models(self):
        stmt = select(MLModels)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_ml_model_details(self, db_id: int, table_name: str, target_column: str):
        stmt = select(MLModels).where(and_(MLModels.db_id == db_id, MLModels.table_name == table_name, MLModels.target_column == target_column))
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_ml_model_details_versioned(self, db_id: int, table_name: str, target_column: str, model_version: int):
        stmt = select(MLModels).where(and_(
            MLModels.db_id == db_id, 
            MLModels.table_name == table_name, 
            MLModels.target_column == target_column,
            MLModels.model_version == model_version
        ))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_model_details(self, model_id: int, details: dict):
        try:
            stmt = update(MLModels).where(MLModels.id == model_id).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
    
    async def record_ml_model_details(self, ml_dict: dict):
        try:
            new_ml = MLModels(**ml_dict)
            self.session.add(new_ml)
            await self.session.commit()
            await self.session.refresh(new_ml)
            return new_ml
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Model details were not stored properly:\n{repr(e)}")
            return None

    async def log_model_activity(self, model_id: int, user_id: int, req_type: str, time_taken: float):
        """
        Logs model usage activity to the SQL database using ORM.
        """
        try:
            # Create the object
            new_log = MLModelUsage(
                model_id=model_id,
                operation_by=user_id,
                request_type=req_type,
                execution_time_ms=time_taken
            )
            
            # Add and Commit
            self.session.add(new_log)
            await self.session.commit()
            
            logger.info(f"Successfully logged activity for model {model_id}")
            
        except Exception as e:
            # Rollback in case of error to keep session clean
            await self.session.rollback()
            logger.error(f"Failed to log model activity: {e}")

    ###################################### DAREPORT BUILDER ################################################
    async def get_report_details_from_report_id(self, report_id: int):
        stmt = select(Reports).where(Reports.id == report_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_report_details_from_db_id(self, db_id: int):
        stmt = select(Reports).where(Reports.db_id == db_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_report_data(self, report_id: int, details: dict):
        try:
            stmt = update(Reports).where(Reports.id == report_id).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.warning(f"Report could not be updated successfully - {repr(e)}")
            await self.session.rollback()
            return False
    
    async def get_report_details_from_db_id_and_report_name(self, db_id: int, report_name: str):
        stmt = select(Reports).where(and_(Reports.db_id==db_id, Reports.report_name==report_name))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_report(self, report_name: str, report_description: str | None, created_by: int, db_id: int):
        try:
            new_report = Reports(
                report_name=report_name,
                report_description=report_description,
                created_by=created_by,
                db_id=db_id
            )
            self.session.add(new_report)
            await self.session.commit()
            await self.session.refresh(new_report)
            return new_report
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Report was not created properly:\n{repr(e)}")
            return None

    async def create_or_get_report(self, db_id: int, report_name: str, report_description: str, created_by: int):
        report_details = await self.get_report_details_from_db_id_and_report_name(db_id, report_name)
        if not report_details:
            return await self.create_report(report_name, report_description, created_by, db_id)
        return report_details
    
    
    async def get_report_component_details_from_id(self, component_id: int):
        stmt = select(ReportComponents).where(ReportComponents.id == component_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_component_details_from_name_and_report_id(self, report_id: int, component_name: str | None):
        stmt = select(ReportComponents).where(and_(ReportComponents.report_id==report_id, ReportComponents.component_name==component_name))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_report_component(self, report_id: int, component_name: str | None, component_description: str | None, component_type: str | None, created_by: int):
        try:
            new_component = ReportComponents(
                report_id=report_id,
                component_name=component_name,
                component_description=component_description,
                component_type=component_type,
                created_by=created_by
            )
            self.session.add(new_component)
            await self.session.commit()
            await self.session.refresh(new_component)
            return new_component
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Report COmponent was not created properly:\n{repr(e)}")
            return None
        
    async def add_component_into_transactions(
        self, 
        component_id: int, 
        modified_by: int,
        component_state_id: int = 0, 
        query: str | None = None,
        table_details: str | None = None, 
        graph_details: str | None = None, 
        insights_details: str | None = None
    ):
        try:
            new_rt = ReportTransactions(
                component_id=component_id,
                modified_by=modified_by,
                component_state_id=component_state_id,
                query=query,
                table_details=table_details,
                graph_details=graph_details,
                insights_details=insights_details
            )
            self.session.add(new_rt)
            await self.session.commit()
            await self.session.refresh(new_rt)
            return new_rt
        except Exception as e:
            await self.session.rollback()
            logger.warning(f"Transaction not created properly - {repr(e)}")
            return None
        
    async def get_component_ids_for_report(self, report_id: int, is_active: bool = True):
        try:
            stmt = select(ReportComponents).where(and_(ReportComponents.report_id==report_id, ReportComponents.is_active==is_active))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to retrive component_ids - {repr(e)}")
            return None
        
    async def get_component_details_from_id(self, component_id: int, is_active: bool = True):
        try:
            stmt = select(ReportComponents).where(and_(ReportComponents.id==component_id, ReportComponents.is_active==is_active))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to retrive component_ids - {repr(e)}")
            return None
        

    async def get_component_last_state(self, component_id: int):
        try:
            stmt = select(ReportTransactions).where(ReportTransactions.component_id==component_id).order_by(ReportTransactions.modified_on.desc())
            result = await self.session.execute(stmt)
            return result.scalars().first()
        except Exception as e:
            logger.warning(f"componenet_fetch failed - {repr(e)}")
            return None
        
    ########## REPRT CHATS ################

    async def get_report_chat_transactions(self, chat_id: str):
        stmt = (
            select(ReportChat).where(ReportChat.chat_id==chat_id)
            .where(TRANSACTION.is_deleted==False)
            .order_by(ReportChat.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


    async def get_report_history(self, chat_id: str):
        stmt = (
            select(ReportWorkflow).where(ReportWorkflow.chat_id==chat_id)
            .order_by(ReportWorkflow.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_report_workflow_transaction(self, details: dict):
        try:
            new_txn = ReportWorkflow(**details)
            self.session.add(new_txn)
            await self.session.commit()
            await self.session.refresh(new_txn)
            return new_txn
        except Exception as e:
            await self.session.rollback()
            logger.warning(f"Report Workflow Transaction not created properly - {repr(e)}")
            return None
    

    async def add_report_chat_transaction(self, details: dict):
        try:
            new_txn = ReportChat(**details)
            self.session.add(new_txn)
            await self.session.commit()
            await self.session.refresh(new_txn)
            return new_txn
        except Exception as e:
            await self.session.rollback()
            logger.warning(f"Report chat Transaction not created properly - {repr(e)}")
            return None
        
    # DATABASE CONNECTIONS
    async def create_db_connection(self, conn_details: dict, user_id: int):
        dbc = DatabaseConnection(created_by=user_id, **conn_details)
        self.session.add(dbc)
        await self.session.commit()
        await self.session.refresh(dbc)
        return dbc
    
    async def get_db_connection(self, db_conn_id: int):
        stmt = (
            select(DatabaseConnection)
            .where(DatabaseConnection.id == db_conn_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_db_connections_all(self):
        stmt = select(DatabaseConnection)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_db_connection(self, db_conn_id: int, details: dict):
        try:
            stmt = update(DatabaseConnection).where(DatabaseConnection.id==db_conn_id).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.warning(f"Database connection not modified for connection id - {db_conn_id} - {repr(e)}")
            await self.session.rollback()
            return False




class AdminSQLHelper(InternalSQLHelper):

    def _join_to_filters(self, stmt, base_table, fltr):
        """
        Fixes the 'identifier could not be bound' error by ensuring 
        continuous join paths (e.g., USER -> CHAT -> DATASET).
        """
        if not fltr:
            return stmt

        # 1. STARTING FROM LLM_USAGE
        if base_table == LLM_USAGE:
            # We must join TRANSACTION to get to CHAT/USER/DATASET
            stmt = stmt.join(TRANSACTION, LLM_USAGE.transaction_id == TRANSACTION.id)
            if fltr.user_name:
                stmt = stmt.join(CHAT, TRANSACTION.chat_id == CHAT.chat_id)
                stmt = stmt.join(USER, CHAT.user_id == USER.id)
            if fltr.db_name:
                # If CHAT wasn't joined by user filter, we join DATASET via TRANSACTION
                stmt = stmt.join(DATASET, TRANSACTION.db_id == DATASET.id)

        # 2. STARTING FROM TRANSACTION
        elif base_table == TRANSACTION:
            if fltr.user_name:
                stmt = stmt.join(CHAT, TRANSACTION.chat_id == CHAT.chat_id)
                stmt = stmt.join(USER, CHAT.user_id == USER.id)
            if fltr.db_name:
                stmt = stmt.join(DATASET, TRANSACTION.db_id == DATASET.id)

        # 3. STARTING FROM CHAT
        elif base_table == CHAT:
            if fltr.user_name:
                stmt = stmt.join(USER, CHAT.user_id == USER.id)
            if fltr.db_name:
                stmt = stmt.join(DATASET, CHAT.db_id == DATASET.id)

        # 4. STARTING FROM USER (The one that caused the error)
        elif base_table == USER:
            if fltr.db_name:
                # FIX: Join CHAT first, then DATASET
                stmt = stmt.join(CHAT, USER.id == CHAT.user_id)
                stmt = stmt.join(DATASET, CHAT.db_id == DATASET.id)

        # 5. STARTING FROM DATASET
        elif base_table == DATASET:
            if fltr.user_name:
                # FIX: Join CHAT first, then USER
                stmt = stmt.join(CHAT, DATASET.id == CHAT.db_id)
                stmt = stmt.join(USER, CHAT.user_id == USER.id)

        # --- APPLY WHERE CLAUSES ---
        if fltr.user_name:
            fname, lname = fltr.first_last
            if fname and lname:
                stmt = stmt.where(and_(USER.first_name == fname, USER.last_name == lname))

        if fltr.db_name:
            stmt = stmt.where(DATASET.db_name == fltr.db_name)

        if fltr.api_name and base_table == LLM_USAGE:
            stmt = stmt.where(LLM_USAGE.api_endpoint == fltr.api_name)

        return stmt


    def _apply_where_filters(self, stmt, fltr):
        """Adds only the WHERE clauses. Joins must be handled by the calling method."""
        if not fltr:
            return stmt
        
        if fltr.user_name:
            fname, lname = fltr.first_last
            if fname and lname:
                stmt = stmt.where(and_(USER.first_name == fname, USER.last_name == lname))
        
        if fltr.db_name:
            stmt = stmt.where(DATASET.db_name == fltr.db_name)
            
        if fltr.api_name:
            stmt = stmt.where(LLM_USAGE.api_endpoint == fltr.api_name)
            
        return stmt

    # --- 1st CATEGORY: OVERALL DASHBOARD METHODS ---

    async def get_overall_summary_kpis(self, fltr=None):
        u_stmt = self._join_to_filters(select(func.count(func.distinct(USER.id))), USER, fltr)
        c_stmt = self._join_to_filters(select(func.count(CHAT.id)), CHAT, fltr)
        t_stmt = self._join_to_filters(select(func.count(TRANSACTION.id)), TRANSACTION, fltr)
        l_stmt = self._join_to_filters(select(func.count(LLM_USAGE.id)), LLM_USAGE, fltr)
        
        token_stmt = select(func.sum(LLM_USAGE.input_tokens + LLM_USAGE.output_tokens + LLM_USAGE.cached_tokens))
        token_stmt = self._join_to_filters(token_stmt, LLM_USAGE, fltr)

        return {
            "total_users": await self.session.scalar(u_stmt) or 0,
            "total_chats": await self.session.scalar(c_stmt) or 0,
            "total_transactions": await self.session.scalar(t_stmt) or 0,
            "total_llm_calls": await self.session.scalar(l_stmt) or 0,
            "total_tokens": (await self.session.execute(token_stmt)).scalar() or 0
        }

    async def get_chats_over_time(self, fltr=None):
        stmt = select(cast(CHAT.created_on, Date).label("date"), func.count(CHAT.id).label("count"))
        stmt = self._join_to_filters(stmt, CHAT, fltr)
        res = await self.session.execute(stmt.group_by(cast(CHAT.created_on, Date)).order_by("date"))
        return res.mappings().all()

    async def get_llm_model_distribution(self, fltr=None):
        stmt = select(LLM_USAGE.llm, func.count(LLM_USAGE.id).label("count"))
        stmt = self._join_to_filters(stmt, LLM_USAGE, fltr)
        res = await self.session.execute(stmt.group_by(LLM_USAGE.llm))
        return res.mappings().all()

    async def get_tokens_over_time(self, fltr=None):
        stmt = select(cast(LLM_USAGE.created_on, Date).label("date"), 
                      func.sum(LLM_USAGE.input_tokens + LLM_USAGE.output_tokens + LLM_USAGE.cached_tokens).label("total_tokens"))
        stmt = self._join_to_filters(stmt, LLM_USAGE, fltr)
        res = await self.session.execute(stmt.group_by(cast(LLM_USAGE.created_on, Date)).order_by("date"))
        return res.mappings().all()

    async def get_tokens_by_model_time(self, fltr=None):
        stmt = select(cast(LLM_USAGE.created_on, Date).label("date"), LLM_USAGE.llm, 
                      func.sum(LLM_USAGE.input_tokens + LLM_USAGE.output_tokens + LLM_USAGE.cached_tokens).label("total_tokens"))
        stmt = self._join_to_filters(stmt, LLM_USAGE, fltr)
        res = await self.session.execute(stmt.group_by(cast(LLM_USAGE.created_on, Date), LLM_USAGE.llm).order_by("date"))
        return res.mappings().all()

    async def get_cache_split(self, fltr=None):
        stmt = select(func.sum(LLM_USAGE.cached_tokens).label("cached_tokens"), 
                      func.sum(LLM_USAGE.input_tokens).label("input_tokens"), 
                      func.sum(LLM_USAGE.output_tokens).label("output_tokens"))
        stmt = self._join_to_filters(stmt, LLM_USAGE, fltr)
        res = await self.session.execute(stmt)
        row = res.mappings().one()
        return [{"metric": k, "value": v or 0} for k, v in row.items()]

    async def get_question_type_distribution(self, fltr=None):
        stmt = select(TRANSACTION.question_type, func.count(TRANSACTION.id).label("count"))
        stmt = self._join_to_filters(stmt, TRANSACTION, fltr)
        res = await self.session.execute(stmt.group_by(TRANSACTION.question_type))
        return res.mappings().all()

    # 2nd CATEGORY: USER / DATASET SPECIFIC METHODS ---

    async def get_user_role_distribution(self, fltr=None):
        stmt = select(USER.role, func.count(USER.id).label("count"))
        stmt = self._join_to_filters(stmt, USER, fltr)
        res = await self.session.execute(stmt.group_by(USER.role))
        return res.mappings().all()

    async def get_user_signup_trend(self, fltr=None):
        stmt = select(cast(USER.created_on, Date).label("date"), func.count(USER.id).label("count"))
        stmt = self._join_to_filters(stmt, USER, fltr)
        res = await self.session.execute(stmt.group_by(cast(USER.created_on, Date)).order_by("date"))
        return res.mappings().all()

    # async def get_daily_active_users(self, fltr=None):
    #     stmt = select(cast(CHAT.created_on, Date).label("date"), func.count(func.distinct(CHAT.user_id)).label("active_users"))
    #     stmt = self._join_to_filters(stmt, CHAT, fltr)
    #     res = await self.session.execute(stmt.group_by(cast(CHAT.created_on, Date)).order_by("date"))
    #     return res.mappings().all()

    # async def get_chats_per_user(self, fltr=None):
    #     stmt = select(USER.email_id, func.count(CHAT.id).label("chat_count")).join(CHAT, USER.id == CHAT.user_id)
    #     if fltr and fltr.db_name:
    #         stmt = stmt.join(DATASET, CHAT.db_id == DATASET.id).where(DATASET.db_name == fltr.db_name)
    #     res = await self.session.execute(stmt.group_by(USER.email_id))
    #     return res.mappings().all()

    async def get_chats_per_user(self, fltr=None):
        # We must join USER to get email_id, and CHAT to get count
        stmt = select(USER.email_id, func.count(CHAT.id).label("chat_count")).join(CHAT, USER.id == CHAT.user_id)
        
        # If user filters by db_name, join DATASET
        if fltr and fltr.db_name:
            stmt = stmt.join(DATASET, CHAT.db_id == DATASET.id)
            
        # apply where filters (user_name filter will apply to the already joined USER table)
        stmt = self._apply_where_filters(stmt, fltr)
        res = await self.session.execute(stmt.group_by(USER.email_id))
        return res.mappings().all()
    
    # async def get_dataset_usage_stats(self, fltr=None):
    #     stmt = select(DATASET.db_name, func.count(TRANSACTION.id).label("transaction_count")).join(TRANSACTION, DATASET.id == TRANSACTION.db_id)
    #     if fltr and fltr.user_name:
    #         stmt = stmt.join(CHAT, TRANSACTION.chat_id == CHAT.chat_id).join(USER, CHAT.user_id == USER.id)
    #         fname, lname = fltr.first_last
    #         stmt = stmt.where(and_(USER.first_name == fname, USER.last_name == lname))
    #     res = await self.session.execute(stmt.group_by(DATASET.db_name))
    #     return res.mappings().all()

    async def get_dataset_usage_stats(self, fltr=None):
        # Join DATASET to TRANSACTION
        stmt = select(DATASET.db_name, func.count(TRANSACTION.id).label("transaction_count")).join(TRANSACTION, DATASET.id == TRANSACTION.db_id)
        
        # If user filters by user_name, join CHAT and USER
        if fltr and fltr.user_name:
            stmt = stmt.join(CHAT, TRANSACTION.chat_id == CHAT.chat_id).join(USER, CHAT.user_id == USER.id)
            
        stmt = self._apply_where_filters(stmt, fltr)
        res = await self.session.execute(stmt.group_by(DATASET.db_name))
        return res.mappings().all()

    async def get_daily_active_users(self, fltr=None):
        stmt = select(cast(CHAT.created_on, Date).label("date"), func.count(func.distinct(CHAT.user_id)).label("active_users"))
        if fltr and fltr.user_name:
            stmt = stmt.join(USER, CHAT.user_id == USER.id)
        if fltr and fltr.db_name:
            stmt = stmt.join(DATASET, CHAT.db_id == DATASET.id)
        stmt = self._apply_where_filters(stmt, fltr)
        res = await self.session.execute(stmt.group_by(cast(CHAT.created_on, Date)).order_by("date"))
        return res.mappings().all()

    async def get_token_dist_per_tx(self, fltr=None):
        stmt = select(LLM_USAGE.transaction_id, 
                      func.sum(LLM_USAGE.input_tokens + LLM_USAGE.output_tokens + LLM_USAGE.cached_tokens).label("total_tokens"))
        stmt = self._join_to_filters(stmt, LLM_USAGE, fltr)
        res = await self.session.execute(stmt.group_by(LLM_USAGE.transaction_id))
        return res.mappings().all()
    

    async def get_distinct_users(self):
        """Returns list of distinct 'First Last' names"""
        # We concatenate in SQL for performance
        stmt = select(func.distinct(USER.first_name + " " + USER.last_name))
        res = await self.session.execute(stmt)
        return [r[0] for r in res.all() if r[0]]

    async def get_distinct_datasets(self):
        """Returns list of distinct db_names"""
        stmt = select(func.distinct(DATASET.db_name))
        res = await self.session.execute(stmt)
        return [r[0] for r in res.all() if r[0]]

    async def get_distinct_api_endpoints(self):
        """Returns list of distinct api_endpoints from usage logs"""
        stmt = select(func.distinct(LLM_USAGE.api_endpoint))
        res = await self.session.execute(stmt)
        return [r[0] for r in res.all() if r[0]]

    
    