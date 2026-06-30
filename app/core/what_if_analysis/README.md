# What-If Analysis Component

## Overview

Enables **predictive modeling & scenario analysis** using AutoML. Train models on business data, make predictions with custom values, analyze feature importance, and explain predictions with LIME and SHAP.

**Tech**: FLAML AutoML + LIME + SHAP + XGBoost/LightGBM

## What It Does

- ✅ Train predictive models automatically on any dataset
- ✅ Make predictions with custom feature values
- ✅ Analyze which features drive predictions (importance)
- ✅ Explain predictions locally (LIME) and globally (SHAP)
- ✅ Track model usage over time
- ✅ Store versioned models with metadata

---

## Folder Structure

```
app/core/what_if_analysis/
├── model_training.py       # Empty (logic in router)
└── temp_data/              # Parquet cache for training data

app/routers/whatIfAnalysis.py  # Main API (all endpoints + business logic)
models/
├── {dbname}/versioned_models/  # Experimental models
└── {dbname}/final_models/      # Approved models
```

---

## How It Works

### **Training Models**

```
1. Select Data
   - Pick dataset/table from available options
   - Choose target column to predict
   ↓
2. Submit Training Request
   - System loads up to 10k rows
   - Caches as Parquet file
   ↓
3. AutoML Training (Background)
   - Detects: regression or classification
   - Tries: LightGBM, XGBoost, CatBoost, RandomForest, ExtraTrees
   - Keeps best model by score (RMSE or Accuracy)
   ↓
4. Check Status
   - Monitor progress, best score
   ↓
5. Finalize
   - Approve best model as final
   ↓
Stored: models/{dbname}/final_models/model__[name]__v[version].pkl
```

### **Making Predictions**

```
1. Load Feature Defaults
   - Get median/mode for each feature
   - Cached in Redis (7 days)
   ↓
2. Customize Features
   - Override defaults with custom values
   ↓
3. Predict
   - Align input DataFrame with training features
   - Model predicts using aligned features
   ↓
4. Log Activity
   - Track prediction timestamp & user
   ↓
Returns: Prediction value + model metadata
```

### **Explaining Predictions**

```
LIME Explanation:
├─ Shows which features supported/opposed prediction
├─ Local interpretability for this specific case
└─ Returns: Weights for each feature + bar chart

SHAP Analysis:
├─ Shows feature impact on prediction
├─ Base value + feature contributions = prediction
├─ Top 10 features in waterfall format
└─ Returns: Base value + contributions + waterfall chart
```

---

## API Endpoints

### **Model Management**

| Endpoint | Input | Output |
|----------|-------|--------|
| GET `/egai/model_registry/get_models` | dbname | All trained models metadata |
| GET `/egai/model_training/available_datasets` | — | List of configured datasets |
| GET `/egai/model_training/available_tables` | dbname | Tables in dataset |
| GET `/egai/model_training/available_columns` | dbname, table | Columns in table |

### **Training**

| Endpoint | Input | Output |
|----------|-------|--------|
| POST `/egai/model_training/train_model` | dbname, table, target_col | job_id, status: "queued" |
| POST `/egai/model_training/check_training_status` | job_id | status, progress, best_score |
| POST `/egai/model_training/finalize_model` | dbname, table, target_col, version | Model marked final |

### **Predictions**

| Endpoint | Input | Output |
|----------|-------|--------|
| POST `/egai/model_predictions/get_base_feature_values` | model_id | Feature defaults (median/mode) |
| POST `/egai/model_predictions/predict` | model_id, features: [{"variable": "...", "value": ...}] | prediction: [value] |

### **Analysis**

| Endpoint | Explains | Output |
|----------|----------|--------|
| POST `/egai/model_analysis/feature_importance` | Which features matter most | Importance %% for each feature |
| POST `/egai/model_analysis/lime` | Local case explanation | Feature weights + bar chart |
| POST `/egai/model_analysis/shap` | Feature contributions | Base value + contributions + waterfall |
| POST `/egai/model_analysis/usage_over_time` | Model usage trends | Calls/day over N days + line chart |

---

## Example: Train & Predict

```
Step 1: Available Datasets
GET /egai/model_training/available_datasets
Response: ["lenovo", "adf", "cx_customer_experience"]

Step 2: Available Tables
GET /egai/model_training/available_tables
Params: dbname="lenovo"
Response: ["Lenovo_data_revised", "Sales_Forecast", "Customer_Insights"]

Step 3: Available Columns
GET /egai/model_training/available_columns
Params: dbname="lenovo", table_name="Lenovo_data_revised"
Response: ["age", "income", "credit_score", "purchase_amount", ...]

Step 4: Train Model
POST /egai/model_training/train_model
Body: {
  "user_name": "john smith",
  "dbname": "lenovo",
  "table_name": "Lenovo_data_revised",
  "target_column": "revenue",
  "fields_to_exclude": ["internal_id"]
}
Response: {"job_id": "abc123", "status": "queued"}

Step 5: Check Status (poll)
POST /egai/model_training/check_training_status
Body: {"job_id": "abc123"}
Response: {
  "status": "completed",
  "progress": "Training completed",
  "best_score": 0.92
}

Step 6: Get Defaults
POST /egai/model_predictions/get_base_feature_values
Body: {"user_name": "john smith", "dbname": "lenovo", "model_id": 1}
Response: ["age": 35, "income": 50000, "credit_score": 700]

Step 7: Make Prediction
POST /egai/model_predictions/predict
Body: {
  "user_name": "john smith",
  "dbname": "lenovo",
  "model_id": 1,
  "features": [
    {"variable": "age", "value": 40},
    {"variable": "income", "value": 75000},
    {"variable": "credit_score", "value": 750}
  ]
}
Response: {
  "model_config": {"best_estimator": "lgbm", "best_score": 0.92},
  "prediction": [48.35]
}

Step 8: Explain Prediction (SHAP)
POST /egai/model_analysis/shap
[Same body as predict]
Response: {
  "status": "success",
  "mode": "regression",
  "base_value": 40.5,
  "prediction_value": 48.35,
  "shap_values": [
    {"feature": "income", "shap_value": 5.2, "input_value": 75000},
    {"feature": "credit_score", "shap_value": 2.1, "input_value": 750},
    {"feature": "age", "shap_value": 0.55, "input_value": 40}
  ],
  "graph": "{...Waterfall chart JSON...}"
}
```

---

## What Models Are Trained

**AutoML selects best from:**
- LightGBM (fast, accurate)
- XGBoost (powerful)
- CatBoost (categorical features)
- RandomForest (ensemble)
- ExtraTrees (extra randomness)

**For regression tasks:**
- Metric: RMSE (Root Mean Squared Error)
- Data split: 80% train, 20% validation

**For classification tasks:**
- Metric: Accuracy
- Data split: 80% train, 20% validation

---

## Understanding Explanations

### **Feature Importance**
Shows raw importance values (sum = 1.0):
```
income:        0.45 (45%)  ← Most important
credit_score:  0.30 (30%)
age:           0.25 (25%)  ← Least important
```

### **LIME (Local Explanation)**
Explains *this single* prediction:
```
Base prediction: 40.5

Feature weights:
  income_high (+0.32)   ← Increased prediction
  age_25_35   (+0.15)
  debt_ratio  (-0.08)   ← Decreased prediction

Final prediction: 48.35
```

### **SHAP (Global + Local)**
Shows contribution from each feature:
```
Base value:      40.5 (expected)
  + income:      +5.2 (75000 pushed up)
  + credit_score: +2.1 (750 pushed up)  
  + age:         +0.55 (40 pushed up)
= Prediction:    48.35
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Training takes very long | Reduce dataset size or exclude non-predictive columns |
| Model accuracy too low | Add more data, check for missing values, validate target column |
| Feature importance all zero | Features may not correlate with target; check data quality |
| Prediction fails | Ensure features match training columns exactly |
| LIME/SHAP returns empty | Issue with encoding non-numeric features; check data types |
| Slow predictions | Redis cache may be cold; first prediction after cache expire is slower |
| Job lost on restart | Jobs stored in memory only; retrain after restart |

---

