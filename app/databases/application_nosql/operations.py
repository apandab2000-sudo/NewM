# from typing import Optional
# from .models import Transaction, Plotly_Graph, Suggestion, Insights
# from app.core.helper import bson_to_json_safe
# from typing import List
# from app.logger import get_logger

# logger = get_logger()

# class NOSQLHelper:
#     @staticmethod
#     async def record_transaction(
#         transaction_id: int, 
#         table, approach: str, 
#         graphs: List[Plotly_Graph], 
#         suggetsions: List[Suggestion],
#         inights: Insights
#     ):
#         existing = await Transaction.find_one(
#             Transaction.transaction_id == transaction_id
#         )
#         if existing:
#             return False
#         t = Transaction(
#             transaction_id=transaction_id, 
#             table=table, 
#             approach=approach,
#             graphs=graphs,
#             suggestions=suggetsions,
#             insights=inights
#         )
#         resp = await t.insert()
#         return resp
    
#     async def record_transactions_bulk(self, transactions_data: List[dict]):
#         try:
#             # Create Transaction objects
#             new_transactions = [
#                 Transaction(**data) 
#                 for data in transactions_data
#             ]
            
#             # Bulk insert using insert_many
#             result = await Transaction.insert_many(new_transactions)
#             return True
            
#         except Exception as e:
#             logger.warning(f"NOSQL data not inserted properly - {repr(e)}")
#             return False


#     @staticmethod
#     async def record_table(transaction_id: int, table, approach: str):
#         # upsert to avoid duplicates if same transaction_id
#         existing = await Transaction.find_one(
#             Transaction.transaction_id == transaction_id
#         )
#         if existing:
#             await existing.set(
#                 {Transaction.table: table, Transaction.approach: approach}
#             )
#             return existing
#         t = Transaction(transaction_id=transaction_id, table=table, approach=approach)
#         resp = await t.insert()
#         return resp

#     @staticmethod
#     async def get_table(transaction_id: int) -> list[dict] | None:
#         doc = await Transaction.find_one(
#             Transaction.transaction_id == transaction_id,
#             fetch_links=False,
#             projection_model=Transaction,
#         )
#         return bson_to_json_safe(doc.table) if doc else None  # type: ignore

#     @staticmethod
#     async def record_graph(transaction_id: int, graphs: list[Plotly_Graph]):
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         if not doc:
#             doc = Transaction(transaction_id=transaction_id, graphs=graphs)
#             return await doc.insert()
#         await doc.set({Transaction.graphs: graphs})
#         return doc

#     @staticmethod
#     async def get_graph(transaction_id: int) -> list[Plotly_Graph] | None:
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         return doc.graphs if doc else None

#     @staticmethod
#     async def record_suggestions(transaction_id: int, suggestions: list[Suggestion]):
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         if not doc:
#             doc = Transaction(transaction_id=transaction_id, suggestions=suggestions)
#             return await doc.insert()
#         await doc.set({Transaction.suggestions: suggestions})
#         return doc

#     @staticmethod
#     async def record_insights(transaction_id: int, insights: Insights):
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         if not doc:
#             doc = Transaction(transaction_id=transaction_id, insights=insights)
#             return await doc.insert()
#         await doc.set({Transaction.insights: insights})
#         return doc

#     @staticmethod
#     async def get_transaction(transaction_id: int) -> Optional[Transaction]:
#         return await Transaction.find_one(Transaction.transaction_id == transaction_id)

#     @staticmethod
#     async def get_insights_table(transaction_id: int):
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         return doc.insights.insights_table if doc and doc.insights else None

#     @staticmethod
#     async def get_insights(transaction_id: int) -> Optional[Insights]:
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         return doc.insights if doc else None

#     @staticmethod
#     async def get_suggestions(transaction_id: int) -> Optional[list[Suggestion]]:
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         return doc.suggestions if doc else None

#     @staticmethod
#     async def delete_transactions(transaction_id: int) -> Optional[int]:
#         doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
#         if doc:
#             await doc.delete()
#             return transaction_id
#         return None


from typing import Optional, List
from .models import Transaction, Plotly_Graph, Suggestion, Insights
from app.core.helper import bson_to_json_safe
from app.logger import get_logger

logger = get_logger(__name__)

# Constants
DEFAULT_FETCH_LINKS = False
MAX_BODY_SIZE_BYTES = 50_000
BULK_INSERT_BATCH_SIZE = 100

class NOSQLHelper:
    """Helper class for NoSQL database operations with proper error handling and logging"""

    @staticmethod
    async def record_transaction(
        transaction_id: int,
        table: List[dict],
        approach: str,
        graphs: List[Plotly_Graph],
        suggestions: List[Suggestion],
        insights: Insights,
    ) -> bool:
        """
        Record a new transaction with all related data.
        
        Args:
            transaction_id: Unique transaction identifier
            table: Data table as list of dictionaries
            approach: Approach used for processing
            graphs: List of Plotly graphs
            suggestions: List of suggestions
            insights: Insights object
            
        Returns:
            True if transaction was created, False if it already exists
            
        Raises:
            Exception: If database operation fails
        """
        try:
            existing = await Transaction.find_one(
                Transaction.transaction_id == transaction_id
            )
            if existing:
                logger.warning(
                    "Transaction already exists",
                    extra={"event_type": "duplicate_transaction", "transaction_id": transaction_id}
                )
                return False

            t = Transaction(
                transaction_id=transaction_id,
                table=table,
                approach=approach,
                graphs=graphs,
                suggestions=suggestions,
                insights=insights,
            )
            await t.insert()
            logger.info(
                "Transaction recorded successfully",
                extra={"event_type": "transaction_created", "transaction_id": transaction_id}
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to record transaction",
                extra={
                    "event_type": "transaction_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def record_transactions_bulk(transactions_data: List[dict]) -> tuple[int, int]:
        """
        Bulk insert multiple transactions.
        
        Args:
            transactions_data: List of transaction dictionaries
            
        Returns:
            Tuple of (inserted_count, failed_count)
            
        Raises:
            ValueError: If transactions_data is empty
        """
        if not transactions_data:
            raise ValueError("transactions_data cannot be empty")

        try:
            # Create Transaction objects with validation
            new_transactions = []
            for data in transactions_data:
                if "transaction_id" not in data:
                    logger.warning(
                        "Skipping transaction without transaction_id",
                        extra={"event_type": "invalid_transaction"}
                    )
                    continue
                try:
                    new_transactions.append(Transaction(**data))
                except Exception as e:
                    logger.warning(
                        "Failed to create transaction object",
                        extra={
                            "event_type": "transaction_validation_error",
                            "data": str(data),
                            "error": str(e),
                        }
                    )
                    continue

            if not new_transactions:
                logger.warning(
                    "No valid transactions to insert",
                    extra={"event_type": "no_valid_transactions"}
                )
                return 0, len(transactions_data)

            # Bulk insert
            result = await Transaction.insert_many(new_transactions)
            inserted_count = len(result)
            failed_count = len(transactions_data) - inserted_count

            logger.info(
                "Bulk transaction insert completed",
                extra={
                    "event_type": "bulk_insert_completed",
                    "inserted_count": inserted_count,
                    "failed_count": failed_count,
                }
            )
            return inserted_count, failed_count

        except Exception as e:
            logger.error(
                "Bulk insert operation failed",
                extra={
                    "event_type": "bulk_insert_error",
                    "total_records": len(transactions_data),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise



    @staticmethod
    async def record_table(transaction_id: int, table: List[dict], approach: str) -> Transaction:
        """
        Record or update table data for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            table: Data table as list of dictionaries
            approach: Approach used
            
        Returns:
            Updated or created Transaction object
            
        Raises:
            Exception: If database operation fails
        """
        try:
            existing = await Transaction.find_one(
                Transaction.transaction_id == transaction_id
            )
            if existing:
                await existing.set({Transaction.table: table, Transaction.approach: approach})
                logger.info(
                    "Transaction table updated",
                    extra={
                        "event_type": "transaction_table_updated",
                        "transaction_id": transaction_id,
                    }
                )
                return existing

            t = Transaction(transaction_id=transaction_id, table=table, approach=approach)
            await t.insert()
            logger.info(
                "Transaction table recorded",
                extra={
                    "event_type": "transaction_table_created",
                    "transaction_id": transaction_id,
                }
            )
            return t
        except Exception as e:
            logger.error(
                "Failed to record table",
                extra={
                    "event_type": "record_table_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_table(transaction_id: int) -> list[dict] | None:
        """
        Retrieve table data for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            Table data as list of dictionaries or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(
                Transaction.transaction_id == transaction_id,
                fetch_links=DEFAULT_FETCH_LINKS,
                projection_model=Transaction,
            )
            if not doc:
                logger.debug(
                    "Transaction not found",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return None
            return bson_to_json_safe(doc.table)
        except Exception as e:
            logger.error(
                "Failed to get table",
                extra={
                    "event_type": "get_table_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def record_graph(transaction_id: int, graphs: List[Plotly_Graph]) -> Transaction:
        """
        Record or update graphs for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            graphs: List of Plotly graphs
            
        Returns:
            Updated or created Transaction object
            
        Raises:
            Exception: If database operation fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                doc = Transaction(transaction_id=transaction_id, graphs=graphs)
                await doc.insert()
                logger.info(
                    "Graphs recorded for new transaction",
                    extra={
                        "event_type": "graphs_created",
                        "transaction_id": transaction_id,
                        "graph_count": len(graphs),
                    }
                )
                return doc
            await doc.set({Transaction.graphs: graphs})
            logger.info(
                "Graphs updated",
                extra={
                    "event_type": "graphs_updated",
                    "transaction_id": transaction_id,
                    "graph_count": len(graphs),
                }
            )
            return doc
        except Exception as e:
            logger.error(
                "Failed to record graphs",
                extra={
                    "event_type": "record_graph_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_graph(transaction_id: int) -> list[Plotly_Graph] | None:
        """
        Retrieve graphs for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            List of Plotly graphs or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                logger.debug(
                    "Transaction not found for graph retrieval",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return None
            return doc.graphs
        except Exception as e:
            logger.error(
                "Failed to get graphs",
                extra={
                    "event_type": "get_graph_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def record_suggestions(transaction_id: int, suggestions: List[Suggestion]) -> Transaction:
        """
        Record or update suggestions for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            suggestions: List of suggestions
            
        Returns:
            Updated or created Transaction object
            
        Raises:
            Exception: If database operation fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                doc = Transaction(transaction_id=transaction_id, suggestions=suggestions)
                await doc.insert()
                logger.info(
                    "Suggestions recorded for new transaction",
                    extra={
                        "event_type": "suggestions_created",
                        "transaction_id": transaction_id,
                        "suggestion_count": len(suggestions),
                    }
                )
                return doc
            await doc.set({Transaction.suggestions: suggestions})
            logger.info(
                "Suggestions updated",
                extra={
                    "event_type": "suggestions_updated",
                    "transaction_id": transaction_id,
                    "suggestion_count": len(suggestions),
                }
            )
            return doc
        except Exception as e:
            logger.error(
                "Failed to record suggestions",
                extra={
                    "event_type": "record_suggestions_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def record_insights(transaction_id: int, insights: Insights) -> Transaction:
        """
        Record or update insights for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            insights: Insights object
            
        Returns:
            Updated or created Transaction object
            
        Raises:
            Exception: If database operation fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                doc = Transaction(transaction_id=transaction_id, insights=insights)
                await doc.insert()
                logger.info(
                    "Insights recorded for new transaction",
                    extra={
                        "event_type": "insights_created",
                        "transaction_id": transaction_id,
                    }
                )
                return doc
            await doc.set({Transaction.insights: insights})
            logger.info(
                "Insights updated",
                extra={
                    "event_type": "insights_updated",
                    "transaction_id": transaction_id,
                }
            )
            return doc
        except Exception as e:
            logger.error(
                "Failed to record insights",
                extra={
                    "event_type": "record_insights_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_suggestions(transaction_id: int) -> list[Suggestion] | None:
        """
        Retrieve suggestions for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            List of suggestions or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                logger.debug(
                    "Transaction not found for suggestions retrieval",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return None
            return doc.suggestions
        except Exception as e:
            logger.error(
                "Failed to get suggestions",
                extra={
                    "event_type": "get_suggestions_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_transaction(transaction_id: int) -> Optional[Transaction]:
        """
        Retrieve complete transaction document.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            Transaction object or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                logger.debug(
                    "Transaction not found",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
            return doc
        except Exception as e:
            logger.error(
                "Failed to get transaction",
                extra={
                    "event_type": "get_transaction_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_insights_table(transaction_id: int) -> list[dict] | None:
        """
        Retrieve insights table data for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            Insights table data or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc or not doc.insights:
                logger.debug(
                    "Insights not found",
                    extra={
                        "event_type": "insights_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return None
            return doc.insights.insights_table
        except Exception as e:
            logger.error(
                "Failed to get insights table",
                extra={
                    "event_type": "get_insights_table_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def get_insights(transaction_id: int) -> Optional[Insights]:
        """
        Retrieve insights for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            Insights object or None if not found
            
        Raises:
            Exception: If database query fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                logger.debug(
                    "Transaction not found for insights retrieval",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return None
            return doc.insights
        except Exception as e:
            logger.error(
                "Failed to get insights",
                extra={
                    "event_type": "get_insights_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    @staticmethod
    async def delete_transactions(transaction_id: int) -> bool:
        """
        Delete a transaction by ID.
        
        Args:
            transaction_id: Transaction identifier
            
        Returns:
            True if transaction was deleted, False if not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
            if not doc:
                logger.warning(
                    "Transaction not found for deletion",
                    extra={
                        "event_type": "transaction_not_found",
                        "transaction_id": transaction_id,
                    }
                )
                return False
            await doc.delete()
            logger.info(
                "Transaction deleted",
                extra={
                    "event_type": "transaction_deleted",
                    "transaction_id": transaction_id,
                }
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to delete transaction",
                extra={
                    "event_type": "delete_transaction_error",
                    "transaction_id": transaction_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
