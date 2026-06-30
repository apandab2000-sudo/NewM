from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from app.logger import get_logger

logger = get_logger(__name__)


class VectorStoreConfig(BaseModel):
    """Configuration for vector store setup."""

    # Vector database settings
    vector_dimension: int = 384
    distance_metric: str = "cosine"

    # Batch processing settings
    batch_size: int = 500
    
    # Retry settings
    max_retries: int = 3
    retry_initial_delay: float = 1.0

    # Timeout settings (in seconds)
    collection_init_timeout: float = 60.0
    insert_timeout: float = 300.0
    delete_timeout: float = 60.0

    # File paths
    metadata_dir_pattern: str = "business_data/{db_name}"
    tables_metadata_file: str = "tables/tables.json"
    columns_metadata_path: str = "columns"
    sample_queries_file: str = "sample_queries.csv"

    def get_metadata_dir(self, db_name: str) -> Path:
        """
        Get metadata directory for database.
        
        Args:
            db_name: Database name
            
        Returns:
            Path to metadata directory
            
        Raises:
            ValueError: If directory doesn't exist
        """
        dir_path = Path(self.metadata_dir_pattern.format(db_name=db_name))
        if not dir_path.exists():
            raise ValueError(f"Metadata directory does not exist: {dir_path}")
        return dir_path

    def get_tables_metadata_path(self, db_name: str) -> Path:
        """Get path to tables metadata CSV file."""
        metadata_dir = self.get_metadata_dir(db_name)
        file_path = metadata_dir / self.tables_metadata_file
        if not file_path.exists():
            raise FileNotFoundError(f"Tables metadata file not found: {file_path}")
        return file_path

    def get_columns_metadata_path(self, db_name: str) -> Path:
        """Get path to columns metadata CSV file."""
        metadata_dir = self.get_metadata_dir(db_name)
        file_path = metadata_dir / self.columns_metadata_path
        if not file_path.exists():
            raise FileNotFoundError(f"Columns metadata file not found: {file_path}")
        return file_path

    def get_sample_queries_path(self, db_name: str) -> Path:
        """Get path to sample queries CSV file."""
        metadata_dir = self.get_metadata_dir(db_name)
        file_path = metadata_dir / self.sample_queries_file
        if not file_path.exists():
            raise FileNotFoundError(f"Sample queries file not found: {file_path}")
        return file_path

    def validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ValueError: If any configuration is invalid
        """
        if self.vector_dimension <= 0:
            raise ValueError("vector_dimension must be positive")
        if self.distance_metric not in ("cosine", "euclidean", "manhattan"):
            raise ValueError(
                f"distance_metric must be one of: cosine, euclidean, manhattan"
            )
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if self.collection_init_timeout <= 0:
            raise ValueError("collection_init_timeout must be positive")
        if self.insert_timeout <= 0:
            raise ValueError("insert_timeout must be positive")

