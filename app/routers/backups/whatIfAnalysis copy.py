from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
    PredictionFeatureRequest
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases.connections import (
    client_connection_pool,
    get_db_async,
    get_redis_client,
)
from app.databases.internal_sql_operations import InternalSQLHelper
import uuid
import yaml
from typing import Dict, Any
from app.core.caching import cache_data, get_cached_data
from app.core.table_from_sql import get_table_from_sql
import pandas as pd
from app.core.helper import make_json_safe, bson_to_json_safe, correct_columns_name, get_table_and_status_and_columns
import asyncio
from datetime import datetime
from sklearn.model_selection import train_test_split
from flaml import AutoML
import joblib
from pydantic import ConfigDict 
import shutil


router = APIRouter(prefix="/egai", tags=["What If - Analysis"])

logger = get_logger()


MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)
MAX_JOBS_HISTORY = 5
TRAINING_JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = asyncio.Lock() 


class JobDetails(TrainModelRequest):
    job_id: str
    session: AsyncSession
    df: pd.DataFrame

    model_config = ConfigDict(arbitrary_types_allowed=True)


# MODEL REGISTRY

@router.post("/model_registry/get_models")
async def get_all_models(    
    data: ResetChat, 
    session: AsyncSession = Depends(get_db_async)
):
    i_data = InternalSQLHelper(session)

    ml_model_details = await i_data.get_all_models()

    for mld in ml_model_details:
        mld.model_details = json.loads(mld.model_details)

    return ml_model_details


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


@router.post("/model_training//train_model", status_code=201)
async def train_model(
    data: TrainModelRequest, 
    bg_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_async)
):
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

    df = df.iloc[:100] # TO BE REOMVED AFTER TESTING

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
            "estimator_list": ["lgbm", "xgboost"],
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
    session: AsyncSession = Depends(get_db_async)
):
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

    features_in_model = list(automl.model.feature_names_in_)

    df = pd.read_parquet("app/core/what_if_analysis/temp_data/Lenovo_data_revised.parquet")
    df_describe = df.describe(include="all")
    df_describe = df_describe.fillna("XXXX")

    feature_value_mappings = []
    for c in df.columns:
        if c in features_in_model:
            if df_describe[c]["50%"] == "XXXX":
                feature_value_mappings.append({
                    "variable": c,
                    "value": df_describe[c]["top"]
                })
            else:
                feature_value_mappings.append({
                    "variable": c,
                    "value": df_describe[c]["50%"]
                })
    
    return feature_value_mappings


@router.post("/model_predictions/predict")
async def predict_value_from_provided_feature_values(
    data: PredictRequest,
    session: AsyncSession = Depends(get_db_async)
):
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

    model_details.model_details = json.loads(model_details.model_details) 

    return {
        "model_config": model_details,
        "prediction": predictions.tolist()
    }

# @router.post("/models/active")
# async def delete_model():
#     """Delete active model"""
#     if ACTIVE_MODEL_PATH.exists():
#         loop = asyncio.get_event_loop()
#         await loop.run_in_executor(None, ACTIVE_MODEL_PATH.unlink)
#         return {"message": "Active model deleted"}
#     raise HTTPException(status_code=404, detail="No active model found")
