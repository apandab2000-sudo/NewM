# Insights Component

## Overview

Generates AI-powered executive summaries from query results. Takes a primary SQL result, uses LLM to generate 1-2 complementary queries, executes them in parallel, and returns formatted HTML insights.

**Tech**: LLM + SQL Execution + Data Statistics + HTML Formatting

## What It Does

- ✅ Takes primary table result + user's question
- ✅ LLM generates 1-2 complementary SQL queries automatically
- ✅ Executes secondary queries in parallel
- ✅ Analyzes all data + statistics using LLM
- ✅ Returns HTML-formatted insight sections + executive summary
- ✅ Stores insights in MongoDB for later retrieval

---

## Folder Structure

```
app/core/inisghts/
└── insightsAgent.py        # Core logic

Related:
├── app/routers/insights.py     # API endpoint
├── app/core/prompts/{dbname}.py
└── app/core/schema_strings/    # Database schemas
```

---

## How It Works

```
Primary Result Table + Question
  ↓
1. Load LLM Config
   - Read database-specific model from clientConfig.yaml
   ↓
2. Generate Secondary SQLs (LLM)
   - Input: Schema + filters + primary question + original SQL
   - LLM generates 1-2 complementary query purposes
   ↓
3. Execute in Parallel
   - Primary table: stats (describe)
   - 1-2 secondary tables: stats (describe)
   - Max 500 rows per query
   ↓
4. Generate Insights (LLM)
   - Input: All tables + all statistics
   - LLM creates HTML-formatted analysis
   ↓
5. Parse & Format
   - Extract sections by <h3> tags
   - Extract summary paragraph
   ↓
6. Store & Return
   - Save to MongoDB (indexed by transaction_id)
   - Return insights list + consolidated summary
   ↓
Returns: List of HTML sections + summary text
```

---

## API Endpoint

### **Get Insights** (POST `/egai/getIntelligentInsights`)

**Input**:
```
{
  "dbname": "cx_customer_experience",
  "first_name": "John",
  "last_name": "Doe",
  "email_id": "john@company.com",
  "chat_id": "chat_uuid",
  "query_key": "transaction_uuid",
  "query": "Show NSAT by account",
  "table": [...],           # Primary result rows
  "sql": "SELECT ...",      # Original SQL
  "filters": [...]
}
```

**Returns**:
```
{
  "status": 200,
  "status_message": "Success",
  "insights": [
    "<h3>Key Findings</h3><ul><li>Account X has 15% higher NSAT than average</li></ul>",
    "<h3>Segment Drivers</h3><p>Premium accounts show 23% better scores...</p>",
    "<h3>Marketing Intelligence</h3><p>Q4 campaigns drove 8% improvement...</p>"
  ],
  "consolidated_insights": "Executive summary paragraph with key metrics and findings..."
}
```

---

## How Insights Are Generated

### **Phase 1: SQL Generation**
1. LLM receives:
   - Database schema
   - Primary SQL + result
   - Applied filters
   - User's original question

2. LLM generates 1-2 queries like:
   - "Segment breakdown by customer tier"
   - "Trend analysis month-over-month"

3. System executes all queries in parallel

### **Phase 2: Analysis**
4. LLM receives:
   - Primary table data + statistics
   - Secondary table data + statistics
   - User question for context

5. LLM generates:
   - Section 1: Key Findings (with numbers)
   - Section 2: Segment Drivers (breakdown by dimension)
   - Section 3: Business Intelligence (recommendations)
   - Summary: 1-paragraph executive takeaway

---

## Storage

Insights are stored in MongoDB:

```python
{
  "transaction_id": "uuid",
  "distinct_insights": [
    "<h3>Key Findings</h3>...",
    "<h3>Segment Drivers</h3>..."
  ],
  "consolidated_insight": "Summary paragraph...",
  "insights_data": [
    {
      "sql": "SELECT...",
      "table": [{"col1": val, ...}, ...]
    }
  ]
}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No insights returned | Query result may be too small (<10 rows) |
| Generic insights | Check schema context, may be incomplete |
| Secondary SQLs fail | Schema changed? Verify table/column existence |
| Slow response | Too many rows? System limits to 500 per query |
| Empty sections | Check LLM prompt config for database |

---
