import asyncio
import collections
from fastapi import APIRouter, HTTPException, Depends
from matplotlib import collections
from app.logger import get_logger
from app.databases.dependencies import get_db_async, vector_pool_manager
from app.databases.client_sql.connections import ConnectionPoolFactory
from app.databases.application_sql.services.datasets import DatasetHelper
from app.databases.vector.operations import VectorStore
from app.core.setups.vectors.vectors import VectorStoreSetupClient
from app.appConfig import settings
from typing import Literal


router = APIRouter(prefix="/vectors", tags=["Vectors"])


logger = get_logger(__name__)


@router.get(
    "/collections",
    summary="List Vector Collections",
    description="Retrieve a list of all vector collections in the vector database",
    response_description="List of vector collections",
    responses={
        200: {"description": "Successful response with list of vector collections"},
        500: {"description": "Internal server error"}
    },
)
async def list_vector_collections():
    try:
        vector_client = await vector_pool_manager.get_pool()
        vector_store = VectorStore(vector_client.vector_db)
        collections = await vector_store.list_collections()
        if collections:
            collections = [coll.name for coll in collections.collections]
        return {"collections": collections}
    except Exception as e:
        logger.error(
            "Failed to list vector collections",
            extra={
                "event_type": "vector_collections_list_error",
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to list vector collections")


@router.get(
    "/collections/{db_name}",
    summary="Get Collection Details",
    description="Retrieve details of a specific vector collection by db_name",
    response_description="Vector collection details",
    responses={
        200: {"description": "Successful response with vector collection details"},
        404: {"description": "Vector collection not found"},
        500: {"description": "Internal server error"}
    },
)
async def get_collection_details(db_name: str | None, collection_name: str | None = None):
    if not db_name and not collection_name:
        raise HTTPException(status_code=400, detail="Either db_name or collection_name must be provided")

    if not collection_name:
        collection_name = f"{settings.app_env}_{db_name}_collection"
        
    try:
        vector_client = await vector_pool_manager.get_pool()
        vector_store = VectorStore(vector_client.vector_db)

        all_collections = await vector_store.list_collections()
        if all_collections:
            all_collections = [coll.name for coll in all_collections.collections]

        if not all_collections or collection_name not in all_collections:
            raise HTTPException(status_code=404, detail="Vector collection not found")

        collection_details = await vector_store.get_collection_details(collection_name)
        if not collection_details:
            raise HTTPException(status_code=404, detail="Vector collection not found")
        return collection_details
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get vector collection details",
            extra={
                "event_type": "vector_collection_details_error",
                "collection_name": collection_name,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to get vector collection details")



@router.delete(
    "/collections/{db_name}",
    summary="Delete Vector Collection",
    description="Delete a specific vector collection by db_name",
    responses={
        200: {"description": "Vector collection deleted successfully"},
        404: {"description": "Vector collection not found"},
        500: {"description": "Internal server error"}
    },
    status_code=200
)
async def delete_vector_collection(db_name: str | None, collection_name: str | None = None):

    if not db_name and not collection_name:
        raise HTTPException(status_code=400, detail="Either db_name or collection_name must be provided")

    if not collection_name:
        # collection_name = f"{settings.app_env}_{db_name}_collection"
        collection_name = db_name
    
    try:
        vector_client = await vector_pool_manager.get_pool()
        vector_store = VectorStore(vector_client.vector_db)

        all_collections = await vector_store.list_collections()
        if all_collections:
            all_collections = [coll.name for coll in all_collections.collections]

        if not all_collections or collection_name not in all_collections:
            raise HTTPException(status_code=404, detail="Vector collection not found")

        await vector_store.delete_collection(collection_name)
        return {"message": "Vector collection deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete vector collection",
            extra={
                "event_type": "vector_collection_delete_error",
                "collection_name": collection_name,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to delete vector collection")
    



@router.delete(
    "/collections/{db_name}/{context_type}",
    summary="Delete Vectors based on Context Type",
    description="Delete vectors from a specific vector collection by db_name and context_type",
    responses={
        200: {"description": "Vectors deleted successfully"},
        404: {"description": "Vector collection not found"},
        500: {"description": "Internal server error"}
    },
    status_code=200
)
async def delete_vectors_by_context_type(
    db_name: str | None, 
    collection_name: str | None = None, 
    context_type: Literal["table_metadata", "column_metadata", "column_unique_value", "sample_sql_query"] = "table_metadata"
):

    if not db_name and not collection_name:
        raise HTTPException(status_code=400, detail="Either db_name or collection_name must be provided")

    if not collection_name:
        # collection_name = f"{settings.app_env}_{db_name}_collection"
        collection_name = db_name
    
    try:
        vector_client = await vector_pool_manager.get_pool()
        vector_store = VectorStore(vector_client.vector_db)

        all_collections = await vector_store.list_collections()
        if all_collections:
            all_collections = [coll.name for coll in all_collections.collections]

        if not all_collections or collection_name not in all_collections:
            raise HTTPException(status_code=404, detail="Vector collection not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete vectors by context type",
            extra={
                "event_type": "delete_vectors_by_context_error",
                "collection_name": collection_name,
                "context_type": context_type,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to delete vectors by context type")
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=300)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )
        
    await vector_store.delete_vectors_by_context_type(context_type=context_type)
    return {"message": "Vectors deleted successfully"}



@router.post(
    "/collections/{db_name}/upsert-table-metadata",
    summary="Upsert Table Metadata to Vector Collection",
    description="Upsert metadata of tables to the corresponding vector collection for a dataset",
    responses={
        200: {"description": "Table metadata upserted successfully"},
        404: {"description": "Dataset or vector collection not found"},
        500: {"description": "Internal server error"}
    },
)
async def upsert_table_metadata_to_vector_collection(
    db_name: str,
    db_session=Depends(get_db_async),
    timeout: int = 300
):
    # Validate dataset exists
    dataset_helper = DatasetHelper(db_session)
    dataset = await dataset_helper.get_dataset_by_name(db_name)
    if not dataset:
        logger.error(
            f"Dataset not found: {db_name}",
            extra={"event_type": "vector_db_dataset_not_found", "db_name": db_name},
        )
        raise HTTPException(status_code=400, detail=f"Dataset '{db_name}' not found")

    # Establish vector database connection
    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {db_name}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": db_name,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=timeout)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    try:
        table_count = await asyncio.wait_for(
            asyncio.gather(
                vector_store.insert_table_vectors(),
            ),
            timeout=timeout,
        )

        result = {
            "success": True,
            "message": "Vector database setup completed successfully",
            "db_name": db_name,
            "statistics": {
                "table_vectors_inserted": table_count,
                "total_vectors_inserted": (
                    table_count
                ),
            },
        }

        logger.info(
            f"Vector database setup completed for: {db_name}",
            extra={
                "event_type": "vector_db_setup_success",
                "db_name": db_name,
                "statistics": result["statistics"],
            },
        )

        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Vector database setup timed out after {timeout}s for dataset: {db_name}",
            extra={
                "event_type": "vector_db_setup_timeout",
                "db_name": db_name,
                "timeout": timeout,
            },
        )
        raise HTTPException(
            status_code=408,
            detail=f"Vector database setup timed out after {timeout} seconds. Try again or increase timeout.",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during vector database setup for dataset: {db_name}: {str(e)}",
            extra={
                "event_type": "vector_db_setup_error",
                "db_name": db_name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail=f"Vector database setup failed: {str(e)}"
        )
    


@router.post(
    "/collections/{db_name}/upsert-column-metadata",
    summary="Upsert Column Metadata to Vector Collection",
    description="Upsert metadata of columns to the corresponding vector collection for a dataset",
    responses={
        200: {"description": "Column metadata upserted successfully"},
        404: {"description": "Dataset or vector collection not found"},
        500: {"description": "Internal server error"}
    },
)
async def upsert_column_metadata_to_vector_collection(
    db_name: str,
    db_session=Depends(get_db_async),
    timeout: int = 300
):
    # Validate dataset exists
    dataset_helper = DatasetHelper(db_session)
    dataset = await dataset_helper.get_dataset_by_name(db_name)
    if not dataset:
        logger.error(
            f"Dataset not found: {db_name}",
            extra={"event_type": "vector_db_dataset_not_found", "db_name": db_name},
        )
        raise HTTPException(status_code=400, detail=f"Dataset '{db_name}' not found")

    # Establish vector database connection
    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {db_name}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": db_name,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=timeout)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    try:
        column_count, column_value_count = await asyncio.wait_for(
            asyncio.gather(
                vector_store.insert_column_vectors(),
                vector_store.insert_column_value_vectors(),
            ),
            timeout=timeout,
        )

        result = {
            "success": True,
            "message": "Vector database setup completed successfully",
            "db_name": db_name,
            "statistics": {
                "column_vectors_inserted": column_count,
                "column_value_vectors_inserted": column_value_count,
                "total_vectors_inserted": (
                    column_count + column_value_count
                ),
            },
        }

        logger.info(
            f"Vector database setup completed for: {db_name}",
            extra={
                "event_type": "vector_db_setup_success",
                "db_name": db_name,
                "statistics": result["statistics"],
            },
        )

        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Vector database setup timed out after {timeout}s for dataset: {db_name}",
            extra={
                "event_type": "vector_db_setup_timeout",
                "db_name": db_name,
                "timeout": timeout,
            },
        )
        raise HTTPException(
            status_code=408,
            detail=f"Vector database setup timed out after {timeout} seconds. Try again or increase timeout.",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during vector database setup for dataset: {db_name}: {str(e)}",
            extra={
                "event_type": "vector_db_setup_error",
                "db_name": db_name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail=f"Vector database setup failed: {str(e)}"
        )



@router.post(
    "/collections/{db_name}/upsert-sample-queries",
    summary="Upsert Sample Queries to Vector Collection",
    description="Upsert sample queries to the corresponding vector collection for a dataset",
    responses={
        200: {"description": "Sample queries upserted successfully"},
        404: {"description": "Dataset or vector collection not found"},
        500: {"description": "Internal server error"}
    },
)
async def upsert_sample_queries_to_vector_collection(
    db_name: str,
    db_session=Depends(get_db_async),
    timeout: int = 300
):
    # Validate dataset exists
    dataset_helper = DatasetHelper(db_session)
    dataset = await dataset_helper.get_dataset_by_name(db_name)
    if not dataset:
        logger.error(
            f"Dataset not found: {db_name}",
            extra={"event_type": "vector_db_dataset_not_found", "db_name": db_name},
        )
        raise HTTPException(status_code=400, detail=f"Dataset '{db_name}' not found")

    # Establish vector database connection
    vector_client = await vector_pool_manager.get_pool()
    if not vector_client:
        logger.error(
            f"Failed to get vector database connection for dataset: {db_name}",
            extra={
                "event_type": "vector_db_connection_error",
                "db_name": db_name,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to establish vector database connection",
        )
    
    vector_store = VectorStoreSetupClient(vector_client, db_name)

    try:
        await asyncio.wait_for(vector_store.init_collection(), timeout=timeout)
    except Exception as e:
        logger.error(
            f"Error initializing vector collection for dataset: {db_name}",
            extra={
                "event_type": "vector_collection_init_error",
                "db_name": db_name,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize vector collection",
        )

    try:
        query_count = await asyncio.wait_for(
            asyncio.gather(
                vector_store.insert_sample_query_vectors()
            ),
            timeout=timeout,
        )

        result = {
            "success": True,
            "message": "Vector database setup completed successfully",
            "db_name": db_name,
            "statistics": {
                "query_vectors_inserted": query_count,
                "total_vectors_inserted": query_count
            },
        }

        logger.info(
            f"Vector database setup completed for: {db_name}",
            extra={
                "event_type": "vector_db_setup_success",
                "db_name": db_name,
                "statistics": result["statistics"],
            },
        )

        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Vector database setup timed out after {timeout}s for dataset: {db_name}",
            extra={
                "event_type": "vector_db_setup_timeout",
                "db_name": db_name,
                "timeout": timeout,
            },
        )
        raise HTTPException(
            status_code=408,
            detail=f"Vector database setup timed out after {timeout} seconds. Try again or increase timeout.",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during vector database setup for dataset: {db_name}: {str(e)}",
            extra={
                "event_type": "vector_db_setup_error",
                "db_name": db_name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail=f"Vector database setup failed: {str(e)}"
        )