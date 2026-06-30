import asyncio
import json
from typing import List, Dict, Any, Optional
import pandas as pd
from app.appConfig import settings
from app.databases.vector.operations import VectorStore
from app.databases.vector.connections import VectorClient
from app.logger import get_logger
from .vector_config import VectorStoreConfig


logger = get_logger(__name__)


class VectorStoreSetupClient:
    def __init__(
        self,
        vector_client: VectorClient,
        db_name: str,
    ):
        self.vector_store = VectorStore(vector_client.vector_db)
        self.db_name = db_name
        self.config = VectorStoreConfig()
        
        # Validate configuration
        self.config.validate()

        # Collection settings
        self.collection_name = db_name
        
        # Cache for loaded metadata
        self._tables_metadata_json: Optional[list | dict] = None
        self._columns_metadata_json: Optional[list | dict] = None
        self._sample_queries_df: Optional[pd.DataFrame] = None


    async def init_collection(self) -> None:
        """
        Initialize the vector collection for the dataset.
        
        Raises:
            asyncio.TimeoutError: If initialization times out
            RetryableError: If vector DB connection fails
        """
        try:
            logger.info(
                f"Initializing vector collection: {self.collection_name}",
                extra={
                    "vector_dimension": self.config.vector_dimension,
                    "distance_metric": self.config.distance_metric,
                },
            )

            await asyncio.wait_for(
                self.vector_store.ensure_collection(
                    self.collection_name,
                    self.config.distance_metric,
                    self.config.vector_dimension,
                ),
                timeout=self.config.collection_init_timeout,
            )

            logger.info(f"Vector collection initialized: {self.collection_name}")

        except asyncio.TimeoutError:
            logger.error(
                f"Vector collection initialization timed out after "
                f"{self.config.collection_init_timeout}s",
                extra={"collection_name": self.collection_name},
            )
            raise

        except Exception as e:
            logger.error(
                f"Error initializing vector collection: {str(e)}",
                extra={"collection_name": self.collection_name, "error": str(e)},
            )
            raise 

    def _load_metadata(self) -> None:
        """
        Load metadata from CSV files (once).
        Caches results for subsequent calls.
        
        Raises:
            FileNotFoundError: If metadata files don't exist
            ValueError: If metadata files cannot be parsed
        """
        if self._tables_metadata_json is not None and self._columns_metadata_json is not None:
            logger.debug("Using cached metadata")
            return

        logger.info(f"Loading metadata for database: {self.db_name}")

        try:
            tables_path = self.config.get_tables_metadata_path(self.db_name)
            columns_path = self.config.get_columns_metadata_path(self.db_name)
            sample_queries_path = None
            
            try:
                sample_queries_path = self.config.get_sample_queries_path(self.db_name)
            except FileNotFoundError:
                logger.debug("Sample queries file not found (optional)")

            # Load all metadata in one operation
            with open(tables_path, "r") as f:
                tables_json = json.load(f)

            columns_json_list = []
            for file in columns_path.glob("*.json"):
                with open(file, "r") as f:
                    columns_json_list.append(json.load(f))

            sample_queries_df = pd.read_csv(sample_queries_path) if sample_queries_path else None

            self._tables_metadata_json = tables_json
            self._columns_metadata_json = columns_json_list
            self._sample_queries_df = sample_queries_df

            logger.info(
                f"Metadata loaded successfully: {len(tables_json)} tables, "
                f"{len(columns_json_list)} columns, "
                f"{len(sample_queries_df) if sample_queries_df is not None else 0} sample queries"
            )

        except (FileNotFoundError, ValueError) as e:
            logger.error(
                f"Error loading metadata: {str(e)}", extra={"db_name": self.db_name}
            )
            raise

    async def insert_table_vectors(self) -> int:
        """
        Insert table metadata vectors into collection.
        
        Returns:
            Number of vectors inserted
            
        Raises:
            asyncio.TimeoutError: If operation times out
            FileNotFoundError: If metadata files don't exist
        """
        logger.info("Starting table vector insertion")
        
        self._load_metadata()
        assert self._tables_metadata_json is not None

        # Prepare documents and metadata
        documents = []
        metadata = []

        for row in self._tables_metadata_json:
            table_name = row["name"]
            description = row.get("description", "")
            column_names = row.get("columns", [])

            doc = self._format_table_document(table_name, description, column_names)
            documents.append(doc)

            metadata.append(
                {
                    "table_name": table_name,
                    "description": description,
                    "columns": column_names,
                    "relationships": row.get("relationships", []),
                }
            )

        # Upsert with timeout and error handling
        try:
            inserted_count = await asyncio.wait_for(
                self._upsert_vectors(
                    documents, metadata, "table_metadata"
                ),
                timeout=self.config.insert_timeout,
            )
            logger.info(f"Inserted {inserted_count} table vectors")
            return inserted_count

        except asyncio.TimeoutError:
            logger.error("Table vector insertion timed out", extra={"db_name": self.db_name})
            raise
        except Exception as e:
            logger.error(
                f"Error during table vector insertion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise

    async def delete_table_vectors(self) -> None:
        """
        Delete all table metadata vectors from collection.
        
        Raises:
            asyncio.TimeoutError: If operation times out
            Exception: If deletion fails
        """
        logger.info("Starting deletion of table vectors")
        
        try:
            await asyncio.wait_for(
                self.vector_store.delete_vectors_by_context_type("table_metadata"),
                timeout=self.config.delete_timeout
            )
            logger.info("Table vectors deleted successfully")

        except asyncio.TimeoutError:
            logger.error("Table vector deletion timed out", extra={"db_name": self.db_name})
            raise
        except Exception as e:
            logger.error(
                f"Error during table vector deletion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise

    async def insert_column_vectors(self) -> int:
        """
        Insert column metadata vectors into collection.
        
        Returns:
            Number of vectors inserted
            
        Raises:
            asyncio.TimeoutError: If operation times out
            FileNotFoundError: If metadata files don't exist
        """
        logger.info("Starting column vector insertion")
        
        self._load_metadata()
        assert self._columns_metadata_json is not None

        documents = []
        metadata = []

        for entry in self._columns_metadata_json:
            for row in entry:
                column_name = row["name"]
                data_type = row.get("type", "")
                description = row.get("description", "")
                synonyms = ", ".join(row.get("synonyms")) if row.get("synonyms") else "",
                table_name = row.get("table_name", "")

                doc, meta = self._format_column_document(
                    column_name, description, synonyms,data_type, table_name, row
                )
                documents.append(doc)
                metadata.append(meta)

        # Upsert with timeout and error handling
        try:
            inserted_count = await asyncio.wait_for(
                self._upsert_vectors(
                    documents, metadata, "column_metadata"
                ),
                timeout=self.config.insert_timeout,
            )
            logger.info(f"Inserted {inserted_count} column vectors")
            return inserted_count

        except asyncio.TimeoutError:
            logger.error("Column vector insertion timed out", extra={"db_name": self.db_name})
            raise
        except Exception as e:
            logger.error(
                f"Error during column vector insertion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise

    async def insert_column_vectors_for_tables(self, tables_list: list[str]) -> int:
        """
        Insert column metadata vectors into collection.
        
        Returns:
            Number of vectors inserted
            
        Raises:
            asyncio.TimeoutError: If operation times out
            FileNotFoundError: If metadata files don't exist
        """
        logger.info("Starting column vector insertion for table(s): %s", tables_list)
        
        self._load_metadata()
        assert self._columns_metadata_json is not None

        documents = []
        metadata = []

        for entry in self._columns_metadata_json:
            for row in entry:
                column_name = row["name"]
                data_type = row.get("type", "")
                description = row.get("description", "")
                synonyms = ", ".join(row.get("synonyms")) if row.get("synonyms") else "",
                table_name = row.get("table_name", "")

                if table_name not in tables_list:
                    continue

                doc, meta = self._format_column_document(
                    column_name, description, synonyms,data_type, table_name, row
                )
                documents.append(doc)
                metadata.append(meta)

        # Upsert with timeout and error handling
        try:
            inserted_count = await asyncio.wait_for(
                self._upsert_vectors(
                    documents, metadata, "column_metadata"
                ),
                timeout=self.config.insert_timeout,
            )
            logger.info(f"Inserted {inserted_count} column vectors for table(s): {tables_list}")
            return inserted_count

        except asyncio.TimeoutError:
            logger.error("Column vector insertion timed out", extra={"db_name": self.db_name, "tables_list": tables_list})
            raise
        except Exception as e:
            logger.error(
                f"Error during column vector insertion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e), "tables_list": tables_list},
            )
            raise

    async def delete_column_vectors(self, table_name: str) -> None:
        """
        Delete all column metadata vectors from collection for a specific table.
        
        Raises:
            asyncio.TimeoutError: If operation times out
            Exception: If deletion fails
        """
        logger.info("Starting deletion of column vectors")
        
        try:
            await asyncio.wait_for(
                self.vector_store.delete_vectors_by_context_type(
                    context_type="column_metadata",
                    other_condition={"table_name": table_name}
                ),
                timeout=self.config.delete_timeout
            )
            logger.info("Column vectors deleted successfully")

        except asyncio.TimeoutError:
            logger.error("Column vector deletion timed out", extra={"db_name": self.db_name})
            raise
        except Exception as e:
            logger.error(
                f"Error during column vector deletion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise

    async def insert_column_value_vectors(self) -> int:
        """
        Insert column value vectors for categorical/string columns into collection.
        Uses batch processing to prevent memory overload for high-cardinality columns.
        
        Returns:
            Number of vectors inserted
            
        Raises:
            asyncio.TimeoutError: If operation times out
            FileNotFoundError: If metadata files don't exist
        """
        logger.info("Starting column value vector insertion")
        
        self._load_metadata()
        assert self._columns_metadata_json is not None

        # Collect all column values
        all_documents = []
        all_metadata = []

        for entry in self._columns_metadata_json:
            for row in entry:
                column_name = row["name"]
                data_type = row.get("type", "")
                table_name = row.get("table_name", "")

                # Only process categorical/string columns
                if data_type not in ("varchar", "nvarchar", "nchar", "object", "bit"):
                    continue

                unique_values_raw = row.get("unique_values")
                if not unique_values_raw:
                    continue

                for value_obj in unique_values_raw:    
                    value = value_obj.get("value")

                    if not value:
                        continue

                    if len(str(value)) < 5: # Skip very short values to reduce noise
                        continue
                    
                    if len(str(value)) > 50: # Skip very long values to prevent memory issues
                        continue 

                    if str(value).isdigit(): # Skip purely numeric values as they may not be meaningful for vectorization
                        continue

                    doc = f"{value}"
                    all_documents.append(doc)
                    all_metadata.append(
                        {"value": value, "column_name": column_name, "table_name": table_name}
                    )

        logger.info(f"Prepared {len(all_documents)} column values for insertion")

        try:
            inserted_count = await asyncio.wait_for(
                self._upsert_vectors(
                    all_documents, all_metadata, "column_unique_value"
                ),
                timeout=self.config.insert_timeout,
            )

            logger.info(f"Inserted {inserted_count} column value vectors")
            return inserted_count

        except asyncio.TimeoutError:
            logger.error(
                "Column value vector insertion timed out",
                extra={"db_name": self.db_name},
            )
            raise
        except Exception as e:
            logger.error(
                f"Error during column value vector insertion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise

    async def insert_sample_query_vectors(self) -> int:
        """
        Insert sample query vectors into collection.
        Optional operation if sample queries file exists.
        
        Returns:
            Number of vectors inserted
            
        Raises:
            asyncio.TimeoutError: If operation times out
            FileNotFoundError: If sample queries metadata file doesn't exist
        """
        logger.info("Starting sample query vector insertion")
        
        self._load_metadata()

        if self._sample_queries_df is None:
            logger.warning("Sample queries file not found, skipping")
            return 0

        documents = []
        metadata = []

        for _, row in self._sample_queries_df.iterrows():
            question = row.get("question", "")
            sql_query = row.get("sql_query", "")
            user_email = row.get("user_email_id", "")
            filters = row.get("filters", "")
            is_positive_example = row.get("is_positive_example", True)

            doc = (
                f"User Query: {question}\n"
                f"SQL Query: {sql_query}\n"
                f"Filters: {filters}"
            )
            documents.append(doc)

            metadata.append(
                {
                    "question": question,
                    "sql_query": sql_query,
                    "user_email_id": user_email,
                    "filters": filters,
                    "is_positive_example": is_positive_example
                }
            )

        try:
            inserted_count = await asyncio.wait_for(
                self._upsert_vectors(
                    documents, metadata, "sample_sql_query"
                ),
                timeout=self.config.insert_timeout,
            )
            logger.info(f"Inserted {inserted_count} sample query vectors")
            return inserted_count

        except asyncio.TimeoutError:
            logger.error(
                "Sample query vector insertion timed out",
                extra={"db_name": self.db_name},
            )
            raise
        except Exception as e:
            logger.error(
                f"Error during sample query vector insertion: {str(e)}",
                extra={"db_name": self.db_name, "error": str(e)},
            )
            raise


    async def _upsert_vectors(
        self,
        documents: List[str],
        metadata: List[Dict[str, Any]],
        context_type: str,
    ) -> int:
        """
        Upsert vectors into collection with retry logic.
        
        Args:
            documents: List of document strings
            metadata: List of metadata dicts
            context_type: Type of context (for categorization)
            
        Returns:
            Number of vectors inserted
            
        Raises:
            RetryableError: If upsert fails
        """
        try:
            logger.debug(f"Upserting vectors ({context_type}), total: {len(documents)}", extra={"context_type": context_type, "count": len(documents)})
            # insert in batches to prevent memory issues
            total_inserted = 0
            for i in range(0, len(documents), self.config.batch_size):
                batch_documents = documents[i:i + self.config.batch_size]
                batch_metadata = metadata[i:i + self.config.batch_size]
                status = await self.vector_store.upsert_data_points(
                    documents=batch_documents, metadata=batch_metadata, context_type=context_type
                )
                if not status:
                    logger.warning(f"Upsert returned failure status for batch starting at index {i} ({context_type})", extra={"context_type": context_type, "batch_start_index": i})
                inserted_count = len(batch_documents)
                logger.info(f"Inserted batch of {inserted_count} vectors ({context_type})", extra={"context_type": context_type, "count": inserted_count})
                total_inserted += inserted_count
            return total_inserted

        except Exception as e:
            logger.error(
                f"Error upserting vectors ({context_type}): {str(e)}",
                extra={"context_type": context_type, "count": len(documents)},
            )
            raise

    @staticmethod
    def _format_table_document(
        table_name: str, description: str, column_names: List[str]
    ) -> str:
        """
        Format table information as document string.
        
        Args:
            table_name: Table name
            description: Table description
            column_names: List of column names
            
        Returns:
            Formatted document string
        """
        columns_str = ", ".join(column_names) if column_names else "(no columns)"
        return f"Table: {table_name}\nDescription: {description}\nColumns: {columns_str}"

    @staticmethod
    def _format_column_document(
        column_name: str,
        description: str,
        synonyms: str,
        data_type: str,
        table_name: str,
        row: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        Format column information as document string and metadata.
        
        Args:
            column_name: Column name
            description: Column description
            data_type: Data type
            table_name: Table name
            row: Full row from metadata DataFrame
            
        Returns:
            Tuple of (document, metadata)
        """

        metadata_value_info = {}

        # Build value range info for numeric types
        if data_type not in ("varchar", "nvarchar", "nchar", "object", "bit"):
            min_value = row.get("min_value")
            max_value = row.get("max_value")
            value_range = (
                f"{min_value} - {max_value}"
                if min_value is not None and max_value is not None
                else "N/A"
            )
            doc = f"{column_name}\n{description}\n{data_type}\n{table_name}\n{value_range}"
            metadata_value_info = {"type": "range", "values": [min_value, max_value]}
        else:
            # For categorical columns, include sample values
            unique_values_raw = row.get("unique_values")
            unique_values = []
            if unique_values_raw:
                for v in unique_values_raw:
                    unique_values.append(v.get("value"))

            doc = (
                f"{column_name}\n{description}\n{', '.join(synonyms) if synonyms else ''}\n{data_type}\n{table_name}\n"
                f"{', '.join(str(v) for v in unique_values)}"
            )
            metadata_value_info = {"type": "unique_values", "values": unique_values}

        metadata = {
            "column_name": column_name,
            "description": description,
            "data_type": data_type,
            "table_name": table_name,
            "value_info": metadata_value_info
        }

        return doc, metadata

    async def delete_vectors_by_context_type(
        self, 
        context_type: str
    ) -> None:
        """
        Delete vectors from collection by context type.
        
        Args:
            context_type: Type of context to delete
            
        Raises:
            asyncio.TimeoutError: If operation times out
            Exception: If deletion fails
        """
        logger.info(f"Starting deletion of vectors with context type: {context_type}")
        
        try:
            await asyncio.wait_for(
                self.vector_store.delete_vectors_by_context_type(context_type),
                timeout=self.config.delete_timeout
            )
            logger.info(f"Vectors with context type '{context_type}' deleted successfully")

        except asyncio.TimeoutError:
            logger.error(
                f"Vector deletion timed out for context type: {context_type}",
                extra={"db_name": self.db_name, "context_type": context_type},
            )
            raise
        except Exception as e:
            logger.error(
                f"Error during vector deletion for context type '{context_type}': {str(e)}",
                extra={"db_name": self.db_name, "context_type": context_type, "error": str(e)},
            )
            raise
