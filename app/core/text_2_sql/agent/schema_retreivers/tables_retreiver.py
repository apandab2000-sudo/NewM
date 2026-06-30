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


class TableRetreiverConfig(BaseModel):
    always_keep_pk_fk: bool = True
    max_concurrent_vector_calls: int = 10
    table_top_k: int = 10
    table_score_threshold: float = 0.1
    rrf_k: int = 60   


def reciprocal_rank(ranked_list: list, k: float = 60.0) -> list:
    """
    Merge N ranked lists via RRF.
    Score = sum(1 / (k + rank)) across all lists a table appears in.
    Higher is better; handles heterogeneous score scales naturally.
    """
     
    fused = {}
    best_candidates = {}

    for ranked in ranked_list:
        for rank, item in enumerate(ranked, start=1):
            fused[item.table_name] = fused.get(item.table_name, 0) + 1 / (rank + k)
            if item.table_name not in best_candidates or item.score > best_candidates[item.table_name].score:
                best_candidates[item.table_name] = item        

    merged = []
    for table_name, score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
        candidate = best_candidates[table_name]
        candidate.score = score
        merged.append(candidate)

    return merged


def keyword_overlap_score(query_tokens: set[str], table_name: str) -> float:
    """
    Normalised token overlap between query entities and table name tokens.
    Returns 0.0–1.0.
    """
    tbl_tokens = set(table_name.lower().replace("_", " ").split())
    if not tbl_tokens:
        return 0.0
    return len(query_tokens & tbl_tokens) / len(tbl_tokens)    


def remove_null_objs(obj: dict | list):
    """Recursively remove keys with null values from a dictionary or list.
        also remove row where is_primary_key == False
    Args:
        obj: The input dictionary or list to clean.
    Returns:
        A new dictionary or list with all null values removed.
    """

    if isinstance(obj, dict):
        return {k: remove_null_objs(v) for k, v in obj.items() if v is not None and not (k == "is_primary_key" and v == False)}
    elif isinstance(obj, list):
        return [remove_null_objs(item) for item in obj if item is not None]
    else:
        return obj


class TableSchemaRetreiver:
    def __init__(
        self,
        dbname: str,
        vector_db,                          # VectorStore instance
        config: Optional[dict] = None,
    ):
        self.dbname = dbname
        self.vector_store = vector_db
        self.cfg = config or TableRetreiverConfig()
        self._sem = asyncio.Semaphore(self.cfg.max_concurrent_vector_calls)


    async def _query(self, **kwargs) -> list[dict]:
        """Single vector store call — semaphore-limited and auto-retried."""
        async with self._sem:
            result = await self.vector_store._query_data(**kwargs)
            return result if isinstance(result, list) else []
        

    async def _vector_table_search(self, query: str, filters: str) -> list[TableCandidates]:
        """Bi-encoder semantic search over table-level vectors."""
        combined = f"{query} {filters}".strip() if filters else query
        raw = await self._query(
            user_query=combined,
            must_filters={"context_type": "table_metadata"},
            n_results=self.cfg.table_top_k,
        )
        return [
            TableCandidates(
                table_name=r["payload"]["table_name"],
                score=r["score"],
                source="vector",
                payload=r["payload"],
            )
            for r in raw
            if r.get("payload", {}).get("table_name")
            and r["score"] >= self.cfg.table_score_threshold
        ]
    

    async def _keyword_table_search(
        self, entities: dict
    ) -> list[TableCandidates]:
        """
        Entity overlap keyword search: for each extracted entity/metric, compute token overlap matching with tables info
        """

        entity_list = list(set(entities.get("entities", []) + entities.get("metrics", []) + entities.get("entity_values", [])))

        if not entity_list:
            logger.warning("No entities for keyword search; skipping.")
            return []

        tasks = []
        for entity in entity_list:
            tasks.append(self._query(
                user_query=entity,
                must_filters={
                    "context_type": "table_metadata"
                },
                n_results=self.cfg.table_top_k,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        scored = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning("Keyword table search error for entity '%s': %s", entity, res)
                continue
            for r in res:
                tbl = r.get("payload", {}).get("table_name")
                if tbl and r["score"] >= self.cfg.table_score_threshold:
                    scored.append(
                        TableCandidates(
                            table_name=tbl,
                            score=r["score"],
                            source="keyword",
                            payload=r["payload"],
                        )
                    )
        return sorted(scored, key=lambda x: x.score, reverse=True)[: self.cfg.table_top_k]
    

    async def _relationship_expand(
        self, table_candidates: list[TableCandidates]
    ) -> list[TableCandidates]:
        """
        For each candidate table, look up related tables via FK metadata.
        Prevents missing JOIN partners that don't score highly on their own.
        """

        relationship_table_list = []
        for cand in table_candidates:
            for c in cand.payload.get("relationships", []):
                relationship_table_list.append(
                    TableCandidates(
                        table_name=c["referenced_table"],
                        score=0.1, # base score for relationship expansion
                        source="relationship",
                        payload=cand.payload,
                    )
                )

        return relationship_table_list
    

    async def get_table_candidates(
        self,
        user_query: str,
        filters: str,
        entities: dict,
    ) -> list[TableCandidates]:
        """
        Run vector + keyword searches in parallel, merge via RRF,
        then expand with relationship traversal. keeping all relationships
        """
     
        vector_results = await self._vector_table_search(user_query, filters)

        for r in vector_results:
            print(f"Vector search candidate: {r.table_name} (score={r.score:.4f})")

        keyword_results = await self._keyword_table_search(entities)

        for r in keyword_results:
            print(f"Keyword search candidate: {r.table_name} (score={r.score:.4f})")
 
        merged = reciprocal_rank(
            [vector_results, keyword_results],
            k=self.cfg.rrf_k,
        )
 
        # Expand with related/joined tables
        rel_extras = await self._relationship_expand(merged[: self.cfg.table_top_k])
        all_candidates = {c.table_name: c for c in merged}
        for extra in rel_extras:
            if extra.table_name not in all_candidates:
                all_candidates[extra.table_name] = extra

        for r in all_candidates.values():
            print(f"Final candidate: {r.table_name} (score={r.score:.4f}, source={r.source})")
 
        return list(all_candidates.values())


    def build_schema(
        self,
        tabele_candidates: list[TableCandidates]
    ):
        columns_metadata_path = Path(f"business_data/{self.dbname}/columns")
        
        table_json = []
        
        for table in tabele_candidates:
            columns_metadata_file = columns_metadata_path / f"{table.table_name}.json"
            if columns_metadata_file.exists():
                ti = {
                    "Table": table.table_name.upper(),
                    "Description": table.payload.get("description", ""),
                }
                with open(columns_metadata_file, "r") as f:
                    columns_metadata= json.load(f)
                    
                    cols_info = []

                    for col in columns_metadata:

                        sample_values = [i["value"] for i in col.get("unique_values", [])][:3] if col.get("unique_values") else None
                        if not sample_values:
                            if col.get("min_value") is not None and col.get("max_value") is not None:
                                sample_values = [col.get("min_value"), col.get("max_value")]

                        cols_info.append({
                            "name": col.get("name").upper(),
                            "type": col.get("type"),
                            "synonyms": col.get("synonyms") if col.get("synonyms") else None,
                            "description": col.get("description") if col.get("description") else None,
                            "is_primary_key": col.get("is_primary_key") if col.get("is_primary_key") is not None else None,
                            "sample_values": sample_values 
                        })

                    ti["Columns"] = cols_info
                    ti["Relationships"] = table.payload.get("description")
                    
                    table_json.append(ti)
            else:
                logger.warning("Columns metadata file not found for table '%s': %s", table.table_name, columns_metadata_file)

        return remove_null_objs(table_json)