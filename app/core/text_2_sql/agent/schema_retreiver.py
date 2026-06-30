from pathlib import Path
from pydantic import Field, BaseModel, ValidationError, field_validator
from typing import Dict, Optional, List, Literal, Any
from app.databases.vector.operations import VectorStore
from app.logger import get_logger
import asyncio
import pandas as pd
from .models import ExtractedEntities, TableCandidates, ColumnCandidates, ColumnValueCandidate
import json
import yaml


logger = get_logger(__name__)







class SchemaContext(BaseModel):
    tables: List[TableCandidates] = Field(default_factory=list)
    value_hints: List[ColumnValueCandidate] = Field(default_factory=list)         


    # def to

    # def to_prompt_string(self):
    #     lines = ["Database Schema Context:"]
    #     for table, cols in self.tables.items():
    #         col_parts = []
    #         for c in cols:
    #             tag = ""
    #             if c.is_primary_key:
    #                 tag += " [PK]"
    #             if c.is_foreign_key:
    #                 tag += " [FK]"
    #             dtype = c.data_type if c.data_type else ""
    #             col_parts.append(f"{c.column_name} ({dtype}){tag}")
    #         lines.append(f"- {table}: " + ", ".join(col_parts))

    #     if self.value_hints:
    #         lines.append("\nValue Mapping Hints:")
    #         for hint in self.value_hints:
    #             lines.append(hint.to_mapping_string())
            

class RetrieverConfig(BaseModel):
    # table retrieval parameters
    # top_k_tables: int = 5
    # table_score_threshold: float = 0.2
    # rrf_k1: float = 60.0

    # # column retrieval parameters
    # column_top_k_per_entity: int = 10
    # column_score_threshold: float = 0.2
    # min_columns_to_keep_table: int = 2

    # # value retrieval parameters
    # value_top_k: int = 5
    # value_score_threshold: float = 0.3
    

    table_top_k: int = 7
    table_score_threshold: float = 0.2
    rrf_k: int = 60                          # RRF constant (standard = 60)
 
    # Stage 2 — column retrieval
    column_top_k_per_entity: int = 10
    column_score_threshold: float = 0.2
    min_columns_to_keep_table: int = 2       # prune tables with 0 matching cols above threshold
 
    # Stage 3 — value matching
    value_top_k: int = 5
    value_score_threshold: float = 0.2
 
    # Concurrency
    max_concurrent_vector_calls: int = 20
 
    # FK/PK preservation
    always_keep_pk_fk: bool = True


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


# def has_time_reference(entities: ExtractedEntities) -> bool:
#     return bool(entities.time_references)

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


class SchemaRetriever:
    def __init__(
        self,
        dbname: str,
        vector_db,                          # VectorStore instance
        config: Optional[RetrieverConfig] = None,
    ):
        self.dbname = dbname
        self.vector_store = vector_db
        self.cfg = config or RetrieverConfig()
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
        self, entities: ExtractedEntities
    ) -> list[TableCandidates]:
        """
        Entity overlap keyword search: for each extracted entity/metric, compute token overlap matching with tables info
        """

        entity_list = list(set(entities.entities + entities.metrics + entities.entity_values))

        if not entity_list:
            # No entities extracted — fallback: keep all candidate tables
            logger.warning("No entities for keyword search; skipping.")
            return []

        tasks = []
        for entity in entity_list:
            self._query(
                user_query=entity,
                must_filters={
                    "context_type": "table_metadata"
                },
                n_results=self.cfg.table_top_k,
            )

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
                        score=0.3, # base score for relationship expansion
                        source="relationship",
                        payload=cand.payload,
                    )
                )

        return relationship_table_list

    async def get_table_candidates(
        self,
        user_query: str,
        filters: str,
        entities: ExtractedEntities,
    ) -> list[TableCandidates]:
        """
        Run vector + keyword searches in parallel, merge via RRF,
        then expand with relationship traversal. keeping all relationships
        """
     
        vector_results = await self._vector_table_search(user_query, filters)
        keyword_results = await self._keyword_table_search(entities)
 
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
 
        return list(all_candidates.values())

    async def _get_entity_mappings(self, entities: ExtractedEntities, tables_list: list[str]) -> list[ColumnValueCandidate]:
        entity_list = list(set(entities.entity_values))

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
    
    async def get_schema(
        self,
        user_query: str,
        filters: str,
        entities: ExtractedEntities
    ) -> SchemaContext:
        """
        Full pipeline:
        1. Table retrieval (vector + keyword + RRF + relationship expand)
        2. Column retrieval with FK/PK preservation + pruning
        3. Categorical value grounding
        Returns a SchemaContext ready to serialise into the LLM prompt.
        """
        # Stage 1
        table_candidates = await self.get_table_candidates(
            user_query, filters, entities
        )

        if not table_candidates:
            logger.warning("No table candidates found for query: %s", user_query)
            return SchemaContext(tables={}, value_hints=[], pruned_tables=[])

        logger.info(
            "Stage 1 — %d table candidates: %s",
            len(table_candidates),
            [c.table_name for c in table_candidates],
        )

        # Stage 2
        value_mappings = await self._get_entity_mappings(
            entities, [c.table_name for c in table_candidates]
        )
        logger.info("Stage 2 — %d value mappings", len(value_mappings))

        return SchemaContext(
            tables=table_candidates,
            value_hints=value_mappings
        )

    async def build_schema(
        self,
        user_query: str,
        filters: str,
        entities: ExtractedEntities
    ):
        schme_context = await self.get_schema(user_query, filters, entities)

        columns_metadata_path = Path(f"business_data/{self.dbname}/columns")
        
        table_json = []
        
        for table in schme_context.tables:
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

        lines = ["Value Mapping Hints:"]
        for h in schme_context.value_hints:
            hint = f"- '{h.entity_value}' can map to {h.table_name}.{h.column_name} = '{h.matched_value}' (score={h.score:.2f})"
            lines.append(hint)

        table_json = remove_null_objs(table_json)
        tables_yaml = yaml.safe_dump(table_json, sort_keys=False, default_flow_style=False, indent=4)

        final_schema = tables_yaml
        print(final_schema)        
        return final_schema, "\n\n" + "\n".join(lines)
            




# class SchemaRetrieverAdvanced:
#     def __init__(
#         self,
#         dbname: str,
#         vector_db,                          # VectorStore instance
#         config: Optional[RetrieverConfig] = None,
#     ):
#         self.db_schema = dbname
#         self.vector_store = vector_db
#         self.cfg = config or RetrieverConfig()
#         self._sem = asyncio.Semaphore(self.cfg.max_concurrent_vector_calls)
 
#     # ── Internal: rate-limited, retried vector call ──────────────────────
 
#     # @retry(
#     #     stop=stop_after_attempt(3),
#     #     wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
#     #     reraise=False,
#     # )
#     async def _query(self, **kwargs) -> list[dict]:
#         """Single vector store call — semaphore-limited and auto-retried."""
#         async with self._sem:
#             result = await self.vector_store._query_data(**kwargs)
#             return result if isinstance(result, list) else []
 
#     # ── Stage 1: Table retrieval with RRF ────────────────────────────────
 
#     async def _vector_table_search(self, query: str, filters: str) -> list[TableCandidates]:
#         """Bi-encoder semantic search over table-level vectors."""
#         combined = f"{query} {filters}".strip() if filters else query
#         raw = await self._query(
#             user_query=combined,
#             must_filters={"context_type": "table_metadata"},
#             n_results=self.cfg.table_top_k,
#         )
#         return [
#             TableCandidates(
#                 table_name=r["payload"]["table_name"],
#                 score=r["score"],
#                 source="vector",
#                 payload=r["payload"],
#             )
#             for r in raw
#             if r.get("payload", {}).get("table_name")
#             and r["score"] >= self.cfg.table_score_threshold
#         ]
 
#     async def _keyword_table_search(
#         self, entities: ExtractedEntities, all_table_names: list[str]
#     ) -> list[TableCandidates]:
#         """
#         Entity overlap keyword search: for each extracted entity/metric, compute token overlap matching with tables info
#         """

#         entity_list = list(set(entities.entities + entities.metrics + entities.entity_values))

#         if not entity_list:
#             # No entities extracted — fallback: keep all candidate tables
#             logger.warning("No entities for keyword search; skipping.")
#             return []

#         tasks = []
#         for entity in entity_list:
#             tasks.append(
#                 self._query(
#                     user_query=entity,
#                     must_filters={
#                         "context_type": "table_metadata"
#                     },
#                 n_results=self.cfg.table_top_k,
#             )

#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         scored = []
#         for res in results:
#             if isinstance(res, Exception):
#                 logger.warning("Keyword table search error for entity '%s': %s", entity, res)
#                 continue
#             for r in res:
#                 tbl = r.get("payload", {}).get("table_name")
#                 if tbl and r["score"] >= self.cfg.table_score_threshold:
#                     scored.append(
#                         TableCandidates(
#                             table_name=tbl,
#                             score=r["score"],
#                             source="keyword",
#                             payload=r["payload"],
#                         )
#                     )
#         return sorted(scored, key=lambda x: x.score, reverse=True)[: self.cfg.table_top_k]

#     async def _relationship_expand(
#         self, table_candidates: list[TableCandidates]
#     ) -> list[TableCandidates]:
#         """
#         For each candidate table, look up related tables via FK metadata.
#         Prevents missing JOIN partners that don't score highly on their own.
#         """
#         tasks = [
#             self._query(
#                 user_query=c.table_name,
#                 must_filters={
#                     "context_type": "table_metadata",
#                     "table_name": c.table_name,
#                 },
#                 n_results=1,
#             )
#             for c in table_candidates
#         ]
#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         extra: list[TableCandidates] = []
#         for res in results:
#             if isinstance(res, Exception):
#                 logger.warning("Relationship expand error: %s", res)
#                 continue
#             for r in res:
#                 tbl = r.get("payload", {}).get("table_name")
#                 if tbl:
#                     extra.append(
#                         TableCandidates(
#                             table_name=tbl,
#                             score=r["score"] * 0.8,  # slight discount for indirect hit
#                             source="relationship",
#                             payload=r["payload"],
#                         )
#                     )
#         return extra
 
#     async def get_table_candidates(
#         self,
#         user_query: str,
#         filters: str,
#         entities: ExtractedEntities,
#     ) -> list[TableCandidates]:
#         """
#         Run vector + keyword searches in parallel, merge via RRF,
#         then expand with relationship traversal.
#         """
     
#         vector_results = await self._vector_table_search(user_query, filters)
#         keyword_results = await self._keyword_table_search(entities)
 
#         merged = reciprocal_rank(
#             [vector_results, keyword_results],
#             k=self.cfg.rrf_k,
#         )
 
#         # Expand with related/joined tables
#         rel_extras = await self._relationship_expand(merged[: self.cfg.table_top_k])
#         all_candidates = {c.table_name: c for c in merged}
#         for extra in rel_extras:
#             if extra.table_name not in all_candidates:
#                 all_candidates[extra.table_name] = extra
 
#         return list(all_candidates.values())[: self.cfg.table_top_k]
 
#     # ── Stage 2: Column retrieval with pruning ───────────────────────────
 
#     async def get_column_candidates(
#         self,
#         table_candidates: list[TableCandidates],
#         entities: ExtractedEntities,
#     ) -> tuple[dict[str, list[ColumnCandidates]], list[str]]:
#         """
#         For each (entity, table) pair, fetch top-K columns in parallel.
#         Returns:
#           - dict[table_name → [ColumnCandidates]] for tables that pass pruning
#           - list of pruned table names
#         """
#         entity_list = list(
#             dict.fromkeys(
#                 entities.entities + entities.metrics + entities.entity_values
#             )
#         )
#         if not entity_list:
#             # No entities extracted — fallback: keep all candidate tables
#             logger.warning("No entities for column search; keeping all table candidates.")
#             return {c.table_name: [] for c in table_candidates}, []
 
#         tasks: list[tuple[str, str, Any]] = []
#         for entity in entity_list:
#             for cand in table_candidates:
#                 tasks.append(
#                     (entity, cand.table_name,
#                      self._query(
#                          user_query=entity,
#                          must_filters={
#                              "context_type": "column_metadata",
#                              "table_name": cand.table_name,
#                          },
#                          n_results=self.cfg.column_top_k_per_entity,
#                      ))
#                 )
 
#         raw_results = await asyncio.gather(
#             *[t[2] for t in tasks], return_exceptions=True
#         )
 
#         # Aggregate: keep max score per (table, column)
#         agg: dict[tuple[str, str], ColumnCandidates] = {}
#         for (entity, table_name, _), result in zip(tasks, raw_results):
#             if isinstance(result, Exception):
#                 logger.warning("Column query error for %s.%s: %s", table_name, entity, result)
#                 continue
#             for r in result:
#                 payload = r.get("payload", {})
#                 col = payload.get("column_name")
#                 if not col:
#                     continue
#                 key = (table_name, col)
#                 existing = agg.get(key)
#                 if existing is None or r["score"] > existing.score:
#                     agg[key] = ColumnCandidates(
#                         table_name=table_name,
#                         column_name=col,
#                         score=r["score"],
#                         data_type=payload.get("data_type", ""),
#                         is_pk=payload.get("is_pk", False), # Need to check this
#                         is_fk=payload.get("is_fk", False), # need to check this 
#                     )
 
#         # Apply date/time type filter if time references present
#         time_filter_active = has_time_reference(entities)
 
#         # Group by table and apply pruning
#         table_columns: dict[str, list[ColumnCandidates]] = {}
#         for (tbl, _), col_cand in agg.items():
#             table_columns.setdefault(tbl, []).append(col_cand)
 
#         kept: dict[str, list[ColumnCandidates]] = {}
#         pruned: list[str] = []
 
#         for tbl, cols in table_columns.items():
#             filtered_cols = []
#             for c in cols:
#                 # Always keep PK/FK columns regardless of score
#                 if self.cfg.always_keep_pk_fk and (c.is_pk or c.is_fk):
#                     filtered_cols.append(c)
#                     continue
#                 # Apply time filter: boost date columns if time references exist
#                 if time_filter_active and c.data_type.lower() in ("date", "datetime", "timestamp"):
#                     filtered_cols.append(c)
#                     continue
#                 if c.score >= self.cfg.column_score_threshold:
#                     filtered_cols.append(c)
 
#             if len(filtered_cols) >= self.cfg.min_columns_to_keep_table:
#                 # Sort: PK first, then FK, then by score desc
#                 filtered_cols.sort(
#                     key=lambda c: (not c.is_pk, not c.is_fk, -c.score)
#                 )
#                 kept[tbl] = filtered_cols
#             else:
#                 pruned.append(tbl)
#                 logger.debug("Pruned table '%s' — no columns above threshold.", tbl)
 
#         return kept, pruned
 
#     # ── Stage 3: Categorical value matching ──────────────────────────────
 
#     async def get_value_mappings(
#         self,
#         table_columns: dict[str, list[ColumnCandidates]],
#         entity_values: list[str],
#     ) -> list[ColumnValueCandidate]:
#         """
#         For each entity value, search categorical value vectors restricted
#         to only the shortlisted (table, column) pairs.
#         """
#         if not entity_values:
#             return []
 
#         # Build flat list of (table, column) pairs eligible for value lookup
#         col_pairs = [
#             (tbl, col.column_name)
#             for tbl, cols in table_columns.items()
#             for col in cols
#         ]
 
#         tasks: list[tuple[str, str, str, Any]] = []
#         for v_ent in entity_values:
#             for tbl, col in col_pairs:
#                 tasks.append(
#                     (v_ent, tbl, col,
#                      self._query(
#                          user_query=v_ent,
#                          must_filters={
#                              "context_type": "column_unique_value",
#                              "table_name": tbl,
#                             #  "column_name": col,
#                          },
#                          n_results=self.cfg.value_top_k,
#                          score_threshold=self.cfg.value_score_threshold,
#                      ))
#                 )
 
#         raw_results = await asyncio.gather(
#             *[t[3] for t in tasks], return_exceptions=True
#         )
 
#         mappings: list[ColumnValueCandidate] = []
#         for (v_ent, tbl, col, _), result in zip(tasks, raw_results):
#             if isinstance(result, Exception):
#                 logger.warning("Value query error for %s.%s = '%s': %s", tbl, col, v_ent, result)
#                 continue
#             for r in result:
#                 matched = r.get("payload", {}).get("value")
#                 if matched:
#                     mappings.append(
#                         ColumnValueCandidate(
#                             entity_value=v_ent,
#                             table_name=tbl,
#                             column_name=col,
#                             matched_value=matched,
#                             score=r["score"],
#                         )
#                     )
 
#         # Deduplicate: keep best match per (entity_value, table, column)
#         best: dict[tuple[str, str, str], ColumnValueCandidate] = {}
#         for m in mappings:
#             key = (m.entity_value, m.table_name, m.column_name)
#             if key not in best or m.score > best[key].score:
#                 best[key] = m
 
#         return sorted(best.values(), key=lambda x: x.score, reverse=True)


#     async def get_schema(
#         self,
#         user_query: str,
#         filters: str,
#         entities: ExtractedEntities,
#         all_table_names: Optional[list[str]] = None,
#     ) -> SchemaContext:
#         """
#         Full pipeline:
#           1. Table retrieval (vector + keyword + RRF + relationship expand)
#           2. Column retrieval with FK/PK preservation + pruning
#           3. Categorical value grounding
#         Returns a SchemaContext ready to serialise into the LLM prompt.
#         """
#         all_table_names = all_table_names or []
 
#         # Stage 1
#         table_candidates = await self.get_table_candidates(
#             user_query, filters, entities, all_table_names
#         )
#         if not table_candidates:
#             logger.warning("No table candidates found for query: %s", user_query)
#             return SchemaContext(tables={}, value_hints=[], pruned_tables=[])
 
#         logger.info(
#             "Stage 1 — %d table candidates: %s",
#             len(table_candidates),
#             [c.table_name for c in table_candidates],
#         )
 
#         # Stage 2
#         table_columns, pruned_tables = await self.get_column_candidates(
#             table_candidates, entities
#         )
#         logger.info(
#             "Stage 2 — kept %d tables, pruned %d: %s",
#             len(table_columns),
#             len(pruned_tables),
#             pruned_tables,
#         )
 
#         # Stage 3
#         value_mappings = await self.get_value_mappings(
#             table_columns, entities.entity_values
#         )
#         logger.info("Stage 3 — %d value mappings", len(value_mappings))
 
#         return SchemaContext(
#             tables=table_columns,
#             value_hints=value_mappings,
#             pruned_tables=pruned_tables,
#         )








# class SchemaRetriever:
#     def __init__(self, dbname, vector_db: VectorStore):
#         self.dbname = dbname
#         self.vector_store = vector_db

#         self.cfg = RetrieverConfig()


#     async def _query(self, **kwargs) -> list[dict]:
#         """Single vector store call — semaphore-limited and auto-retried."""
#         async with self._sem:
#             result = await self.vector_store._query_data(**kwargs)
#             return result if isinstance(result, list) else []
        

#     async def _vector_table_search(self, user_query: str, filters: str) -> list[TableCandidates]:
#         combined = f"{user_query} {filters}".strip() if filters else user_query
        
#         raw = await self._query(
#             user_query=combined,
#             must_filters={"context_type": "table_metadata"},
#             n_results=self.cfg.top_k_tables,
#         )

#         output = []

#         for item in raw:
#             if 'table_name' in item['payload'] and item["score"] >= self.cfg.table_score_threshold:
#                 tc = TableCandidates(
#                     table_name = item['payload']["table_name"],
#                     score = item['score'],
#                     source = "vector_search",
#                     columns = item['payload'].get("columns", []),
#                     relationships=item['payload'].get("relationships", [])
#             )
#             output.append(tc)
#         return output

#     async def _keyword_table_search(
#         self, user_query: str, entities: ExtractedEntities, all_table_names: list[str]
#     ) -> list[TableCandidates]:
#         """
#         Token overlap between extracted entity tokens and table name tokens.
#         No extra vector call needed — runs purely on the known table list.
#         """
#         query_tokens = set(
#             token.lower()
#             for term in (entities.entities + entities.metrics)
#             for token in term.replace("_", " ").split()
#         )
#         if not query_tokens:
#             return []
 
#         scored = []
#         for tbl in all_table_names:
#             s = keyword_overlap_score(query_tokens, tbl)
#             if s > 0:
#                 scored.append(
#                     TableCandidates(table_name=tbl, score=s, source="keyword_match")
#                 )
#         return sorted(scored, key=lambda x: x.score, reverse=True)[: self.cfg.table_top_k]
    
#     async def _relationship_expand(self, table_candidates: list[TableCandidates]) -> list[TableCandidates]:
#         """
#         Expand initial table candidates with directly related tables from metadata.
#         Boost scores of related tables to surface them higher in final ranking.
#         """
#         tasks = []
#         for cand in table_candidates:
#             tasks.append(
#                 self._query(
#                     user_query=cand.table_name,
#                     must_filters={"context_type": "table_metadata", "table_name": cand.table_name},
#                     n_results=1
#                 )
#             )

#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         extra = []

#         for res in results:
#             if isinstance(res, Exception):
#                 logger.warning("Relationship expand error: %s", res)
#                 continue
#             for r in res:
#                 tbl = r.get("payload", {}).get("table_name")
                
#                 if tbl:
#                     extra.append(
#                         TableCandidates(
#                             table_name=tbl,
#                             score=r.get("score", 0) * 0.8,  
#                             source="relationship_expand",
#                             columns=r.get("payload", {}).get("columns", []),
#                         )
#                     )
#         return extra
    

#     async def get_table_candidates(self, user_query: str, filters: str, entities: ExtractedEntities, all_table_names: list[str]) -> list[TableCandidates]:
#         """
#         Run vector + keyword searches in parallel, merge via RRF,
#         then expand with relationship traversal.
#         """
         
#         vector_task = self._vector_table_search(user_query, filters)
#         keyword_task = self._keyword_table_search(user_query, entities, all_table_names)

#         vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)

#         merged = reciprocal_rank([vector_results, keyword_results], k1=self.cfg.rrf_k1)

#         relationship_expanded = await self._relationship_expand(merged)
#         all_candidates = {c.table_name: c for c in merged}

#         for rel in relationship_expanded:
#             if rel.table_name in all_candidates:
#                 existing = all_candidates[rel.table_name]
#                 existing.score = max(existing.score, rel.score)
#                 if rel.columns:
#                     existing.columns = list(set(existing.columns) | set(rel.columns))
#             else:
#                 all_candidates[rel.table_name] = rel


#         sorted_candidates = sorted(all_candidates.values(), key=lambda x: x.score, reverse=True)
#         return sorted_candidates[: self.cfg.top_k_tables]
    
#     async def get_column_candidates(self, table_candidates: list[TableCandidates], entities: ExtractedEntities) -> tuple[dict[str, list[ColumnCandidates]], list[str]]:
#         entity_list = list(
#             dict.fromkeys(
#                 entities.entities + entities.metrics + entities.entity_values
#             )
#         )
#         if not entity_list:
#             # No entities extracted — fallback: keep all candidate tables
#             logger.warning("No entities for column search; keeping all table candidates.")
#             return {c.table_name: [] for c in table_candidates}, []
 
#         tasks: list[tuple[str, str, Any]] = []
#         for entity in entity_list:
#             for cand in table_candidates:
#                 tasks.append(
#                     (entity, cand.table_name,
#                      self._query(
#                          user_query=entity,
#                          must_filters={
#                              "context_type": "column_metadata",
#                              "table_name": cand.table_name,
#                          },
#                          n_results=self.cfg.column_top_k_per_entity,
#                      ))
#                 )
 
#         raw_results = await asyncio.gather(
#             *[t[2] for t in tasks], return_exceptions=True
#         )
 
#         # Aggregate: keep max score per (table, column)
#         agg: dict[tuple[str, str], ColumnCandidates] = {}
#         for (entity, table_name, _), result in zip(tasks, raw_results):
#             if isinstance(result, Exception):
#                 logger.warning("Column query error for %s.%s: %s", table_name, entity, result)
#                 continue
#             for r in result:
#                 payload = r.get("payload", {})
#                 col = payload.get("column_name")
#                 if not col:
#                     continue
#                 key = (table_name, col)
#                 existing = agg.get(key)
#                 if existing is None or r["score"] > existing.score:
#                     agg[key] = ColumnCandidates(
#                         table_name=table_name,
#                         column_name=col,
#                         score=r["score"],
#                         data_type=payload.get("data_type", ""),
#                         is_pk=payload.get("is_pk", False),
#                         is_fk=payload.get("is_fk", False),
#                     )
 
#         # Apply date/time type filter if time references present
#         time_filter_active = has_time_reference(entities)
 
#         # Group by table and apply pruning
#         table_columns: dict[str, list[ColumnCandidates]] = {}
#         for (tbl, _), col_cand in agg.items():
#             table_columns.setdefault(tbl, []).append(col_cand)
 
#         kept: dict[str, list[ColumnCandidates]] = {}
#         pruned: list[str] = []
 
#         for tbl, cols in table_columns.items():
#             filtered_cols = []
#             for c in cols:
#                 # Always keep PK/FK columns regardless of score
#                 if self.cfg.always_keep_pk_fk and (c.is_pk or c.is_fk):
#                     filtered_cols.append(c)
#                     continue
#                 # Apply time filter: boost date columns if time references exist
#                 if time_filter_active and c.data_type.lower() in ("date", "datetime", "timestamp"):
#                     filtered_cols.append(c)
#                     continue
#                 if c.score >= self.cfg.column_score_threshold:
#                     filtered_cols.append(c)
 
#             if len(filtered_cols) >= self.cfg.min_columns_to_keep_table:
#                 # Sort: PK first, then FK, then by score desc
#                 filtered_cols.sort(
#                     key=lambda c: (not c.is_pk, not c.is_fk, -c.score)
#                 )
#                 kept[tbl] = filtered_cols
#             else:
#                 pruned.append(tbl)
#                 logger.debug("Pruned table '%s' — no columns above threshold.", tbl)
 
#         return kept, pruned        


# class SchemaRetriever:
#     def __init__(self, dbname, vector_db: VectorStore):
#         self.db_schema = dbname
#         self.vector_store = vector_db

#     def get_entity_list(self, entities: dict):
#         entity_list = []

#         for ent in entities.get("entities", []):
#             try:
#                 entity_list.append(ent)
#             except Exception as e:
#                 logger.warning(f"Error appending entity {ent}: {e}")

#         for metric in entities.get("metrics", []):
#             if metric not in entity_list:
#                 try:
#                     entity_list.append(metric)
#                 except Exception as e:
#                     logger.warning(f"Error appending metric {metric}: {e}")
        
#         for fil in entities.get("entity_values", []):
#             if fil not in entity_list:
#                 try:
#                     entity_list.append(fil)
#                 except Exception as e:
#                     logger.warning(f"Error appending filter {fil}: {e}")

#         return entity_list
    
#     def get_entity_value_lists(self, entities: dict) -> list:
#         entity_value_lists = []

#         for fil in entities.get("entity_values", []):
#             if fil not in entity_value_lists:
#                 try:
#                     entity_value_lists.append(fil)
#                 except Exception as e:
#                     logger.warning(f"Error appending filter {fil}: {e}")

#         return entity_value_lists
    
#     async def _trverse_tables_for_relaationships(self, table_candidates: list):
#         tasks = []
#         for table in table_candidates:
#             tasks.append(
#                 self.vector_store._query_data(
#                     user_query=table['payload']['table_name'],
#                     must_filters={"context_type": "table_metadata", "table_name": table['payload']['table_name']},
#                     n_results=1
#                 )
#             )
#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         return results
    
    
#     async def get_table_candidates(self, user_query: str, filters: str):
#         table_candidates = await self.vector_store._query_data(
#             user_query=user_query + " " + filters if filters else user_query,
#             must_filters={"context_type": "table_metadata"},
#             n_results=10
#         )
#         relationship_candidates = await self._trverse_tables_for_relaationships(table_candidates)
        
#         for rel in relationship_candidates:
#             table_candidates.extend(rel)
        
#         return table_candidates

    
#     async def get_column_candidates_per_table(self, table_list: dict, entity_list: list):
#         tasks = []
#         for entity in entity_list:
#             for table in table_list.keys():
#                 tasks.append(
#                     self.vector_store._query_data(
#                         user_query=entity,
#                         must_filters={"context_type": "column_metadata", "table_name": table},
#                         n_results=10)
#                 )
#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         return results
    

#     async def get_column_value_candidates(self, table_column_mappings: list, entity: str, threshold: float = 0.3):
#         tasks = []
#         for mapping in table_column_mappings:
#             tasks.append(
#                 self.vector_store._query_data(
#                         user_query=entity,
#                         must_filters={"context_type": "column_unique_value", "table_name": mapping['table_name'], "column_name": mapping['column_name']},
#                         n_results=5,
#                         score_threshold=threshold)
#                 )
#         results = await asyncio.gather(*tasks, return_exceptions=True)
#         return results

    
#     async def entity_mapping(self, user_query: str, filters: str, entities: dict): 

#         table_candidates = await self.get_table_candidates(user_query, filters)

#         table_results = {cand['payload']['table_name']: {"score": cand['score']} for cand in table_candidates if 'table_name' in cand['payload'] and cand['payload']['table_name'] is not None}

#         entity_list = self.get_entity_list(entities)
#         entity_value_list = self.get_entity_value_lists(entities)

#         column_candidates = await self.get_column_candidates_per_table(table_results, entity_list)

#         col_table_mappings = []
#         for col_result in column_candidates:
#             for mapping in col_result:
#                 col_table_mappings.append({
#                     "table_name": mapping['payload']['table_name'],
#                     "column_name": mapping['payload']['column_name'],
#                     "score": mapping['score']
#                 })

#         df = pd.DataFrame(col_table_mappings)
#         df = df.groupby(['table_name', 'column_name']).agg({'score': 'max'}).reset_index()

#         col_table_mappings = df.groupby('table_name')["column_name"].apply(list).reset_index().to_dict(orient='records')

#         col_value_mappings = []
#         for v_ent in entity_value_list:
#             res = await self.get_column_value_candidates(col_table_mappings, v_ent)
#             print(res)
#             for r in res:
#                 for rec in r:
#                     col_value_mappings.append(f"- '{v_ent}' best matches {rec['payload']['table_name']}.{rec['payload']['column_name']} = '{rec['payload']['value']}' (score={rec['score']:.2f})")

#         return {
#             # "tables_list": tables_list,
#             "tbl_col_mappings": col_table_mappings,
#             "column_value_mappings": col_value_mappings,
#             # "entities": entity_list,
#             # "entity_value_list": entity_value_list,
#             # "column_value_candidates": column_value_candidates
#         }
    
#     async def get_schema(self, user_query: str, filters: str, entities: dict):
#         mapping_results = await self.entity_mapping(user_query, filters, entities)
#         return mapping_results


