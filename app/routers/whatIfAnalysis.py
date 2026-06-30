from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from app.logger import get_logger
from app.appConfig import settings
import os
import json 
from pathlib import Path
from typing import List, Optional
from app.models import (
    ResetChat, 
    UserName, 
    TargetVariable, 
    TrainModelRequest, 
    TrainModelStatus, 
    FinalizeModel, 
    ModelRequestLineage, 
    PredictRequest,
    PredictionFeatureRequest,
    GetModelsRequest, ModelUsageRequest
)
from sqlalchemy.ext.asyncio import AsyncSession
# from app.databases.connections import (
#     client_connection_pool,
#     get_db_async,
#     get_redis_client,
# )
from app.databases.dependencies import (
    get_db_async,
    # get_vector_client,
    # get_nosql_client,
    get_pool,
    get_caching_client
)
from app.databases.application_sql.operations import InternalSQLHelper
import uuid
import yaml
from typing import Dict, Any
from app.core.caching import cache_data, get_cached_data
# from app.core.table_from_sql import get_table_from_sql
from app.databases.client_sql.operations import (
    get_table_from_sql, 
    get_table_and_status_and_columns
)
import pandas as pd
# from app.core.helper import make_json_safe, bson_to_json_safe, correct_columns_name, get_table_and_status_and_columns
from app.core.helper import make_json_safe, bson_to_json_safe, correct_columns_name
import asyncio
from datetime import datetime
from sklearn.model_selection import train_test_split
from flaml import AutoML
import joblib
from pydantic import ConfigDict 
import shutil
import io
import base64
import numpy as np
from app.core.graphs.plotly.plotly_graphs_2d import get_2d_line_chart, get_2d_bar_chart
import plotly.graph_objects as go


import lime
import lime.lime_tabular
import shap
import matplotlib
import matplotlib.pyplot as plt
# Set Matplotlib to non-interactive mode for server environment
matplotlib.use('Agg')
from sqlalchemy import text
from datetime import timedelta


router = APIRouter(prefix="/egai", tags=["What If - Analysis"])

logger = get_logger()


MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)
MAX_JOBS_HISTORY = 5
TRAINING_JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = asyncio.Lock() 
FEATURE_VALUES_TTL = 604800  # Cache for 7 days

##################################
LOGS_DIR = Path("model_logs")
LOGS_DIR.mkdir(exist_ok=True)

PREDICTION_LOG_FILE = LOGS_DIR / "prediction_activity.json"

def log_prediction_activity(model_id: str, inference_time: float):
    """Appends prediction activity to a JSON log file."""
    try:
        entry = {
            "model_id": model_id,
            "timestamp": datetime.now().isoformat(),
            "inference_time": inference_time
        }
        
        # Simple file lock mechanism could be added here for high concurrency
        if PREDICTION_LOG_FILE.exists():
            with open(PREDICTION_LOG_FILE, "r+") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
                data.append(entry)
                f.seek(0)
                json.dump(data, f, indent=2)
        else:
            with open(PREDICTION_LOG_FILE, "w") as f:
                json.dump([entry], f, indent=2)
    except Exception as e:
        logger.error(f"Failed to log prediction activity: {e}")

def get_prediction_logs(model_id: str = None) -> List[Dict]:
    """Reads prediction logs, optionally filtered by model_id."""
    if not PREDICTION_LOG_FILE.exists():
        return []
    try:
        with open(PREDICTION_LOG_FILE, "r") as f:
            data = json.load(f)
        if model_id:
            return [d for d in data if d.get("model_id") == model_id]
        return data
    except Exception:
        return []
    

#####################################
class JobDetails(TrainModelRequest):
    job_id: str
    session: AsyncSession
    df: pd.DataFrame

    model_config = ConfigDict(arbitrary_types_allowed=True)


# MODEL REGISTRY

# @router.post("/model_registry/get_models")
# async def get_all_models(    
#     data: ResetChat, 
#     session: AsyncSession = Depends(get_db_async)
# ):


@router.post("/model_registry/get_models")
async def get_all_models(
    data: GetModelsRequest,
    session: AsyncSession = Depends(get_db_async),
):
    i_data = InternalSQLHelper(session)

    ml_model_details = await i_data.get_all_models()

    for mld in ml_model_details:
        mld.model_details = json.loads(mld.model_details)

    return ml_model_details

# @router.post("/model_registry/get_models")
# async def get_all_models(
#     data: GetModelsRequest,
#     session: AsyncSession = Depends(get_db_async),
# ):
#     i_data = InternalSQLHelper(session)

#     # Fetch all ML models
#     ml_model_details = await i_data.get_all_models()

#     enriched_models = []
#     for mld in ml_model_details:
#         # Convert model_details JSON string to dictionary
#         mld.model_details = json.loads(mld.model_details)

#         # Get user name from operation_by (user ID)
#         user = await i_data.get_user_details_from_userid(mld.operation_by)
#         if user:
#             operation_by_name = f"{user.first_name} {user.last_name}"
#         else:
#             operation_by_name = f"User ID {mld.operation_by}"

#         # Get db_name from db_id
#         db = await i_data.get_db_details_from_dbid(mld.db_id)
#         db_name = db.db_name if db else f"DB ID {mld.db_id}"

#         # Build enriched model dict
#         enriched_models.append({
#             "operation_by": operation_by_name,
#             "model_version": mld.model_version,
#             "model_details": mld.model_details,
#             "lineage": mld.lineage,
#             "db_name": db_name,
#             "id": mld.id,
#             "table_name": mld.table_name,
#             "target_column": mld.target_column,
#             "model_type": mld.model_type,
#             "is_final": mld.is_final,
#             "created_on": mld.created_on
#         })

#     return enriched_models



@router.post("/model_registry/get_models_lineage")
async def get_all_models_from_lineage(    
    data: ModelRequestLineage, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    db_details = await i_data.get_db_details_from_dbname(data.dbname)

    ml_model_details = await i_data.get_ml_model_details(
        db_details.id,
        data.table_name,
        data.target_column
    )

    for mld in ml_model_details:
        mld.model_details = json.loads(mld.model_details)

    return ml_model_details


# MODEL TRAINING

@router.post("/model_training/available_datasets", status_code=200)
async def get_available_datasets(data: UserName, session: AsyncSession = Depends(get_db_async)):
    i_data = InternalSQLHelper(session)

    user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)
    
    with open("app/clientConfig.yaml", "r") as f:
        config_dict = yaml.safe_load(f)

    if not config_dict.keys():
        raise HTTPException(status_code=404, detail="No Datasets found")

    return {
        "status": 200,
        "message": "Datasets found",
        "datasets": list(config_dict.keys())
    }


@router.post("/model_training/available_tables", status_code=200)
async def get_tables_for_dataset(data: ResetChat, session: AsyncSession = Depends(get_db_async)):
    i_data = InternalSQLHelper(session)

    user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)
    
    with open("app/clientConfig.yaml", "r") as f:
        config_dict = yaml.safe_load(f)

    available_tables = config_dict.get(data.dbname, {})["DATABASE"].get("available_tables", [])

    if not available_tables:
        raise HTTPException(status_code=404, detail="No tables configured for given dataset")

    return {
        "status": 200,
        "message": "Tables found",
        "dbname": data.dbname,
        "tables": available_tables
    }


@router.post("/model_training/available_columns", status_code=200)
async def get_columns_from_table(data: TargetVariable, session: AsyncSession = Depends(get_db_async)):
    i_data = InternalSQLHelper(session)
    client_pool = client_connection_pool

    user_details = await i_data.create_or_get_user(first_name=data.first_name, last_name=data.last_name, email_id=data.email_id)
    if not user_details:
        raise HTTPException(detail="user does not exists nor created successfully", status_code=404)
    
    sql = f"SELECT TOP 1 * from {data.table_name}"
    table_details = await get_table_from_sql(client_pool, sql_query=sql)
    
    return {
        "status": 200,
        "message": "Variables/Columns found",
        "dbname": data.dbname,
        "table_name": data.table_name,
        "available_columns": table_details.columns
    }



async def cleanup_old_jobs():
    async with JOBS_LOCK:
        if len(TRAINING_JOBS) > MAX_JOBS_HISTORY:
            completed = [
                job_id for job_id, job in TRAINING_JOBS.items()
                if job["status"] in ["completed", "failed"]
            ]
            # Keep only recent completed jobs
            for job_id in completed[:-2]:  # Keep last 2 completed
                del TRAINING_JOBS[job_id]
                logger.info(f"Cleaned up old job: {job_id}")

async def update_job_status(job_id: str, updates: Dict[str, Any]):
    async with JOBS_LOCK:
        if job_id in TRAINING_JOBS:
            TRAINING_JOBS[job_id].update(updates)

async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    async with JOBS_LOCK:
        return TRAINING_JOBS.get(job_id, None)
    
def get_metric_name(task: str) -> str:    # Need to be Updated to allow user to select performance metric
    return "rmse" if task == "regression" else "accuracy"


@router.post("/model_training/train_model", status_code=201)
async def train_model(
    data: TrainModelRequest, 
    bg_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_async)
):
    async with JOBS_LOCK:
        active_jobs = [
            job for job in TRAINING_JOBS.values()
            if job["status"] in ("queued", "training")
        ]

    if len(active_jobs) >= 2:
        return JSONResponse(
            status_code=429,
            content={
                "status": "rejected",
                "reason": "Maximum number of active training jobs reached.",
                "limit": 2
            }
        )
    client_pool = client_connection_pool

    sql = f"SELECT COUNT({data.target_column}) from {data.table_name}"
    table_details = await get_table_from_sql(client_pool, sql_query=sql)
    total_rows = table_details.rows[0][0]

    if total_rows>=10000:
        rows_to_fetch = 10000
    else:
        rows_to_fetch = total_rows

    file_path = f"app/core/what_if_analysis/temp_data/{data.table_name}.parquet"
    if not os.path.exists(file_path):
        logger.debug("reading data from sql")
        sql = f"SELECT TOP {rows_to_fetch} * from {data.table_name} ORDER BY NEWID()"
        table_details = await get_table_from_sql(client_pool, sql_query=sql, row_limit=10_000)
        table_json, table_status, table_columns = get_table_and_status_and_columns(table_details)
        df = pd.DataFrame(table_json)
        df.to_parquet(f"app/core/what_if_analysis/temp_data/{data.table_name}.parquet")
    else:
        logger.debug("reading data from temp path")
        df = pd.read_parquet(file_path)
        table_json = df.to_dict(orient="records")

    # df = df.iloc[:100] # TO BE REOMVED AFTER TESTING

    job_id = str(uuid.uuid4())
    
    async with JOBS_LOCK:
        TRAINING_JOBS[job_id] = {
            "status": "queued",
            "progress": "Initializing...",
            "started_at": datetime.now().isoformat(),
            "request": dict(data)
        }

    training_job_details = JobDetails(
        **data.model_dump(), 
        job_id=job_id, 
        session=session, 
        df=df
    )

    bg_tasks.add_task(run_training_wrapper, training_job_details)
    bg_tasks.add_task(cleanup_old_jobs)

    logger.info(f"Training job {job_id} queued")
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Training started in background"
    }


async def run_training_wrapper(training_job_details: JobDetails):
    try:
        i_data = InternalSQLHelper(training_job_details.session)
        
        user_details = await i_data.get_user_details_from_username(
            training_job_details.first_name, 
            training_job_details.last_name
        ) 
        db_details = await i_data.get_db_details_from_dbname(training_job_details.dbname)

        older_model_details = await i_data.get_ml_model_details(
            db_details.id, 
            training_job_details.table_name,
            training_job_details.target_column
        )

        if not older_model_details:
            model_version = 1
        else:
            model_version = max([m.model_version for m in older_model_details]) + 1

        model_lineage = f"{training_job_details.dbname}__{training_job_details.table_name}__{training_job_details.target_column}"
        
        # ✅ Get the current event loop and pass it to sync function
        loop = asyncio.get_event_loop()
        
        # Run CPU-intensive training in thread pool
        model_dict = await asyncio.to_thread(
            run_training_job, 
            training_job_details, 
            model_version,
            loop  # Pass the event loop
        )

        if not model_dict:
            logger.error("Model not trained properly")
        else:
            model_details = {
                "best_estimator": model_dict["model"].best_estimator,
                "best_score": float(model_dict["model"].best_loss),
                "evaluation_metric": model_dict["evaluation_metric"],
                "model_feature_importances": {
                    k: v for k, v in zip(
                        list(model_dict["model"].model.feature_names_in_), 
                        [float(i) for i in list(model_dict["model"].model.estimator.feature_importances_)]
                    )
                }
            }
            
            await i_data.record_ml_model_details({
                "db_id": db_details.id,
                "operation_by": user_details.id,
                "table_name": training_job_details.table_name,
                "target_column": training_job_details.target_column,
                "model_version": model_version,
                "model_type": model_dict["model_type"],
                "model_details": json.dumps(model_details),
                "lineage": model_lineage
            })

    except Exception as e:
        logger.error(f"Training wrapper failed: {str(e)}", exc_info=True)
        await update_job_status(training_job_details.job_id, {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })


def is_continuous(series: pd.Series, unique_threshold=0.1):
    if pd.api.types.is_numeric_dtype(series):
        if pd.api.types.is_float_dtype(series) or (series % 1 != 0).any():
            return True
        else:
            if series.nunique() / len(series) > unique_threshold:
                return True
    return False


def run_training_job(training_job_details: JobDetails, model_version: int, loop: asyncio.AbstractEventLoop):
    """Synchronous training task (runs in thread pool)"""
    try:

        def update_status(updates: dict):
            """Helper to update status from sync code"""
            future = asyncio.run_coroutine_threadsafe(
                update_job_status(training_job_details.job_id, updates), loop)
            future.result(timeout=5)

        # Update status: Loading data
        update_status({
            "status": "loading_data",
            "progress": "Loading dataset..."
        })
        
        # Validate label exists
        if training_job_details.target_column not in training_job_details.df.columns:
            raise ValueError(f"Label '{training_job_details.target_column}' not found in columns: {training_job_details.df.columns.tolist()}")
        
        # Split data
        X = training_job_details.df.drop(columns=[training_job_details.target_column])
        if training_job_details.fields_to_exclude:
            X = X.drop(training_job_details.fields_to_exclude, axis=1)
        y = training_job_details.df[training_job_details.target_column]

        test_size = 0.2
        
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=test_size, random_state=42)
        logger.info(f"Job {training_job_details.job_id}: Train size={len(X_train)}, Val size={len(X_val)}")
        
        update_status({
            "status": "training",
            "progress": f"Training on {len(X_train)} samples..."
        })
        
        regression_or_classification = "regression" if is_continuous(training_job_details.df[training_job_details.target_column]) else "classification"
        evaluation_metric = get_metric_name(regression_or_classification)

        # Configure AutoML
        automl = AutoML()
        settings = {
            "task": regression_or_classification,
            # "time_budget": 3600,
            "max_iter": 2, # TO BE REOMVED AFTER TESTING
            "metric": evaluation_metric,
            # "estimator_list": ["lgbm", "xgboost"],
            "estimator_list": ["lgbm", "xgboost", "catboost", "extra_tree", "rf"],
            "log_file_name": f"logs/train_{training_job_details.job_id}.log",
            "verbose": True,
        }
        
        # Train model
        automl.fit(
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val,
            **settings
        )
        
        # Save model with version
        update_status({
            "status": "saving",
            "progress": "Saving model..."
        })
        

        DB_MODELS_DIR = MODEL_DIR / training_job_details.dbname
        FINAL_MODELS_DIR = DB_MODELS_DIR / "final_models"
        VERSIONED_MODELS_DIR = DB_MODELS_DIR / "versioned_models"
        FINAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        VERSIONED_MODELS_DIR.mkdir(parents=True, exist_ok=True)

        versioned_path = VERSIONED_MODELS_DIR / f"model__{training_job_details.dbname}__{training_job_details.table_name}__{training_job_details.target_column}__{model_version}.pkl"

        # Saving as verioned model. It will be moved to final after user finalizesthe model
        joblib.dump(automl, versioned_path)
        
        logger.info(f"Job {training_job_details.job_id}: Model saved to {versioned_path}")
        
        # Update status: Completed
        update_status({
            "status": "completed",
            "progress": "Training completed successfully",
            "best_model": automl.best_estimator,
            "best_score": automl.best_loss,
            "model_path": str(versioned_path),
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"Job {training_job_details.job_id}: Completed. Best model: {automl.best_estimator}, Score: {automl.best_loss}")
        return {
            "model": automl,
            "model_type": regression_or_classification,
            "evaluation_metric": evaluation_metric
        }
    
    except Exception as ex:
        logger.error(f"Job {training_job_details.job_id} failed: {str(ex)}", exc_info=True)
        asyncio.run(update_job_status(training_job_details.job_id, {
            "status": "failed",
            "error": str(ex),
            "completed_at": datetime.now().isoformat()
        }))


@router.post("/model_training/check_training_status")
async def check_training_status_from_jobid(data: TrainModelStatus):
    
    job = await get_job_status(data.job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": data.job_id,
        "status": job["status"],
        "progress": job.get("progress"),
        "best_model": job.get("best_model"),
        "best_score": job.get("best_score"),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at")
    }


# State will only remain till application is running. It resets on application start
@router.post("/model_training/gat_jobs_in_state")
async def list_all_jobsin_current_state():
    async with JOBS_LOCK:
        jobs = [
            {
                "job_id": job_id,
                "status": job["status"],
                "started_at": job.get("started_at"),
                "best_model": job.get("best_model")
            }
            for job_id, job in TRAINING_JOBS.items()
        ]
    return {
        "jobs": jobs
    }


@router.post("/model_training/finalize_model")
async def use_as_final_model(    
    data: FinalizeModel, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    db_details = await i_data.get_db_details_from_dbname(data.dbname)

    ml_model_details = await i_data.get_ml_model_details_versioned(
        db_details.id,
        data.table_name,
        data.target_column,
        data.model_version
    )

    DB_MODELS_DIR = MODEL_DIR / data.dbname
    FINAL_MODELS_DIR = DB_MODELS_DIR / "final_models"
    VERSIONED_MODELS_DIR = DB_MODELS_DIR / "versioned_models"
    FINAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONED_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    versioned_model_path = VERSIONED_MODELS_DIR / f"model__{data.dbname}__{data.table_name}__{data.target_column}__{data.model_version}.pkl"
    
    if not ml_model_details or not os.path.exists(versioned_model_path):
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        shutil.copy(versioned_model_path, FINAL_MODELS_DIR)
        ml_model_details = await i_data.update_model_details(ml_model_details.id, {"is_final": True})
    except Exception as e:
        raise HTTPException(detail="Model not finalized", status_code=400)

    return ml_model_details


@router.post("/model_predictions/get_base_feature_values")
async def get_base_features_and_values_for_prediction(
    data: PredictionFeatureRequest,
    session: AsyncSession = Depends(get_db_async),
    redis_client = Depends(get_caching_client)
):
    i_data = InternalSQLHelper(session)

    cache_key = f"base_feature_defaults::{data.dbname}::{data.model_id}"

    cached_result = await get_cached_data(redis_client, cache_key)
    if cached_result is not None:
        return cached_result

    user_details = await i_data.get_user_details_from_username(data.first_name, data.last_name)
    if not user_details:
        raise HTTPException(detail="User not found", status_code=404)

    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(detail="Model does not exists", status_code=404)
    
    # db_details = await i_data.get_db_details_from_dbname(data.dbname)
    # if not model_details:
    #     raise HTTPException(detail="Model does not exists", status_code=404)
    
    # model_name = f"model__{data.dbname}__{model_details.table_name}__{model_details.target_column}__{model_details.model_version}.pkl"

    # DB_MODELS_DIR = MODEL_DIR / data.dbname
    # if model_details.is_final:
    #     model_path = DB_MODELS_DIR / "final_models" / model_name
    # else:
    #     model_path = DB_MODELS_DIR / "versioned_models" / model_name
    
    # if not os.path.exists(model_path):
    #     raise HTTPException(detail="Model Does not exists in path", status_code=404)

    # automl = await asyncio.to_thread(joblib.load, model_path)

    # features_in_model = list(automl.model.feature_names_in_)

    # df = pd.read_parquet("app/core/what_if_analysis/temp_data/Lenovo_data_revised.parquet")
    # df_describe = df.describe(include="all")
    # df_describe = df_describe.fillna("XXXX")

    # feature_value_mappings = []
    # for c in df.columns:
    #     if c in features_in_model:
    #         if df_describe[c]["50%"] == "XXXX":
    #             feature_value_mappings.append({
    #                 "variable": c,
    #                 "value": df_describe[c]["top"]
    #             })
    #         else:
    #             feature_value_mappings.append({
    #                 "variable": c,
    #                 "value": df_describe[c]["50%"]
    #             })
    
    # return feature_value_mappings

    ##############readind data from database##################
    db_details = await i_data.get_db_details_from_dbname(data.dbname)

    model_name = f"model__{data.dbname}__{model_details.table_name}__{model_details.target_column}__{model_details.model_version}.pkl"
    DB_MODELS_DIR = MODEL_DIR / data.dbname
    model_path = DB_MODELS_DIR / ("final_models" if model_details.is_final else "versioned_models") / model_name

    if not os.path.exists(model_path):
        raise HTTPException(detail="Model Does not exists in path", status_code=404)

    #Load model
    automl = await asyncio.to_thread(joblib.load, model_path)
    features_in_model = list(automl.model.feature_names_in_)

    #Load data from correct table
    sql = f"SELECT * FROM {model_details.table_name}"
    table_details = await get_table_from_sql(client_connection_pool, sql_query=sql, row_limit=10000)

    table_json, _, _ = get_table_and_status_and_columns(table_details)
    df = pd.DataFrame(table_json)

    #Compute default values (median / mode)
    feature_value_mappings = []

    for col in features_in_model:
        if col not in df.columns:
            continue

        series = df[col]

        if pd.api.types.is_numeric_dtype(series):
            value = series.median()
        else:
            value = series.mode().iloc[0] if not series.mode().empty else None

        feature_value_mappings.append({
            "variable": col,
            "value": value
        })
    
    await cache_data(redis_client, cache_key, feature_value_mappings, FEATURE_VALUES_TTL)


    return feature_value_mappings


@router.post("/model_predictions/predict")
async def predict_value_from_provided_feature_values(
    data: PredictRequest,
    session: AsyncSession = Depends(get_db_async)
):
    start_time = datetime.now()

    i_data = InternalSQLHelper(session)

    user_details = await i_data.get_user_details_from_username(data.first_name, data.last_name)
    if not user_details:
        raise HTTPException(detail="User not found", status_code=404)

    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(detail="Model does not exists", status_code=404)
    
    db_details = await i_data.get_db_details_from_dbname(data.dbname)
    if not model_details:
        raise HTTPException(detail="Model does not exists", status_code=404)
    
    model_name = f"model__{data.dbname}__{model_details.table_name}__{model_details.target_column}__{model_details.model_version}.pkl"

    DB_MODELS_DIR = MODEL_DIR / data.dbname
    if model_details.is_final:
        model_path = DB_MODELS_DIR / "final_models" / model_name
    else:
        model_path = DB_MODELS_DIR / "versioned_models" / model_name
    
    if not os.path.exists(model_path):
        raise HTTPException(detail="Model Does not exists in path", status_code=404)

    automl = await asyncio.to_thread(joblib.load, model_path)

    features_dict = {i.variable:i.value for i in data.features}
    x_df =  pd.DataFrame([features_dict])
    
    predictions = await asyncio.to_thread(automl.predict, x_df)

    # model_details.model_details = json.loads(model_details.model_details) 
    response_model_config = {}
    if model_details.model_details:
        try:
            response_model_config = json.loads(model_details.model_details)
        except:
            response_model_config = {}
    # <--- LOGGING START --->
    try:
        duration = (datetime.now() - start_time).total_seconds() * 1000
        await i_data.log_model_activity(
            model_id=data.model_id, 
            user_id=user_details.id, 
            req_type="predict", 
            time_taken=duration
        )
    except Exception as e:
        logger.error(f"Logging failed: {e}")
    # <--- LOGGING END --->

    return {
        "model_config": response_model_config,
        "prediction": predictions.tolist()
    }






# @router.post("/model_analysis/feature_importance")
# async def get_feature_importance_stats(
#     data: PredictionFeatureRequest,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     """
#     Returns feature importance strictly from the SAVED model details in the database.
#     Does NOT access raw data, SQL tables, or temporary parquet files.
#     """
#     i_data = InternalSQLHelper(session)

#     # 1. Fetch Model Details from Database
#     model_record = await i_data.get_model_details_from_id(data.model_id)
#     if not model_record:
#         raise HTTPException(status_code=404, detail="Model not found")

#     # 2. Parse the JSON stored in the DB
#     try:
#         model_meta = json.loads(model_record.model_details)
#     except Exception:
#         # Fallback if JSON is corrupt
#         model_meta = {}

#     # 3. Get the Importance Dict
#     importances = model_meta.get("model_feature_importances", {})
    
#     if not importances:
#         return {
#             "status": "success",
#             "message": "No feature importance data found in model metadata.",
#             "total_importance": 0,
#             "feature_statistics": []
#         }

#     # 4. Format and Sort the Data (Pure CPU logic, no data loading)
#     total_importance = sum(importances.values())
#     stats_data = []

#     for feature, score in importances.items():
        
#         # Calculate Percentage
#         importance_percentage = (score / total_importance) * 100 if total_importance > 0 else 0.0

#         stats_data.append({
#             "feature": feature,
#             "importance_score_raw": score,
#             "importance_percentage": f"{importance_percentage:.2f}%",
#             # We cannot provide Mean/Median/Mode without accessing the raw data table
#             "mean": "N/A", 
#             "median": "N/A",
#             "mode": "N/A"
#         })
    
#     # Sort by importance descending
#     stats_data.sort(key=lambda x: x["importance_score_raw"], reverse=True)

#     return {
#         "status": "success",
#         "total_importance": total_importance,
#         "feature_statistics": stats_data
#     }



@router.post("/model_analysis/feature_importance")
async def get_feature_importance_stats(
    data: PredictionFeatureRequest,
    session: AsyncSession = Depends(get_db_async)
):
    """
    Returns feature importance from Saved Model.
    Calculates Mean, Median, Mode by reading data directly from SQL (InMemory),
    matching the logic of 'get_base_feature_values'.
    """
    i_data = InternalSQLHelper(session)

    # 1. Fetch Model Details
    model_record = await i_data.get_model_details_from_id(data.model_id)
    if not model_record:
        raise HTTPException(status_code=404, detail="Model not found")

    # 2. Get Importance Dict from Metadata
    try:
        model_meta = json.loads(model_record.model_details)
    except:
        model_meta = {}
    
    importances = model_meta.get("model_feature_importances", {})
    if not importances:
        return {"status": "success", "feature_statistics": []}

    # 3. Load Data directly from SQL (Same logic as get_base_feature_values)
    # We avoid temp parquet files here.
    df = pd.DataFrame()
    try:
        # Load data from correct table
        # Limiting to 10,000 rows for performance (sufficient for stats estimation)
        sql = f"SELECT TOP 10000 * FROM {model_record.table_name}"
        
        # Note: Ensure client_connection_pool is imported available
        table_details = await get_table_from_sql(client_connection_pool, sql_query=sql, row_limit=10000)
        
        table_json, _, _ = get_table_and_status_and_columns(table_details)
        df = pd.DataFrame(table_json)
    except Exception as e:
        logger.error(f"Failed to load data for stats: {e}")
        # We continue even if data load fails, returning just the importance scores
        pass

    # 4. Calculate Stats
    def compute_stats_logic(dataframe, importance_dict):
        total_importance = sum(importance_dict.values())
        stats_data = []

        for feature, score in importance_dict.items():
            
            # Defaults
            mean_val = "N/A"
            median_val = "N/A"
            mode_val = "N/A"

            # If dataframe loaded successfully and column exists
            if not dataframe.empty and feature in dataframe.columns:
                series = dataframe[feature]
                
                # Calculate Stats based on Type
                if pd.api.types.is_numeric_dtype(series):
                    try:
                        mean_val = round(float(series.mean()), 2)
                        median_val = round(float(series.median()), 2)
                        # For numeric, mode can be multiple, take first
                        if not series.mode().empty:
                            mode_val = round(float(series.mode().iloc[0]), 2)
                    except:
                        pass
                else:
                    # Categorical / Object
                    if not series.mode().empty:
                        mode_val = str(series.mode().iloc[0])
                    # Mean/Median don't apply to categorical
            
            # Percent calculation
            importance_percentage = (score / total_importance) * 100 if total_importance > 0 else 0.0

            stats_data.append({
                "feature": feature,
                "importance_score_raw": score,
                "importance_percentage": f"{importance_percentage:.2f}%"
                # "mean": mean_val,
                # "median": median_val,
                # "mode": mode_val
            })
        
        # Sort by importance
        stats_data.sort(key=lambda x: x["importance_score_raw"], reverse=True)
        return total_importance, stats_data

    # Run calculation
    total_imp, feature_stats = await run_in_threadpool(compute_stats_logic, df, importances)

    return {
        "status": "success",
        "total_importance": total_imp,
        "feature_statistics": feature_stats
    }


###########################################
def load_automl_model(model_details, dbname: str):
    model_name = (
        f"model__{dbname}__"
        f"{model_details.table_name}__"
        f"{model_details.target_column}__"
        f"{model_details.model_version}.pkl"
    )

    base_dir = MODEL_DIR / dbname
    model_path = base_dir / (
        "final_models" if model_details.is_final else "versioned_models"
    ) / model_name

    if not model_path.exists():
        raise FileNotFoundError("Model file not found")

    return joblib.load(model_path)



def build_model_instance(
    automl,
    raw_df: pd.DataFrame,
    user_features: dict
) -> pd.DataFrame:
    """
    Build a fully aligned single-row DataFrame
    matching AutoML model feature schema.
    """

    model_features = list(automl.model.feature_names_in_)

    # Validate user inputs
    invalid = set(user_features) - set(model_features)
    if invalid:
        raise HTTPException(
            400,
            f"Invalid features provided: {sorted(invalid)}"
        )

    instance = {}

    for col in model_features:
        if col in user_features:
            instance[col] = user_features[col]
        else:
            series = raw_df[col]
            if pd.api.types.is_numeric_dtype(series):
                instance[col] = series.median()
            else:
                mode = series.mode()
                instance[col] = mode.iloc[0] if not mode.empty else None

    return pd.DataFrame([instance], columns=model_features)

from sklearn.preprocessing import LabelEncoder

# def generate_lime_plot(explanation) -> Optional[str]:
#     """
#     Generates a LIME plot from the explanation object and returns Base64 string.
#     """
#     try:
#         # LIME has a built-in method to create a matplotlib figure
#         # label=1 usually creates the plot for the positive class in classification
#         # or the predicted value in regression.
#         fig = explanation.as_pyplot_figure()
        
#         # Save to buffer
#         buf = io.BytesIO()
#         fig.tight_layout()
#         fig.savefig(buf, format="png", bbox_inches="tight")
#         plt.close(fig)  # Important: Close plot to free memory
        
#         buf.seek(0)
#         img_str = base64.b64encode(buf.read()).decode("utf-8")
#         return img_str
#     except Exception as e:
#         logger.error(f"Error generating LIME plot: {e}")
#         return None

def generate_lime_plot_plotly(explanation) -> dict:
    """
    Generates a Plotly Horizontal Bar chart for LIME with Red/Green coloring.
    """
    try:
        # 1. Extract data from LIME explanation
        # returns list of tuples: [('feature_A', 0.5), ('feature_B', -0.2)]
        data_list = explanation.as_list()
        
        # Reverse to put the most important feature at the top in Plotly
        data_list.reverse() 
        
        features = [x[0] for x in data_list]
        scores = [x[1] for x in data_list]
        
        # 2. Determine Colors (Green for Positive, Red for Negative)
        colors = ['#28a745' if s > 0 else '#dc3545' for s in scores]

        # 3. Create Figure
        fig = go.Figure(go.Bar(
            x=scores,
            y=features,
            orientation='h',
            marker_color=colors,
            text=[f"{s:.4f}" for s in scores], # Show values on bars
            textposition='auto',
            hovertemplate='<b>Feature</b>: %{y}<br><b>Contribution</b>: %{x}<extra></extra>'
        ))

        fig.update_layout(
            title="LIME Local Feature Importance",
            xaxis_title="Contribution to Prediction",
            yaxis_title="Features",
            template="plotly_white",
            margin=dict(l=150, r=20, t=40, b=40) # Extra left margin for long feature names
        )

        fig.update_yaxes(linewidth=1.2, ticklabelstandoff=10)
        fig.update_xaxes(showgrid=True, linewidth=1.2)

        return fig.to_json()
    except Exception as e:
        logger.error(f"Error generating LIME Plotly graph: {e}")
        return None


def generate_shap_plot_plotly(explanation_obj) -> dict:
    """
    Generates a Plotly Waterfall chart for SHAP.
    """
    try:
        # 1. Extract Data
        # SHAP objects can be complex, we extract the raw arrays
        features = np.array(explanation_obj.feature_names)
        values = np.array(explanation_obj.values)
        base_value = float(explanation_obj.base_values)
        
        # 2. Sort by Absolute Importance (Top 10) to avoid clutter
        # Get indices of top 10 features by absolute value
        top_indices = np.argsort(np.abs(values))[-10:] 
        
        # Filter and Sort
        top_features = features[top_indices]
        top_values = values[top_indices]
        
        # 3. Create Waterfall Chart
        fig = go.Figure(go.Waterfall(
            name = "SHAP",
            orientation = "v",
            measure = ["relative"] * len(top_values),
            x = top_features,
            y = top_values,
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#dc3545"}}, # Red
            increasing = {"marker":{"color":"#28a745"}}, # Green
            totals = {"marker":{"color":"#007bff"}}      # Blue (if we added a total bar)
        ))

        # Add a line for the Base Value (Starting point)
        # Note: Waterfall charts in Plotly represent delta. 
        # To make it intuitive, we title it with the base/final values.
        final_pred = base_value + np.sum(values)

        fig.update_layout(
            title=f"SHAP Waterfall (Base: {base_value:.4f} → Pred: {final_pred:.4f})",
            xaxis_title="Features",
            yaxis_title="Contribution to Prediction",
            template="plotly_white",
            showlegend = False
        )

        fig.update_yaxes(showgrid=True, linewidth=1.2)
        fig.update_xaxes(linewidth=1.2)

        return fig.to_json()

    except Exception as e:
        logger.error(f"Error generating SHAP Plotly graph: {e}")
        return None

class LimeEncoder:
    """
    Helper to bridge the gap between LIME (needs numeric/int) 
    and FLAML (needs original strings/dataframes).
    """
    def __init__(self):
        self.encoders = {}
        self.feature_names = []
        self.categorical_features_indices = []
        self.categorical_names_map = {}
        self.original_dtypes = {}

    def fit(self, df: pd.DataFrame):
        self.feature_names = list(df.columns)
        self.original_dtypes = df.dtypes
        
        # Create a copy to work on
        data = df.copy()

        for idx, col in enumerate(self.feature_names):
            # Check if column is categorical (object, category, or bool)
            if not pd.api.types.is_numeric_dtype(df[col]):
                self.categorical_features_indices.append(idx)
                
                # Handle NaNs before encoding
                data[col] = data[col].fillna("Unknown").astype(str)
                
                le = LabelEncoder()
                le.fit(data[col])
                self.encoders[idx] = le
                self.categorical_names_map[idx] = le.classes_.tolist()
            else:
                # Fill numeric NaNs for LIME stability
                if data[col].isnull().any():
                     data[col] = data[col].fillna(data[col].median())

        return data

    def transform_to_lime_format(self, df: pd.DataFrame) -> np.ndarray:
        """Converts DataFrame to Numpy array with encoded categoricals"""
        data = df.copy()
        for idx, col in enumerate(self.feature_names):
            if idx in self.encoders:
                le = self.encoders[idx]
                # Handle unseen labels carefully
                data[col] = data[col].fillna("Unknown").astype(str)
                # Map known labels to codes, unknown to -1 (or handle gracefully)
                data[col] = data[col].map(lambda x: getattr(le, 'transform', lambda y: [0])([x])[0] if x in le.classes_ else 0)
            else:
                data[col] = data[col].astype(float)
        return data.values

    def inverse_transform_to_model_format(self, numpy_array: np.ndarray) -> pd.DataFrame:
        """Converts LIME Numpy array back to DataFrame for FLAML"""
        df_dict = {}
        for idx, col in enumerate(self.feature_names):
            col_data = numpy_array[:, idx]
            
            if idx in self.encoders:
                # Round to nearest int because LIME might generate 1.0001
                col_indices = np.round(col_data).astype(int)
                le = self.encoders[idx]
                # Clip to safe range
                col_indices = np.clip(col_indices, 0, len(le.classes_) - 1)
                df_dict[col] = le.inverse_transform(col_indices)
            else:
                df_dict[col] = col_data
        
        # Reconstruct DataFrame
        df_res = pd.DataFrame(df_dict)
        
        # Attempt to cast back to original dtypes where possible
        for col, dtype in self.original_dtypes.items():
            if pd.api.types.is_integer_dtype(dtype):
                df_res[col] = df_res[col].astype(int)
            # We leave floats as floats and strings as objects
            
        return df_res

# --- API ENDPOINTS ---

@router.post("/model_analysis/lime")
async def explain_with_lime(
    data: PredictRequest, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    # 1. Fetch Model Details
    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(404, "Model not found")

    # 2. Load FLAML Model
    try:
        automl = await asyncio.to_thread(load_automl_model, model_details, data.dbname)
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise HTTPException(500, "Could not load model file")

    # 3. Load Reference Data (SQL)
    try:
        sql = f"SELECT TOP 1000 * FROM {model_details.table_name}"
        table_details = await get_table_from_sql(client_connection_pool, sql)
        table_json, _, _ = get_table_and_status_and_columns(table_details)
        reference_df = pd.DataFrame(table_json)
        
        # Filter columns
        model_features = list(automl.model.feature_names_in_)
        reference_df = reference_df[model_features]
    except Exception as e:
        raise HTTPException(500, "Failed to fetch reference data")

    # 4. Initialize Encoder 
    encoder_helper = LimeEncoder()
    encoder_helper.fit(reference_df)
    training_data_numpy = encoder_helper.transform_to_lime_format(reference_df)

    # 5. Prepare User Instance
    user_features_dict = {f.variable: f.value for f in data.features}
    instance_row_df = build_model_instance(automl, reference_df, user_features_dict)
    instance_numpy = encoder_helper.transform_to_lime_format(instance_row_df)[0]

    # 6. CAPABILITY CHECK: Determine Mode Dynamically
    # We test the model with one row to see if it supports predict_proba
    is_classification = False
    class_names = None
    
    try:
        # Test prediction on the first row of reference data
        test_input = encoder_helper.inverse_transform_to_model_format(training_data_numpy[0:1])
        
        # Try calling predict_proba
        _ = automl.predict_proba(test_input)
        
        # If no error, it is classification
        is_classification = True
        if hasattr(automl.model, 'classes_'):
            class_names = list(map(str, automl.model.classes_))
        else:
            class_names = ["0", "1"]
            
    except Exception:
        # If predict_proba fails (AssertionError or AttributeError), it is Regression
        is_classification = False
        class_names = ["prediction_value"]

    mode = "classification" if is_classification else "regression"
    logger.info(f"LIME Analysis running in mode: {mode}")

    # 7. Define Prediction Wrapper
    def predict_wrapper(numpy_array):
        # Convert LIME's numpy array -> DataFrame
        X_reconstructed = encoder_helper.inverse_transform_to_model_format(numpy_array)
        
        if is_classification:
            try:
                probs = automl.predict_proba(X_reconstructed)
                if hasattr(probs, 'values'):
                    return probs.values
                return probs
            except:
                # Fallback to regression behavior if weird edge case
                return automl.predict(X_reconstructed)
        else:
            # For regression, LIME expects a 1D array, but FLAML returns (N,) or (N,1)
            preds = automl.predict(X_reconstructed)
            if hasattr(preds, 'values'):
                preds = preds.values
            return preds

    # 8. Run LIME
    def run_lime_explanation():
        explainer = lime.lime_tabular.LimeTabularExplainer(
            training_data=training_data_numpy,
            feature_names=encoder_helper.feature_names,
            categorical_features=encoder_helper.categorical_features_indices,
            categorical_names=encoder_helper.categorical_names_map,
            class_names=class_names,
            mode=mode,
            verbose=False,
            random_state=42
        )

        explanation = explainer.explain_instance(
            data_row=instance_numpy,
            predict_fn=predict_wrapper,
            num_features=10,
            # Only use top_labels for classification
            top_labels=1 if is_classification else None
        )
        return explanation

    try:
        exp = await run_in_threadpool(run_lime_explanation)
        # plot_base64 = await run_in_threadpool(generate_lime_plot, exp)
        graph_json = await run_in_threadpool(generate_lime_plot_plotly, exp)
        
        
        formatted_results = [{"feature": f, "weight": float(w)} for f, w in exp.as_list()]
        
        # Get predicted value safely
        try:
            if is_classification:
                prediction_val = exp.predict_proba.tolist()
            else:
                # Regression usually stores score in .predicted_value (scalar)
                prediction_val = float(exp.predicted_value)
        except:
            prediction_val = "N/A"

        return {
            "status": "success",
            "mode": mode,
            "prediction_value": prediction_val,
            "local_feature_importance": formatted_results,
            "graph": graph_json
        }

    except Exception as e:
        logger.error(f"LIME Logic Failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Analysis failed: {str(e)}")


# --- SHAP SPECIFIC HELPERS ---

# def generate_shap_plot(explanation_obj) -> Optional[str]:
#     """
#     Generates a SHAP waterfall plot and returns it as a Base64 string.
#     """
#     try:
#         # Create a buffer
#         buf = io.BytesIO()
        
#         # specific matplotlib config for this plot
#         plt.figure(figsize=(10, 6))
        
#         # Generate plot
#         # show=False prevents it from trying to pop up a window
#         shap.plots.waterfall(explanation_obj, show=False)
        
#         # Save to buffer
#         plt.tight_layout()
#         plt.savefig(buf, format="png", bbox_inches="tight")
#         plt.close() # Close plot to free memory
        
#         buf.seek(0)
#         img_str = base64.b64encode(buf.read()).decode("utf-8")
#         return img_str
#     except Exception as e:
#         logger.error(f"Error generating SHAP plot: {e}")
#         return None

def calculate_shap_values(automl, reference_df, instance_df, is_classification):
    """
    CPU-bound function to calculate SHAP values.
    Includes robust fallback to Numpy arrays if DataFrame column validation fails.
    """
    
    # --- 1. Sanitize Data Types ---
    # Ensure instance_df columns strictly match reference_df types
    try:
        for col in reference_df.columns:
            if col in instance_df.columns:
                # Force numeric types
                if pd.api.types.is_numeric_dtype(reference_df[col]):
                    instance_df[col] = pd.to_numeric(instance_df[col], errors='coerce')
                    if instance_df[col].isnull().any():
                         median_val = reference_df[col].median()
                         instance_df[col] = instance_df[col].fillna(median_val)
                    instance_df[col] = instance_df[col].astype(reference_df[col].dtype)
                else:
                    # Force object/string types
                    instance_df[col] = instance_df[col].astype(reference_df[col].dtype)
    except Exception as e:
        print(f"Error sanitizing types: {e}")

    # --- 2. Define Prediction Logic with Fallback ---
    # We define a helper that tries DataFrame first, then Numpy array
    def safe_predict(data):
        try:
            return automl.predict(data)
        except TypeError as te:
            if "'NoneType' object is not iterable" in str(te):
                # Fallback: Convert to numpy array to bypass sklearn column validation
                if hasattr(data, "values"):
                    return automl.predict(data.values)
            raise te
            
    def safe_predict_proba(data):
        try:
            return automl.predict_proba(data)
        except TypeError as te:
            if "'NoneType' object is not iterable" in str(te):
                if hasattr(data, "values"):
                    return automl.predict_proba(data.values)
            raise te
        except AttributeError:
             # Fallback to predict if predict_proba doesn't exist
            return safe_predict(data)

    # --- 3. Wrapper for SHAP ---
    def predict_wrapper(data):
        # Convert SHAP's numpy input back to DataFrame with correct schema
        if isinstance(data, np.ndarray):
            df_temp = pd.DataFrame(data, columns=reference_df.columns)
            # Restore types
            for col in reference_df.columns:
                if pd.api.types.is_numeric_dtype(reference_df[col]):
                    df_temp[col] = df_temp[col].astype(reference_df[col].dtype)
            data = df_temp

        if is_classification:
            return safe_predict_proba(data)
        else:
            return safe_predict(data)

    # --- 4. Prepare Background Data ---
    if reference_df.empty:
        raise ValueError("Reference dataframe is empty.")

    if len(reference_df) > 50:
        background_data = shap.utils.sample(reference_df, 50) 
    else:
        background_data = reference_df

    # --- 5. Initialize Explainer ---
    # KernelExplainer works best with the predict_wrapper logic defined above
    explainer = shap.KernelExplainer(predict_wrapper, background_data)

    # --- 6. Calculate SHAP Values ---
    shap_values = explainer.shap_values(instance_df, nsamples="auto", silent=True)

    # --- 7. Get Base Prediction ---
    # Use safe_predict to handle the initial prediction call that was crashing
    predicted_val = safe_predict(instance_df)[0]
    
    target_shap_values = None
    base_value = 0.0

    if is_classification:
        class_idx = 0 
        # Robust class index detection
        try:
            if hasattr(automl.model, 'classes_') and automl.model.classes_ is not None:
                classes_list = list(automl.model.classes_)
                try:
                    class_idx = classes_list.index(predicted_val)
                except ValueError:
                    class_idx = 1
            else:
                 class_idx = 1 if (predicted_val == 1 or str(predicted_val) == '1') else 0
        except Exception:
            class_idx = 1

        if isinstance(shap_values, list):
            if class_idx >= len(shap_values): class_idx = 0
            target_shap_values = shap_values[class_idx]
            
            # Handle list nesting
            if isinstance(target_shap_values, list): target_shap_values = target_shap_values[0]
            elif isinstance(target_shap_values, np.ndarray) and target_shap_values.ndim > 1: target_shap_values = target_shap_values[0]

            # Handle base value nesting
            exp_val = explainer.expected_value
            if isinstance(exp_val, (list, np.ndarray)):
                base_value = exp_val[class_idx] if class_idx < len(exp_val) else exp_val[0]
            else:
                base_value = exp_val
        else:
            target_shap_values = shap_values[0] if (isinstance(shap_values, np.ndarray) and shap_values.ndim > 1) else shap_values
            base_value = explainer.expected_value
    else:
        # Regression
        target_shap_values = shap_values[0] if (isinstance(shap_values, np.ndarray) and shap_values.ndim > 1) else shap_values
        base_value = explainer.expected_value

    if target_shap_values is None:
        raise ValueError("Failed to extract SHAP values")

    # --- 8. Build Explanation Object ---
    # Flatten if necessary
    if isinstance(target_shap_values, np.ndarray):
        target_shap_values = target_shap_values.flatten()
    
    explanation = shap.Explanation(
        values=target_shap_values,
        base_values=base_value,
        data=instance_df.iloc[0].values,
        feature_names=instance_df.columns.tolist()
    )
    
    return explanation, predicted_val



@router.post("/model_analysis/shap")
async def explain_with_shap(
    data: PredictRequest, 
    session: AsyncSession = Depends(get_db_async)
):
    print("--- DEBUG: API Endpoint Called ---")
    i_data = InternalSQLHelper(session)

    # 1. Fetch Model Details
    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(404, "Model not found")

    # 2. Load FLAML Model
    try:
        automl = await asyncio.to_thread(load_automl_model, model_details, data.dbname)
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise HTTPException(500, "Could not load model file")

    # 3. Load Reference Data
    try:
        sql = f"SELECT TOP 200 * FROM {model_details.table_name} ORDER BY NEWID()"
        table_details = await get_table_from_sql(client_connection_pool, sql)
        table_json, _, _ = get_table_and_status_and_columns(table_details)
        reference_df = pd.DataFrame(table_json)
        
        model_features = list(automl.model.feature_names_in_)
        reference_df = reference_df[model_features]
        
        for col in reference_df.columns:
            if pd.api.types.is_numeric_dtype(reference_df[col]):
                reference_df[col] = reference_df[col].fillna(reference_df[col].median())
            else:
                mode_val = reference_df[col].mode()
                fill_val = mode_val.iloc[0] if not mode_val.empty else "Unknown"
                reference_df[col] = reference_df[col].fillna(fill_val)
                
    except Exception as e:
        logger.error(f"SHAP Data Fetch Error: {e}")
        raise HTTPException(500, "Failed to fetch reference data")

    # 4. Prepare Instance
    user_features_dict = {f.variable: f.value for f in data.features}
    try:
        instance_df = build_model_instance(automl, reference_df, user_features_dict)
    except Exception as e:
         raise HTTPException(400, f"Error building feature instance: {str(e)}")

    # 5. Determine Mode
    is_classification = False
    try:
        _ = automl.predict_proba(instance_df)
        is_classification = True
    except:
        is_classification = False

    logger.info(f"SHAP Analysis running. Mode: {'Classification' if is_classification else 'Regression'}")

    # 6. Run SHAP (Heavy Calculation)
    try:
        explanation_obj, predicted_val = await run_in_threadpool(
            calculate_shap_values, 
            automl, 
            reference_df, 
            instance_df, 
            is_classification
        )
    except ValueError as ve:
        logger.error(f"SHAP Value Error: {ve}", exc_info=True)
        print(f"--- DEBUG: Caught ValueError: {ve}")
        raise HTTPException(400, f"Analysis Error: {str(ve)}")
    except Exception as e:
        logger.error(f"SHAP Calculation failed: {e}", exc_info=True)
        print(f"--- DEBUG: Caught Exception: {e}")
        raise HTTPException(500, f"SHAP internal calculation failed: {str(e)}")

    # 7. Generate Plot
    try:
        print("--- DEBUG: Generating Plot...")
        # plot_base64 = await run_in_threadpool(generate_shap_plot, explanation_obj)
        graph_json = await run_in_threadpool(generate_shap_plot_plotly, explanation_obj)
        print("--- DEBUG: Plot generated.")
    except Exception as e:
        print(f"--- DEBUG: Plot generation failed: {e}")
        graph_json = None

    # 8. Format Response
    shap_values_list = []
    
    try:
        print("--- DEBUG: Formatting Response...")
        feats = explanation_obj.feature_names
        vals = explanation_obj.values
        
        # --- FIX IS HERE ---
        # We use the dictionary created in Step 4 to look up values efficiently.
        # getattr(data.features...) failed because data.features is a list, not an object.
        for feat, val in zip(feats, vals):
            shap_values_list.append({
                "feature": feat,
                "shap_value": float(val) if val is not None else 0.0,
                "input_value": user_features_dict.get(feat, None) 
            })
            
    except Exception as e:
        print(f"--- DEBUG: Formatting failed: {e}")
        logger.error(f"Error formatting SHAP response: {e}")
        raise HTTPException(500, f"Error formatting analysis results: {str(e)}")

    shap_values_list.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

    pred_output = predicted_val
    if hasattr(predicted_val, 'item'):
        pred_output = predicted_val.item()
    elif isinstance(predicted_val, np.ndarray):
        pred_output = predicted_val.tolist()

    return {
        "status": "success",
        "mode": "classification" if is_classification else "regression",
        "base_value": float(explanation_obj.base_values) if explanation_obj.base_values is not None else 0.0,
        "prediction_value": pred_output,
        "shap_values": shap_values_list,
        "graph": graph_json
    }

def generate_usage_graph(usage_data: list[dict], days: int) -> str:
    """
    Generates a line chart for usage trends and returns Base64 string.
    """
    try:
        # Convert to DataFrame for easier plotting
        if not usage_data:
            return None
            
        df = pd.DataFrame(usage_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # Plot data
        ax.plot(df['date'], df['count'], marker='o', linestyle='-', color='#007bff', linewidth=2, markersize=6)
        
        # Fill area under line
        ax.fill_between(df['date'], df['count'], color='#007bff', alpha=0.1)

        # Styling
        ax.set_title(f"Model Usage - Last {days} Days", fontsize=14, pad=15)
        ax.set_xlabel("Date", fontsize=10)
        ax.set_ylabel("Request Count", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.6)
        
        # Rotate Date Labels
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Ensure integers on Y-axis (since counts can't be decimals)
        from matplotlib.ticker import MaxNLocator
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        # Save to buffer
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
        plt.close(fig) # Critical: Release memory
        
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode("utf-8")
        return img_str

    except Exception as e:
        logger.error(f"Error generating usage graph: {e}")
        # Don't crash the API if graph fails
        return None


@router.post("/model_activity/usage_over_time")
async def get_model_usage_over_time(
    data: ModelUsageRequest,
    session: AsyncSession = Depends(get_db_async)
):
    """
    Returns the daily usage count for a specific model over the last X days.
    """
    i_data = InternalSQLHelper(session)
    
    # 1. Verify Model Exists
    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(status_code=404, detail="Model not found")

    try:
        # 2. Query the Logs Table
        # We group by the date part of 'created_on'
        sql = text("""
            SELECT 
                FORMAT(created_on, 'yyyy-MM-dd') as date_str,
                COUNT(*) as usage_count
            FROM [IOD_TRANSACTIONS].[applicationLogs].[model_prediction_logs]
            WHERE model_id = :model_id
              AND created_on >= DATEADD(day, -:days, GETDATE())
            GROUP BY FORMAT(created_on, 'yyyy-MM-dd')
            ORDER BY date_str ASC
        """)
        
        result = await session.execute(sql, {"model_id": data.model_id, "days": data.days})
        rows = result.fetchall()
        
    # 3. Process Data (Fill Missing Dates with 0)
        # Convert SQL result to Dict for easy lookup
        data_map = {row[0]: row[1] for row in rows}
        
        # Generate full list of dates for the last X days
        end_date = datetime.now()
        print("end_date:", end_date)
        start_date = end_date - timedelta(days=data.days - 1)
        print("start_date:", start_date)
        
        # Create a complete list of dates using Pandas to handle gaps
        date_range = pd.date_range(start=start_date, end=end_date)
        
        usage_trend_complete = []
        for dt in date_range:
            date_str = dt.strftime('%Y-%m-%d')
            count = data_map.get(date_str, 0) # Get count or 0 if date missing in SQL
            usage_trend_complete.append({"date": date_str, "count": count})

        total_calls = sum(item['count'] for item in usage_trend_complete)

        # # 4. Generate Graph (Run in Threadpool to avoid blocking)
        # graph_base64 = await run_in_threadpool(
        #     generate_usage_graph, 
        #     usage_trend_complete, 
        #     data.days
        # )

        def generate_graph_wrapper(data_list):
            if not data_list: return None
            
            # Prepare DataFrame
            df = pd.DataFrame(data_list)
            # Ensure date column is datetime objects (as required by get_2d_line_chart logic for dticks)
            df['date'] = pd.to_datetime(df['date'])
            
            # Call existing function
            fig = get_2d_line_chart(
                df=df, 
                num_cols=['count'], 
                date_cols=['date'], 
                draw_area=True # Enable area fill
            )
            
            # Update title/layout specific to this view if needed
            # fig.update_layout(title_text=f"Model Usage - Last {data.days} Days")
            graph_title = f"Model Usage - Last {data.days} Days"
            fig.update_layout(
                    template="simple_white",
                    margin=dict(l=20, r=20, b=0, t=0, pad=0),
                    height=350,
                    font=dict(
                        family="open sans, Helvetica Neue, Helvetica, Arial, sans-serif",
                    ),
                    # yaxis=dict(tickformat="d"),
                    title=dict(
                        text=graph_title,
                        x=0,
                        y=0.96,
                        font_color="#1E78B4",
                        xanchor="left",
                        font_size=2,
                        font_weight=800
                    ),
                    legend_grouptitlefont=dict(
                        size=12.8,
                        weight=600
                    ),
                    legend=dict(
                        orientation="h",
                        xref="container",
                        yref="container",
                        yanchor="auto",
                        xanchor="auto",
                        font_size=12,
                        font_weight=400
                    ),
                    xaxis_title=dict(
                        font_size=12.8,
                        font_weight=400
                    ),
                    yaxis_title=dict(
                        font_size=12.8,
                        font_weight=400
                    ),
                    barcornerradius="5%",
                    bargroupgap=0.2
                )
            fig.update_xaxes(tickfont=dict(size=12))
            fig.update_yaxes(tickfont=dict(size=12))


            # Return JSON
            # return json.loads(fig.to_json())
            return fig.to_json()
        
        graph_json = await run_in_threadpool(generate_graph_wrapper, usage_trend_complete)

        return {
            "status": "success",
            "model_id": data.model_id,
            "period_days": data.days,
            "total_calls": total_calls,
            "usage_trend": usage_trend_complete, # Now includes dates with 0 counts
            "graph": graph_json
        }

    except Exception as e:
        logger.error(f"Error fetching usage analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch usage analytics")


# def generate_distribution_graph(bins: list, counts: list) -> str:
#     """
#     Generates a bar chart for inference time distribution.
#     """
#     try:
#         if len(counts) == 0:
#             return None

#         # Create figure
#         fig, ax = plt.subplots(figsize=(10, 5))
        
#         # Create X-axis labels from bins (e.g., "0-50", "50-100")
#         bin_labels = [f"{int(bins[i])}-{int(bins[i+1])}" for i in range(len(bins)-1)]
        
#         # Plot Bar Chart
#         bars = ax.bar(bin_labels, counts, color='#28a745', alpha=0.7, edgecolor='black')
        
#         # Add labels on top of bars
#         ax.bar_label(bars, padding=3)

#         # Styling
#         ax.set_title("Inference Time Distribution (ms)", fontsize=14, pad=15)
#         ax.set_xlabel("Time Range (ms)", fontsize=10)
#         ax.set_ylabel("Frequency (Count)", fontsize=10)
#         ax.grid(axis='y', linestyle='--', alpha=0.6)
        
#         # Rotate labels if there are many bins
#         plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

#         # Save to buffer
#         buf = io.BytesIO()
#         plt.tight_layout()
#         plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
#         plt.close(fig) 
        
#         buf.seek(0)
#         img_str = base64.b64encode(buf.read()).decode("utf-8")
#         return img_str

#     except Exception as e:
#         logger.error(f"Error generating distribution graph: {e}")
#         return None
    

# @router.post("/model_activity/inference_distribution")
# async def get_inference_distribution(
#     data: ModelUsageRequest,
#     session: AsyncSession = Depends(get_db_async)
# ):
#     """
#     Returns statistics and a histogram of inference times for a model.
#     """
#     i_data = InternalSQLHelper(session)
    
#     # 1. Verify Model
#     model_details = await i_data.get_model_details_from_id(data.model_id)
#     if not model_details:
#         raise HTTPException(status_code=404, detail="Model not found")

#     try:
#         # 2. Query Raw Execution Times
#         # We need individual records to calculate percentiles and histogram
#         sql = text("""
#             SELECT execution_time_ms
#             FROM [IOD_TRANSACTIONS].[applicationLogs].[model_prediction_logs]
#             WHERE model_id = :model_id
#               AND created_on >= DATEADD(day, -:days, GETDATE())
#               AND execution_time_ms IS NOT NULL
#         """)
        
#         result = await session.execute(sql, {"model_id": data.model_id, "days": data.days})
#         # Extract list of floats [120.5, 45.2, ...]
#         times = [row[0] for row in result.fetchall()]
        
#         if not times:
#             return {
#                 "status": "success",
#                 "message": "No data available for this period",
#                 "stats": {},
#                 "distribution": [],
#                 "graph_base64": None
#             }

#         # 3. Processing with Pandas/Numpy
#         df = pd.DataFrame(times, columns=['ms'])
        
#         # Calculate Key Stats
#         stats = {
#             "count": int(df['ms'].count()),
#             "min_ms": round(float(df['ms'].min()), 2),
#             "max_ms": round(float(df['ms'].max()), 2),
#             "avg_ms": round(float(df['ms'].mean()), 2),
#             "p50_median_ms": round(float(df['ms'].quantile(0.5)), 2),
#             "p95_ms": round(float(df['ms'].quantile(0.95)), 2), # 95% of requests are faster than this
#             "p99_ms": round(float(df['ms'].quantile(0.99)), 2)
#         }

#         # 4. Create Histogram Data
#         # We use numpy to automatically calculate bin edges
#         # We limit outliers for the graph by clipping at P99 for better visualization logic if needed,
#         # but here we'll use the raw data with auto-bins.
#         hist_counts, bin_edges = np.histogram(times, bins=10) 

#         distribution_data = []
#         for i in range(len(hist_counts)):
#             distribution_data.append({
#                 "range_start": float(bin_edges[i]),
#                 "range_end": float(bin_edges[i+1]),
#                 "label": f"{int(bin_edges[i])}-{int(bin_edges[i+1])}",
#                 "count": int(hist_counts[i])
#             })

#         # 5. Generate Graph
#         graph_base64 = await run_in_threadpool(
#             generate_distribution_graph, 
#             bin_edges, 
#             hist_counts
#         )

#         return {
#             "status": "success",
#             "model_id": data.model_id,
#             "period_days": data.days,
#             "statistics": stats,
#             "distribution": distribution_data,
#             "graph_base64": graph_base64
#         }

#     except Exception as e:
#         logger.error(f"Error fetching inference distribution: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to calculate distribution")


# def generate_distribution_graph(bins: list, counts: list) -> str:
#     """
#     Generates a bar chart for inference time distribution in Seconds.
#     """
#     try:
#         if len(counts) == 0:
#             return None

#         # Create figure
#         fig, ax = plt.subplots(figsize=(10, 5))
        
#         # Create X-axis labels from bins (formatted to 2 decimal places)
#         # e.g., "0.05-0.10"
#         bin_labels = [f"{bins[i]:.2f}-{bins[i+1]:.2f}" for i in range(len(bins)-1)]
        
#         # Plot Bar Chart
#         bars = ax.bar(bin_labels, counts, color='#28a745', alpha=0.7, edgecolor='black')
        
#         # Add labels on top of bars
#         ax.bar_label(bars, padding=3)

#         # Styling
#         ax.set_title("Inference Time Distribution (Seconds)", fontsize=14, pad=15)
#         ax.set_xlabel("Time Range (s)", fontsize=10)
#         ax.set_ylabel("Frequency (Count)", fontsize=10)
#         ax.grid(axis='y', linestyle='--', alpha=0.6)
        
#         # Rotate labels for readability
#         plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

#         # Save to buffer
#         buf = io.BytesIO()
#         plt.tight_layout()
#         plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
#         plt.close(fig) 
        
#         buf.seek(0)
#         img_str = base64.b64encode(buf.read()).decode("utf-8")
#         return img_str

#     except Exception as e:
#         logger.error(f"Error generating distribution graph: {e}")
#         return None
    

@router.post("/model_activity/inference_distribution")
async def get_inference_distribution(
    data: ModelUsageRequest,
    session: AsyncSession = Depends(get_db_async)
):
    """
    Returns statistics and a histogram of inference times (in Seconds) for a model.
    """
    i_data = InternalSQLHelper(session)
    
    # 1. Verify Model
    model_details = await i_data.get_model_details_from_id(data.model_id)
    if not model_details:
        raise HTTPException(status_code=404, detail="Model not found")

    try:
        # 2. Query Raw Execution Times (Stored as MS in DB)
        sql = text("""
            SELECT execution_time_ms
            FROM [IOD_TRANSACTIONS].[applicationLogs].[model_prediction_logs]
            WHERE model_id = :model_id
              AND created_on >= DATEADD(day, -:days, GETDATE())
              AND execution_time_ms IS NOT NULL
        """)
        
        result = await session.execute(sql, {"model_id": data.model_id, "days": data.days})
        times_ms = [row[0] for row in result.fetchall()]
        
        if not times_ms:
            return {
                "status": "success",
                "message": "No data available for this period",
                "stats": {},
                "distribution": [],
                "graph": None
            }

        # 3. Convert to Seconds
        df_raw = pd.DataFrame(times_ms, columns=['ms'])
        df_raw['sec'] = df_raw['ms'] / 1000.0  # <--- Conversion here
        
        # 4. Calculate Key Stats (in Seconds)
        # Using 3 or 4 decimal places is better for fast inference
        stats = {
            "count": int(df_raw['sec'].count()),
            "min_sec": round(float(df_raw['sec'].min()), 4),
            "max_sec": round(float(df_raw['sec'].max()), 4),
            "avg_sec": round(float(df_raw['sec'].mean()), 4),
            "p50_median_sec": round(float(df_raw['sec'].quantile(0.5)), 4),
            "p95_sec": round(float(df_raw['sec'].quantile(0.95)), 4),
            "p99_sec": round(float(df_raw['sec'].quantile(0.99)), 4)
        }

        # 5. Create Histogram Data (on Seconds column)
        # Bins=10 creates 10 bars
        # hist_counts, bin_edges = np.histogram(df['sec'], bins=10) 

        # distribution_data = []
        # for i in range(len(hist_counts)):
        #     distribution_data.append({
        #         "range_start": float(bin_edges[i]),
        #         "range_end": float(bin_edges[i+1]),
        #         "label": f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}s",
        #         "count": int(hist_counts[i])
        #     })

        def generate_dist_graph_wrapper(series_data):
            # Create Histogram Buckets
            hist_counts, bin_edges = np.histogram(series_data, bins=10)
            
            # Prepare DataFrame for get_2d_bar_chart
            # It expects columns for X (Category) and Y (Number)
            chart_data = []
            for i in range(len(hist_counts)):
                label = f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}s"
                chart_data.append({"Range": label, "Count": int(hist_counts[i])})
            
            df_chart = pd.DataFrame(chart_data)
            
            # Call existing function
            fig = get_2d_bar_chart(
                df=df_chart,
                num_cols=['Count'],     # Y-axis
                cat_cols=['Range'],     # X-axis
                orientation='v'
            )
            
            # Custom updates
            # fig.update_layout(
            #     title_text="Inference Time Distribution",
            #     xaxis_title="Time Range (s)"
            # )

            graph_title = "Inference Time Distribution"
            fig.update_layout(
                    template="simple_white",
                    margin=dict(l=20, r=20, b=0, t=0, pad=0),
                    height=350,
                    font=dict(
                        family="open sans, Helvetica Neue, Helvetica, Arial, sans-serif",
                    ),
                    # yaxis=dict(tickformat="d"),
                    title=dict(
                        text=graph_title,
                        x=0,
                        y=0.96,
                        font_color="#1E78B4",
                        xanchor="left",
                        font_size=2,
                        font_weight=800
                    ),
                    legend_grouptitlefont=dict(
                        size=12.8,
                        weight=600
                    ),
                    legend=dict(
                        orientation="h",
                        xref="container",
                        yref="container",
                        yanchor="auto",
                        xanchor="auto",
                        font_size=12,
                        font_weight=400
                    ),
                    xaxis_title=dict(
                        font_size=12.8,
                        font_weight=400,
                        text="Time Range (s)"
                    ),
                    yaxis_title=dict(
                        font_size=12.8,
                        font_weight=400
                    ),
                    barcornerradius="5%",
                    bargroupgap=0.2
                )
            fig.update_xaxes(tickfont=dict(size=12))
            fig.update_yaxes(tickfont=dict(size=12))
            return fig.to_json()
            # return json.loads(fig.to_json())

        graph_json = await run_in_threadpool(generate_dist_graph_wrapper, df_raw['sec'])

        # # 6. Generate Graph
        # graph_base64 = await run_in_threadpool(
        #     generate_distribution_graph, 
        #     bin_edges, 
        #     hist_counts
        # )

        return {
            "status": "success",
            "model_id": data.model_id,
            "period_days": data.days,
            "statistics": stats,
            # "distribution": distribution_data,
            "graph": graph_json
        }

    except Exception as e:
        logger.error(f"Error fetching inference distribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate distribution")


# @router.post("/models/active")
# async def delete_model():
#     """Delete active model"""
#     if ACTIVE_MODEL_PATH.exists():
#         loop = asyncio.get_event_loop()
#         await loop.run_in_executor(None, ACTIVE_MODEL_PATH.unlink)
#         return {"message": "Active model deleted"}
#     raise HTTPException(status_code=404, detail="No active model found")
