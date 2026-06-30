# Dashboards Component

## Overview

Generates **automated business intelligence dashboards** in three modes:
- **Auto Dashboards**: Pre-configured queries executed automatically
- **Custom Dashboards**: LLM-generated queries from user questions
- **Introduction Pages**: Database overview with table statistics

**Tech**: LLM SQL Generation + Parallel Query Execution + Graph Generation

## What It Does

- ✅ Execute pre-configured dashboard SQL queries
- ✅ Generate visualizations (charts) for each query
- ✅ Create custom dashboards from natural language
- ✅ Generate introduction pages with schema overview
- ✅ Separate KPI views from analytical views
- ✅ Store results in MongoDB with metadata

---

## Folder Structure

```
app/core/dashboards/
├── custom_dashboard.py     # LLM-based custom dashboard generation
├── introductions.py        # Database introduction page builder
└── [other utilities]

app/routers/dashboards.py   # API endpoints
```

---

## How It Works

### **Auto Dashboard**

```
1. Load Configuration
   - Fetch pre-configured SQL queries for database
   ↓
2. Execute Queries in Parallel
   - Run all dashboard queries simultaneously
   - Limit to 500 rows per query
   ↓
3. Generate Graphs
   - Plotly or ECharts (configured per database)
   - One graph per query result
   ↓
4. Store Results
   - Save tables + graphs to MongoDB
   - Track by transaction_id
   ↓
5. Return Combined Results
   Returns: Array of {sql, table, graph, columns}
```

### **Custom Dashboard**

```
1. Load LLM Config & Schema
   - Database schema from schema_strings/
   - LLM model from clientConfig.yaml
   ↓
2. Call LLM to Generate SQL
   - Generates 2-4 related queries
   - Classifies: KPI view vs Analytical view
   ↓
3. Execute All Queries
   - In parallel on client database
   ↓
4. Generate Visualizations
   - KPI cards: Show metrics + growth
   - Analytical: Chart full results
   ↓
5. Return Organized Results
   Returns: KPI views + Analytical views (each with chart)
```

### **Introduction Page**

```
1. Extract Schema Metadata
   - Identify column types: identity, datetime, numeric, categorical
   ↓
2. Generate Statistics Queries
   - Distinct count (categorical)
   - Min/max ranges (numeric)
   - Top 3 values (for preview)
   ↓
3. Execute Stats Queries
   - Get actual column statistics
   ↓
4. Format for Display
   - Create metadata mapping
   - Group statistics by column type
   ↓
5. Return Overview
   Returns: Table summaries + column metadata
```
---

### **Other Endpoints**

```
POST /egai/getLastRefreshDate
     Get when database was last updated

POST /egai/hpe_custom_dashboard
     Render introduction page with live data

POST /egai/navigation/dashboardToConversation
     Link dashboard result to chat conversation
```

## Dashboard Types

### **Auto Dashboard** (Pre-configured)
- Executed from stored SQL queries
- Consistent, fast, reliable
- Good for standard reporting
- No LLM involved

### **Custom Dashboard** (LLM-generated)
- Created from natural language
- Flexible, exploratory
- Separates KPI views from analytical views
- One LLM call per user question

### **Introduction Page** (Schema overview)
- Shows available tables and columns
- Provides statistics and value ranges
- Helps users understand data
- No complex SQL, just metadata

---

## Storage

Results stored in MongoDB:

```
Document: Transaction/Dashboard Result
├─ query_key: "uuid"
├─ table: [rows...]
├─ graphs: [chart_objects...]
├─ metadata: {columns, types, row_count}
└─ created_at: timestamp
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No charts generated | Check GRAPH_TYPE in config (echarts or plotly) |
| Custom dashboard queries fail | Schema may be incomplete; check schema_strings folder |
| Slow dashboard load | Too many rows? Auto-dashboard limits to 500 per query |
| Introduction page missing tables | Ensure database schema is properly configured |
| LLM generates wrong SQL | Provide more context in custom query or adjust prompt |

---

