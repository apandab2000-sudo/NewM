# Report Builder Component

## Overview

**LLM-driven component engine** that transforms natural language queries into dynamic report visualizations. Uses intelligent routing to decide component types, Text2SQL for queries, and LLM-generated insights.

**Tech**: LLM Routing + Text2SQL + ECharts + Dynamic Component Generation

## What It Does

- ✅ Convert plain English description to report components
- ✅ Automatically route to best component type (graph, KPI, table, insights, etc.)
- ✅ Generate SQL automatically from natural language
- ✅ Create visualizations (bar, line, pie, etc.)
- ✅ Calculate metrics (growth %, sparklines)
- ✅ Generate AI-written insights from data
- ✅ Store report components with full state history

---

## Folder Structure

```
app/core/report_builder/
├── report_component.py    # Component processing logic

app/routers/report_builder.py  # API endpoints (main logic)
```

---

## How It Works

```
User: "Show top 10 products by revenue"
  ↓
1. Route Component Type
   - LLM analyzes query
   - Determines: graph vs table vs KPI vs insights
   ↓
2. Generate SQL
   - Text2SQL converts NL to SQL
   - Validates against database schema
   ↓
3. Execute Query
   - Runs on client database
   - Returns raw data rows
   ↓
4. Component-Specific Processing
   - Graph: Generate ECharts JSON
   - KPI: Calculate growth %, sparkline
   - Table: Format columns
   - Insights: LLM analyzes data
   ↓
5. Save State
   - Store in component_transactions table
   - Track component_state_id, metadata
   ↓
6. Return to User
   Returns: SQL + data + visualization + metadata
```

---

## API Endpoints

### **Report Management**

```
POST   /egai/report_builder/v1/reports
       Create new report

GET    /egai/report_builder/v1/reports?dbname=X&user_name=X
       List all user's reports

GET    /egai/report_builder/v1/reports/{report_id}?dbname=X&user_name=X
       Get report details

PUT    /egai/report_builder/v1/reports
       Update report name/description

DELETE /egai/report_builder/v1/reports/{report_id}
       Delete report
```

### **Component Management**

```
POST   /egai/report_builder/v1/reports/components
       Create new component in report

GET    /egai/report_builder/v1/reports/{report_id}/components
       List all components in report

POST   /egai/report_builder/v1/reports/components/update  [MAIN LOGIC]
       Update component (executes query, generates output)

DELETE /egai/report_builder/v1/reports/components/{component_id}
       Delete component
```

---

## Component Types

### **1. Table**
Just the raw data table
```json
{
  "component_type": "table",
  "component_output": {
    "sql": "SELECT col1, col2 FROM table",
    "table": [{"col1": "val1", "col2": "val2"}, ...],
    "table_columns": ["col1", "col2"]
  }
}
```

### **2. Graph**
ECharts visualization
```json
{
  "component_type": "graph",
  "component_output": {
    "sql": "SELECT product, revenue ...",
    "table": [{"product": "A", "revenue": 150000}, ...],
    "graph": [{"type": "bar", "data": {...}}],
    "graph_title": "Top Products by Revenue"
  }
}
```

### **3. KPI Card**
Single metric with growth
```json
{
  "component_type": "kpi_card",
  "component_output": {
    "title": "Total Revenue",
    "value": 125450.75,
    "previous_value": 100000.00,
    "growth_percentage": 25.45,      # ((current - prev) / prev) * 100
    "growth_status": "up",           # "up" or "down"
    "sparkline": [95000, 98000, ..., 125450.75]  # Last 10 data points
  }
}
```

### **4. SmartArt**
Visual list/process/hierarchy
```json
{
  "component_type": "smartart",
  "component_output": {
    "title": "Customer Segments",
    "style": "list",   # or process, hierarchy, cycle
    "items": [
      {"label": "Premium", "description": "High-value"},
      {"label": "Standard", "description": "Regular"}
    ],
    "count": 2
  }
}
```

### **5. Insights**
AI-generated summary
```json
{
  "component_type": "insights",
  "component_output": {
    "sql": "SELECT ...",
    "table": [...],
    "insights": {
      "summary": "Revenue increased 25% this quarter, driven by..."
    }
  }
}
```

### **6. Paragraph**
AI-written narrative text
```json
{
  "component_type": "paragraph",
  "component_output": {
    "summary": "Sales showed strong growth in Q4 with..."
  }
}
```

### **7. Metric Grid**
Multiple KPIs in one view
```json
{
  "component_type": "metric_grid",
  "component_output": {
    "metrics": [
      {"title": "Revenue", "value": 125450},
      {"title": "Orders", "value": 1542},
      {"title": "Avg Order Value", "value": 81.35}
    ]
  }
}
```

### **8. Header**
Report title section
```json
{
  "component_type": "header",
  "component_output": {
    "title": "Sales Report Q4 2025",
    "subtitle": "Monthly Performance Analysis"
  }
}
```

---

## Example: Create & Update Component

```
Step 1: Create Report
POST /egai/report_builder/v1/reports
{
  "user_name": "john smith",
  "dbname": "lenovo",
  "report_name": "Q4 Sales Analysis",
  "report_description": "Sales metrics and trends"
}
Response: {"report_id": 1, "name": "Q4 Sales Analysis"}

Step 2: Add Component
POST /egai/report_builder/v1/reports/components
{
  "user_name": "john smith",
  "dbname": "lenovo",
  "report_id": 1,
  "component_name": "Top Products",
  "component_description": "Best performing products"
}
Response: {"component_id": 101}

Step 3: Update Component (Generate Output)
POST /egai/report_builder/v1/reports/components/update
{
  "user_name": "john smith",
  "dbname": "lenovo",
  "report_id": 1,
  "component_id": 101,
  "query": "Show top 10 products by revenue",
  "component_metadata": {
    "component_type": "graph",
    "title": "Top Products by Revenue",
    "x_axis": "product_name",
    "y_axis": "revenue"
  }
}
Response:
{
  "component_id": 101,
  "component_type": "graph",
  "component_output": {
    "sql": "SELECT product_name AS product_name, revenue FROM products ORDER BY revenue DESC LIMIT 10",
    "table": [
      {"product_name": "Product A", "revenue": 150000},
      {"product_name": "Product B", "revenue": 120000}
    ],
    "graph": [{"type": "bar", "data": {...}}],
    "graph_title": "Top Products by Revenue"
  }
}
```

## How Components Are Generated

### **1. LLM Routing**
- Analyzes query: "Show top 10 products by revenue"
- Suggests: component_type = "graph", title = "Top Products by Revenue"
- Returns metadata with visualization hints

### **2. SQL Generation**
- Text2SQL converts query to SQL
- Validates against database schema
- Returns executable SQL

### **3. Data Execution**
- Runs SQL against client database
- Returns result rows

### **4. Component Processing**
- **Graph**: ECharts library generates visualization
- **KPI**: Calculates growth % and sparkline
- **Insights**: LLM analyzes table and writes summary
- **SmartArt**: Transforms rows to styled items
- **Paragraph**: LLM writes narrative from data

---

## Storage

Component state persists in SQL database:

```
Table: component_transactions
├─ component_state_id      (auto-incremented)
├─ query                   (user question)
├─ table_details JSON      (schema, columns, row count)
├─ graph_details JSON      (chart type, title, axes)
├─ insights_details JSON   (summary, analysis)
└─ created_at              (timestamp)
```

Each update creates new state record (no overwrite).

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Awaiting human input" status | Query is ambiguous; provide more context or specify columns |
| Empty graph | Check data has at least 2 dimensions; ensure SQL returns rows |
| Wrong metric in KPI | Specify column name explicitly in query |
| Insights are generic | Add more context about business goals |
| Slow component generation | Too much data? Add LIMIT or filters to query |
| SQL error | Check table/column names against schema |

---

## Dependencies

```
fastapi>=0.95.0            # API framework
sqlalchemy>=2.0.48         # ORM + async DB
pandas>=2.3.3              # Data transformation
openai>=2.26.0             # LLM (configurable provider)
plotly>=5.0.0              # ECharts generation
pydantic>=2.0              # Data validation
```

