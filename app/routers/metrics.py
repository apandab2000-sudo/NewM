from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY
from prometheus_client.multiprocess import MultiProcessCollector
import os


router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_registry():
    """Get the appropriate registry based on deployment mode."""
    # Check if running in multiprocess mode (multiple workers)
    if "prometheus_multiproc_dir" in os.environ:
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        return registry
    return REGISTRY


@router.get(
        "", 
        summary="Prometheus Metrics Endpoint", 
        description="Exposes application metrics in Prometheus format for monitoring and alerting.",
        response_description="Prometheus metrics data",
        responses={
            200: {"description": "Successful response with Prometheus metrics data"},
            500: {"description": "Internal server error"}
        },
        status_code=200
)
def metrics():
    registry = get_registry()
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Content-Encoding": "identity"} # Disable gzip compression for Prometheus scraping
    )