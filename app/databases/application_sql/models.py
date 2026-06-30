from typing import List, Optional
from sqlalchemy import ForeignKey, String, Integer, DateTime, Boolean, Float, NVARCHAR, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime, timezone
from urllib.parse import quote
from sqlalchemy.dialects.mssql import JSON
from app.appConfig import settings
from typing import Literal
from typing import Dict


class Base(DeclarativeBase):
    pass


SCHEMA = settings.sql_schema  


class USER(Base):
    __tablename__ = "users_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    chats: Mapped[List["CHAT"]] = relationship("CHAT", back_populates="user", cascade="all, delete-orphan")
    ml_models: Mapped[List["MLModels"]] = relationship("MLModels", back_populates="user", cascade="all, delete-orphan")
    datasets: Mapped[List["DATASET"]] = relationship("DATASET", back_populates="creator", cascade="all, delete-orphan")

    # Added relationship to usage logs
    model_usage_logs: Mapped[List["MLModelUsage"]] = relationship("MLModelUsage", back_populates="user", cascade="all, delete-orphan")
    
    # Added relationship to report builder
    user_reports: Mapped[List["Reports"]] = relationship("Reports", back_populates="user", cascade="all, delete-orphan")
    user_report_components: Mapped[List["ReportComponents"]] = relationship("ReportComponents", back_populates="user", cascade="all, delete-orphan")
    user_report_transactions: Mapped[List["ReportTransactions"]] = relationship("ReportTransactions", back_populates="user", cascade="all, delete-orphan")
    database_connections: Mapped[List["DatabaseConnection"]] = relationship("DatabaseConnection", back_populates="creator", cascade="all, delete-orphan")

class DATASET(Base):
    __tablename__ = "datasets_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    db_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    db_schema: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    connection_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.database_connections.id"), nullable=True)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(100), default="openai", nullable=True)
    ai_model_mappings: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    graph_type: Mapped[Optional[str]] = mapped_column(String(100), default="plotly_charts", nullable=True)
    ai_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    last_refresh_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    refresh_frequency_details: Mapped[Optional[str]] = mapped_column(String(100), default="0 0 * * *", nullable=True)
    tables_to_use: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    is_self_serve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"), nullable=True)

    chats: Mapped[List["CHAT"]] = relationship("CHAT", back_populates="datas", cascade="all, delete-orphan")
    transactions: Mapped[List["TRANSACTION"]] = relationship("TRANSACTION", back_populates="datas", cascade="all, delete-orphan")
    ml_models: Mapped[List["MLModels"]] = relationship("MLModels", back_populates="datas", cascade="all, delete-orphan")
    custom_dashboard: Mapped[List["CustomDashboards"]] = relationship("CustomDashboards", back_populates="datas", cascade="all, delete-orphan")
    data_reports: Mapped[List["Reports"]] = relationship("Reports", back_populates="data", cascade="all, delete-orphan")
    db_connections: Mapped["DatabaseConnection"] = relationship("DatabaseConnection", back_populates="datasets")
    creator: Mapped["USER"] = relationship("USER", back_populates="datasets")


class CHAT(Base):
    __tablename__ = "chats_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=False)
    db_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.datasets_new.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"), nullable=False)
    genie_conversation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_report: Mapped[bool] = mapped_column(Boolean, nullable=True)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["USER"] = relationship("USER", back_populates="chats")
    datas: Mapped["DATASET"] = relationship("DATASET", back_populates="chats")
    transactions: Mapped[List["TRANSACTION"]] = relationship("TRANSACTION", back_populates="chat", cascade="all, delete-orphan")
    report_chats: Mapped[List["ReportChat"]] = relationship("ReportChat", back_populates="chat", cascade="all, delete-orphan")
    report_workflows: Mapped[List["ReportWorkflow"]] = relationship(
        "ReportWorkflow", back_populates="chat", cascade="all, delete-orphan"
     )

class QUERY(Base):
    __tablename__ = "queries_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_query: Mapped[str] = mapped_column(String(200), nullable=False)
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    transactions: Mapped[List["TRANSACTION"]] = relationship("TRANSACTION", back_populates="query", cascade="all, delete-orphan")


class SQL(Base):
    __tablename__ = "sqls_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sql_code: Mapped[str] = mapped_column(String(3000), nullable=False)

    # relationships
    transactions: Mapped[List["TRANSACTION"]] = relationship("TRANSACTION", back_populates="sql", cascade="all, delete-orphan")


class LLM_USAGE(Base):
    __tablename__ = "api_usage_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.transactions_new.id"), nullable=True)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    cached_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    llm: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    transaction: Mapped["TRANSACTION"] = relationship("TRANSACTION", back_populates="llm_usage")


class TRANSACTION(Base):
    __tablename__ = "transactions_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    db_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.datasets_new.id"), nullable=False)
    query_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.queries_new.id"), nullable=False)
    sql_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.sqls_new.id"), nullable=True)
    chat_id: Mapped[Optional[int]] = mapped_column(String(100), ForeignKey(f"{SCHEMA}.chats_new.chat_id"), nullable=True)
    parent_transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.transactions_new.id"), nullable=True)
    validated_transaction: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    feedback: Mapped[Optional[str]] = mapped_column(String(4000), default=None, nullable=True)
    question_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    filters: Mapped[Optional[str]] = mapped_column(String(4000), default=None, nullable=True)
    approach: Mapped[Optional[str]] = mapped_column(String(4000), default=None, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(String(4000), default=None, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_query: Mapped[Optional[str]] = mapped_column(String(4000), default=None, nullable=True)

    #Added by Mayur
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=True)
    suggestions_attempted: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    graph_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    is_dml_attempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    graph_types: Mapped[str] = mapped_column(NVARCHAR(1000), nullable=True)
    intent_similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    suggestions_dml_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    is_graph_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suggestions_successful: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    query: Mapped["QUERY"] = relationship("QUERY", back_populates="transactions")
    datas: Mapped["DATASET"] = relationship("DATASET", back_populates="transactions")
    sql: Mapped["SQL"] = relationship("SQL", back_populates="transactions")
    chat: Mapped[Optional["CHAT"]] = relationship("CHAT", back_populates="transactions")
    llm_usage: Mapped[List["LLM_USAGE"]] = relationship("LLM_USAGE", back_populates="transaction", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "db_id": self.db_id,
            "query_id": self.query_id,
            "sql_id": self.sql_id,
            "chat_id": self.chat_id,
            "parent_transaction_id": self.parent_transaction_id,
            "validated_transaction": self.validated_transaction,
            "comments": self.comments,
            "feedback": self.feedback if self.feedback else None,
            "question_type": self.question_type,
            "filters": self.filters,
            "approach": self.approach,
            "raw_response": self.raw_response,
            "is_deleted": self.is_deleted,
        }


class CustomDashboards(Base):
    __tablename__ = "customDashboards_new"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    db_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.datasets_new.id"), nullable=False)
    sequence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    sql_code: Mapped[str] = mapped_column(String(4000), nullable=False)
    approach: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    graph_type: Mapped[str] = mapped_column(String(100), nullable=False)
    graph_label: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    datas: Mapped["DATASET"] = relationship("DATASET", back_populates="custom_dashboard")


class MLModels(Base):
    __tablename__ = "mlmodels"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    db_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.datasets_new.id"), nullable=False)
    operation_by: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_column: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_type: Mapped[Literal["classification", "regression"]] = mapped_column(String(200), default="regression", nullable=False)
    model_details: Mapped[str] = mapped_column(String(4000), nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lineage: Mapped[str] = mapped_column(String(200), nullable=True)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    datas: Mapped["DATASET"] = relationship("DATASET", back_populates="ml_models")
    user: Mapped["USER"] = relationship("USER", back_populates="ml_models")
    # Added relationship to logs
    usage_logs: Mapped[List["MLModelUsage"]] = relationship("MLModelUsage", back_populates="model", cascade="all, delete-orphan")

class MLModelUsage(Base):
    __tablename__ = "model_prediction_logs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.mlmodels.id"), nullable=False)
    operation_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"), nullable=True)
    request_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    execution_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    model: Mapped["MLModels"] = relationship("MLModels", back_populates="usage_logs")
    user: Mapped["USER"] = relationship("USER", back_populates="model_usage_logs")


class Reports(Base):
    __tablename__ = "reports"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    db_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.datasets_new.id"), nullable=False)
    report_name: Mapped[str] = mapped_column(String(100), nullable=False)
    report_description: Mapped[str] = mapped_column(NVARCHAR(1000), nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["USER"] = relationship("USER", back_populates="user_reports")
    data: Mapped["DATASET"] = relationship("DATASET", back_populates="data_reports")
    report_components: Mapped[List["ReportComponents"]] = relationship(
        "ReportComponents", back_populates="report", cascade="all, delete-orphan"
    )
    report_workflows: Mapped[List["ReportWorkflow"]] = relationship(
        "ReportWorkflow", back_populates="reports", cascade="all, delete-orphan"
    )

class ReportComponents(Base):
    __tablename__ = "report_components"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.reports.id"), nullable=False)
    component_name: Mapped[str] = mapped_column(String(100), nullable=True)
    component_description: Mapped[str] = mapped_column(NVARCHAR(1000), nullable=True)
    component_type: Mapped[str] = mapped_column(NVARCHAR(20), nullable=True, default=None)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False
    )

    user: Mapped["USER"] = relationship("USER", back_populates="user_report_components")
    report: Mapped["Reports"] = relationship("Reports", back_populates="report_components")
    report_component_transactions = relationship(
        "ReportTransactions", back_populates="component", cascade="all, delete-orphan"
    )

class ReportTransactions(Base):
    __tablename__ = "report_transactions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.report_components.id"), nullable=False)

    component_state_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_final_state: Mapped[bool] = mapped_column(Boolean, default=False)

    query: Mapped[str] = mapped_column(String(1000), nullable=True)
    table_details: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    graph_details: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    insights_details: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)

    modified_by: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users_new.id"), nullable=False)
    modified_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False
    )

    component: Mapped["ReportComponents"] = relationship("ReportComponents", back_populates="report_component_transactions")
    user: Mapped["USER"] = relationship("USER", back_populates="user_report_transactions")


class ReportChat(Base):
    __tablename__ = "report_chats"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[Optional[int]] = mapped_column(String(100), ForeignKey(f"{SCHEMA}.chats_new.chat_id"), nullable=True)
    type: Mapped[str] = mapped_column(String(1000), nullable=True)
    intent: Mapped[str] = mapped_column(String(1000), nullable=True)
    intent_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    kpis: Mapped[str] = mapped_column(String(1000), nullable=True)
    kpis_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    metrics: Mapped[str] = mapped_column(String(1000), nullable=True)
    metrics_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    filters: Mapped[str] = mapped_column(String(1000), nullable=True)
    filters_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    time_grain: Mapped[str] = mapped_column(String(1000), nullable=True)
    time_grain_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    raw_response: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    user_prompted_back: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    step_at: Mapped[int] = mapped_column(Integer, default=False, nullable=True) # 0-Unclear intent,  1-intent identification, 2-Kpi and metrics, 3-Time and filters 4-Suggested Queries, 5-Report Generation 
    user_input: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    transaction_output: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True)
    
    chat: Mapped[Optional["CHAT"]] = relationship("CHAT", back_populates="report_chats")


class ReportWorkflow(Base):
    __tablename__ = "report_workflows"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[Optional[int]] = mapped_column(String(100), ForeignKey(f"{SCHEMA}.chats_new.chat_id"), nullable=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.reports.id"), nullable=False)
    query: Mapped[str] = mapped_column(String(1000), nullable=True)
    text_output: Mapped[str] = mapped_column(String(1000), nullable=True)
    options: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    state: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    intent: Mapped[str] = mapped_column(NVARCHAR(1000), nullable=True)
    kpis: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    structure: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    report: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    intent_messages: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    kpi_messages: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    additional_detail_messages: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    structure_messages: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    report_messages: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)
    initial_query: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    build_type: Mapped[str] = mapped_column(NVARCHAR(100), nullable=True)
    completed_steps: Mapped[str] = mapped_column(NVARCHAR(4000), nullable=True)
    additional_details: Mapped[str] = mapped_column(NVARCHAR(length=None), nullable=True)

    chat: Mapped[Optional["CHAT"]] = relationship("CHAT", back_populates="report_workflows")
    reports: Mapped[Optional["Reports"]] = relationship("Reports", back_populates="report_workflows")


class DatabaseConnection(Base):
    __tablename__ = "database_connections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(String(100), nullable=True)
    username: Mapped[str] = mapped_column(NVARCHAR(100), nullable=True)
    password: Mapped[str] = mapped_column(NVARCHAR(100), nullable=True)
    host: Mapped[str] = mapped_column(NVARCHAR(100), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=True)
    db: Mapped[str] = mapped_column(NVARCHAR(100), nullable=True)
    dialect: Mapped[str] = mapped_column(NVARCHAR(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.users_new.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)

    creator: Mapped[Optional["USER"]] = relationship("USER", back_populates="database_connections")
    datasets: Mapped["DATASET"] = relationship("DATASET", back_populates="db_connections")


# def setup_internal_data():
#     """
#     Setup Internal SQL Database
#     :return: None
#     """

#     host = "172.31.34.92"
#     port = "1433"
#     username = "SURAJ_THULKAR"
#     password = "eClrxST#1234"
#     db = "IOD_TRANSACTIONS"

#     engine = create_engine(
#         f"mssql+pyodbc://{username}:{password}@{host}:{port}/{db}?driver=ODBC+Driver+17+for+SQL+Server"
#     )
#     session = Session(engine)
#     Base.metadata.create_all(engine)
#     print(Base.metadata.tables.keys())

# if __name__ == "__main__":
#     setup_internal_data()

