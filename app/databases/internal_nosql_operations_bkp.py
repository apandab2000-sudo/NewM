from typing import Optional
from app.databases.nosql_schema import Transaction, Plotly_Graph, Suggestion, Insights
from app.core.helper import bson_to_json_safe
from typing import List
from app.logger import get_logger

logger = get_logger()

class NOSQLHelper:

    @staticmethod
    async def record_transaction(
        transaction_id: int, 
        table, approach: str, 
        graphs: List[Plotly_Graph], 
        suggetsions: List[Suggestion],
        inights: Insights
    ):
        existing = await Transaction.find_one(
            Transaction.transaction_id == transaction_id
        )
        if existing:
            return False
        t = Transaction(
            transaction_id=transaction_id, 
            table=table, 
            approach=approach,
            graphs=graphs,
            suggestions=suggetsions,
            insights=inights
        )
        resp = await t.insert()
        return resp
    
    async def record_transactions_bulk(self, transactions_data: List[dict]):
        try:
            # Create Transaction objects
            new_transactions = [
                Transaction(**data) 
                for data in transactions_data
            ]
            
            # Bulk insert using insert_many
            result = await Transaction.insert_many(new_transactions)
            return True
            
        except Exception as e:
            logger.warning(f"NOSQL data not inserted properly - {repr(e)}")
            return False


    @staticmethod
    async def record_table(transaction_id: int, table, approach: str):
        # upsert to avoid duplicates if same transaction_id
        existing = await Transaction.find_one(
            Transaction.transaction_id == transaction_id
        )
        if existing:
            await existing.set(
                {Transaction.table: table, Transaction.approach: approach}
            )
            return existing
        t = Transaction(transaction_id=transaction_id, table=table, approach=approach)
        resp = await t.insert()
        return resp

    @staticmethod
    async def get_table(transaction_id: int) -> list[dict] | None:
        doc = await Transaction.find_one(
            Transaction.transaction_id == transaction_id,
            fetch_links=False,
            projection_model=Transaction,
        )
        return bson_to_json_safe(doc.table) if doc else None  # type: ignore

    @staticmethod
    async def record_graph(transaction_id: int, graphs: list[Plotly_Graph]):
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        if not doc:
            doc = Transaction(transaction_id=transaction_id, graphs=graphs)
            return await doc.insert()
        await doc.set({Transaction.graphs: graphs})
        return doc

    @staticmethod
    async def get_graph(transaction_id: int) -> list[Plotly_Graph] | None:
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        return doc.graphs if doc else None

    @staticmethod
    async def record_suggestions(transaction_id: int, suggestions: list[Suggestion]):
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        if not doc:
            doc = Transaction(transaction_id=transaction_id, suggestions=suggestions)
            return await doc.insert()
        await doc.set({Transaction.suggestions: suggestions})
        return doc

    @staticmethod
    async def record_insights(transaction_id: int, insights: Insights):
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        if not doc:
            doc = Transaction(transaction_id=transaction_id, insights=insights)
            return await doc.insert()
        await doc.set({Transaction.insights: insights})
        return doc

    @staticmethod
    async def get_transaction(transaction_id: int) -> Optional[Transaction]:
        return await Transaction.find_one(Transaction.transaction_id == transaction_id)

    @staticmethod
    async def get_insights_table(transaction_id: int):
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        return doc.insights.insights_table if doc and doc.insights else None

    @staticmethod
    async def get_insights(transaction_id: int) -> Optional[Insights]:
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        return doc.insights if doc else None

    @staticmethod
    async def get_suggestions(transaction_id: int) -> Optional[list[Suggestion]]:
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        return doc.suggestions if doc else None

    @staticmethod
    async def delete_transactions(transaction_id: int) -> Optional[int]:
        doc = await Transaction.find_one(Transaction.transaction_id == transaction_id)
        if doc:
            await doc.delete()
            return transaction_id
        return None
