from .metrics import router as metrics_router
from .healthCheck import router as health_router
from .dashboards import router as dashboards_router 
from .chats import router as chats_router
from .tables import router as tables_router
from .graphs import router as graphs_router
from .drilldowns import router as drilldown_router
from .suggestions import router as suggestions_router
from .insights import router as insights_router
from .feedbacks import router as feedback_router
from .conversations import router as conversation_router
from .setups import router as setup_router
# from .whatIfAnalysis import router as whatif_router
# from .admin_dashboards import router as admin_dashboards_router
# from .report_builder import router as report_builder_router
# from .report_builder_chat import router as report_builder_chat_router
from .db_connections import router as db_connections_router
from .datasets import router as datasets_router
from .vectors import router as vectors_router
from .self_serve import router as self_serve_router