from sqlalchemy.ext.asyncio import AsyncSession
from ..models import DATASET, DatabaseConnection
from sqlalchemy import select, update, text
from app.logger import get_logger
from sqlalchemy import func
import asyncio
from app.databases.client_sql.connections import ConnectionPoolFactory
from app.databases.client_sql.operations import get_table_from_sql


logger = get_logger(__name__)


class DatasetHelper:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_datasets(self):
        try:
            stmt = select(
                DATASET.id, 
                DATASET.db_name
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error("Error fetching datasets", extra={"event_type": "fetch_datasets_error", "error": str(e)})
            return []

    async def get_dataset_by_name(self, db_name: str):
        try:
            stmt = select(DATASET).where(DATASET.db_name == db_name)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("Error fetching dataset details", extra={"event_type": "fetch_dataset_details_error", "db_name": db_name, "error": str(e)})
            return None
        
    async def create_dataset(self, dataset_data: dict):
        try:
            new_dataset = DATASET(**dataset_data)
                # db_name=dataset_data["db_name"],
                # db_schema=dataset_data.get("db_schema"),
                # ai_provider=dataset_data["ai_provider"],
                # ai_model_mappings=dataset_data.get("ai_model_mappings") if dataset_data.get("ai_model_mappings") else None,
                # graph_type=dataset_data["graph_type"],
                # connection_id=dataset_data["connection_id"]
            # )
            self.session.add(new_dataset)
            await self.session.commit()
            await self.session.refresh(new_dataset)
            return new_dataset
        except Exception as e:
            logger.error("Error creating dataset", extra={"event_type": "create_dataset_error", "db_name": dataset_data["db_name"], "error": str(e)})
            await self.session.rollback()
            return None
        
    async def update_dataset(self, db_name: str, details: dict):
        try:
            stmt = update(DATASET).where(DATASET.db_name==db_name).values(**details)
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.warning("Dataset not modified", extra={"event_type": "update_dataset_error", "db_name": db_name, "error": str(e)})
            await self.session.rollback()
            return False

    async def refresh_dataset(self, db_name: str):
        try:
            logger.info("Refreshing dataset", extra={"event_type": "refresh_dataset", "db_name": db_name})
            stmt = update(DATASET).where(DATASET.db_name==db_name).values(last_refresh_date=func.now())
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.error("Error refreshing dataset", extra={"event_type": "refresh_dataset_error", "db_name": db_name, "error": str(e)})
            await self.session.rollback()
            return False
        
    async def get_dataset_and_connection_details(self, db_name: str):
        try:
            stmt = select(
                DATASET,
                DatabaseConnection
            ).join(DatabaseConnection, DatabaseConnection.id == DATASET.connection_id).where(DATASET.db_name == db_name)
            result = await self.session.execute(stmt)
            return result.one_or_none()
        except Exception as e:
            logger.error("Error fetching dataset and connection details", extra={"event_type": "fetch_dataset_connection_details_error", "db_name": db_name, "error": str(e)})
            return None

    async def create_filter_table(
        self,
        db_name: str,
        table_mappings: list,
        join_conditions: list = None,
        filter_table_name: str = None,
        connection_pool: object = None
    ):
        """
        Create a new filter table by joining specified tables and selecting specific columns.
        
        Args:
            db_name: Dataset name for logging
            table_mappings: List of dicts with 'table_name' and 'columns' keys
            join_conditions: List of join condition dicts or None for single table
            filter_table_name: Custom name for filter table or None for auto-generated
            connection_pool: ConnectionPoolFactory pool instance for executing SQL
            
        Returns:
            dict with 'success' status and 'table_name' of created filter table or error details
        """
        try:
            if not connection_pool:
                logger.error("Connection pool not provided", extra={"event_type": "create_filter_table_error", "db_name": db_name})
                return {"success": False, "error": "Connection pool not provided"}

            # Generate filter table name if not provided
            if not filter_table_name:
                filter_table_name = f"filter_table_{db_name}_{int(func.now().compile().string.replace('now()', ''))}"

            # Build SELECT clause with all columns
            select_parts = []
            for mapping in table_mappings:
                table_name = mapping.get("table_name")
                columns = mapping.get("columns", [])
                alias = mapping.get("alias", table_name)
                
                for col in columns:
                    select_parts.append(f"{alias}.[{col}]")

            if not select_parts:
                logger.warning("No columns specified for filter table", extra={"event_type": "no_columns_specified", "db_name": db_name})
                return {"success": False, "error": "No columns specified for filter table"}

            select_clause = ", ".join(select_parts)

            # Build FROM clause with joins
            from_clause = f"[{table_mappings[0]['table_name']}] AS {table_mappings[0].get('alias', table_mappings[0]['table_name'])}"
            
            if join_conditions:
                for join_cond in join_conditions:
                    join_type = join_cond.get("join_type", "INNER")
                    table1_alias = next((m.get("alias", m["table_name"]) for m in table_mappings if m["table_name"] == join_cond["table1"]), join_cond["table1"])
                    table2_name = join_cond["table2"]
                    table2_alias = next((m.get("alias", m["table_name"]) for m in table_mappings if m["table_name"] == table2_name), table2_name)
                    on_clause = join_cond.get("on_clause", "")
                    
                    from_clause += f" {join_type} JOIN [{table2_name}] AS {table2_alias} ON {on_clause}"

            # Build CREATE TABLE AS SELECT statement
            create_table_sql = f"SELECT {select_clause} INTO [{filter_table_name}] FROM {from_clause}"

            logger.info("Creating filter table", extra={
                "event_type": "creating_filter_table",
                "db_name": db_name,
                "filter_table_name": filter_table_name,
                "num_tables": len(table_mappings),
                "sql": create_table_sql
            })

            # Execute table creation
            async with connection_pool.get_session() as session:
                result = await session.execute(text(create_table_sql))
                await session.commit()

            # Create indexes on each column
            index_results = await self._create_indexes_on_columns(
                filter_table_name,
                [col for mapping in table_mappings for col in mapping.get("columns", [])],
                connection_pool,
                db_name
            )

            if not index_results["success"]:
                logger.warning("Some indexes failed to create", extra={
                    "event_type": "index_creation_partial_failure",
                    "db_name": db_name,
                    "filter_table_name": filter_table_name,
                    "failed_indexes": index_results.get("failed_indexes", [])
                })

            return {
                "success": True,
                "table_name": filter_table_name,
                "columns": [col for mapping in table_mappings for col in mapping.get("columns", [])],
                "indexes_created": len(index_results.get("created_indexes", [])),
                "message": f"Filter table '{filter_table_name}' created successfully with {len(index_results.get('created_indexes', []))} indexes"
            }

        except Exception as e:
            logger.error("Error creating filter table", extra={
                "event_type": "create_filter_table_error",
                "db_name": db_name,
                "filter_table_name": filter_table_name,
                "error": str(e)
            })
            return {"success": False, "error": str(e)}

    async def _create_indexes_on_columns(
        self,
        table_name: str,
        columns: list,
        connection_pool: object,
        db_name: str = None
    ):
        """
        Create indexes on specified columns in a table.
        
        Args:
            table_name: Table name to create indexes on
            columns: List of column names
            connection_pool: Database connection pool
            db_name: Dataset name for logging
            
        Returns:
            dict with 'success' status and lists of 'created_indexes' and 'failed_indexes'
        """
        created_indexes = []
        failed_indexes = []

        try:
            for column in columns:
                if not column:
                    continue
                    
                index_name = f"idx_{table_name}_{column}".replace(" ", "_").replace("-", "_")[:128]  # SQL Server limit
                create_index_sql = f"CREATE INDEX [{index_name}] ON [{table_name}] ([{column}])"

                try:
                    async with connection_pool.get_session() as session:
                        await session.execute(text(create_index_sql))
                        await session.commit()
                    
                    created_indexes.append(index_name)
                    logger.debug("Index created", extra={
                        "event_type": "index_created",
                        "db_name": db_name,
                        "table_name": table_name,
                        "index_name": index_name,
                        "column": column
                    })

                except Exception as col_error:
                    failed_indexes.append({
                        "column": column,
                        "error": str(col_error)
                    })
                    logger.warning("Failed to create index on column", extra={
                        "event_type": "index_creation_failed",
                        "db_name": db_name,
                        "table_name": table_name,
                        "column": column,
                        "error": str(col_error)
                    })

            return {
                "success": len(failed_indexes) == 0,
                "created_indexes": created_indexes,
                "failed_indexes": failed_indexes
            }

        except Exception as e:
            logger.error("Error creating indexes", extra={
                "event_type": "create_indexes_error",
                "db_name": db_name,
                "table_name": table_name,
                "error": str(e)
            })
            return {
                "success": False,
                "created_indexes": created_indexes,
                "failed_indexes": failed_indexes,
                "error": str(e)
            }