from pathlib import Path
from pydantic import Field, BaseModel, ValidationError, field_validator
from typing import Dict, Optional, List, Literal, Any
from app.databases.vector.operations import VectorStore
from app.logger import get_logger
import asyncio
import pandas as pd
from ..models import ExtractedEntities, TableCandidates, ColumnCandidates, ColumnValueCandidate
import json
import yaml


logger = get_logger(__name__)


class EntityRetreiverConfig(BaseModel):
    max_concurrent_vector_calls: int = 10
    value_top_k: int = 5
    value_score_threshold: float = 0.2

    
class EntityRetreiver:
    def __init__(self, dbname: str, vector_db: VectorStore, config: Optional[EntityRetreiverConfig] = None):
        self.dbname = dbname
        self.vector_store = vector_db
        self.cfg = config or EntityRetreiverConfig()
        self._sem = asyncio.Semaphore(self.cfg.max_concurrent_vector_calls)


    async def _query(self, **kwargs) -> list[dict]:
        """Single vector store call — semaphore-limited and auto-retried."""
        async with self._sem:
            result = await self.vector_store._query_data(**kwargs)
            return result if isinstance(result, list) else []

    async def get_entities(self, tables_list: list, entities: dict):
        
        entity_list = list(set(entities.get("entities", []) + entities.get("metrics", []) + entities.get("entity_values", [])))

        tasks = []
        for entity in entity_list:
            tasks.append({
                "entity": entity,
                "task": self._query(
                    user_query=entity,
                    must_filters={
                        "context_type": "column_unique_value",
                        "table_name": tables_list,
                    },
                    n_results=self.cfg.value_top_k,
                    score_threshold=self.cfg.value_score_threshold,
                )
            })
        results = await asyncio.gather(*[t["task"] for t in tasks], return_exceptions=True)
        
        mappings: list[ColumnValueCandidate] = []        
        for v_ent, result in zip(entity_list, results):
            if isinstance(result, Exception):
                logger.warning("Value query error for entity '%s': %s", v_ent, result)
                continue
            for r in result:
                matched = r.get("payload", {}).get("value")
                if matched:
                    mappings.append(
                        ColumnValueCandidate(
                            entity_value=v_ent,
                            table_name=r.get("payload", {}).get("table_name"),
                            column_name=r.get("payload", {}).get("column_name"),
                            matched_value=matched,
                            score=r["score"],
                        )
                    )
        # Deduplicate: keep best match per (entity_value, table, column)
        best: dict[tuple[str, str, str], ColumnValueCandidate] = {}
        for m in mappings:
            key = (m.entity_value, m.table_name, m.column_name)
            if key not in best or m.score > best[key].score:
                best[key] = m
        
        return sorted(best.values(), key=lambda x: x.score, reverse=True)

    def get_entity_hint_string(self, entity_mappings: list[ColumnValueCandidate]) -> str:
        if not entity_mappings:
            return "None"
        hint_str = "Entity-Value Mappings:\n"
        for m in entity_mappings:
            hint_str += f"- '{m.entity_value}' matches {m.table_name}.{m.column_name} = '{m.matched_value}' (score={m.score:.2f})\n"
        return hint_str