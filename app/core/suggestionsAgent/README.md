# Suggestions Component

## Overview

Generates intelligent follow-up questions based on a user's original query. When user asks a question, this component suggests 3-5 deeper exploration questions they might ask next.

**Tech**: OpenAI LLM + SQL Execution + Parallel Query Processing

## What It Does

- ✅ Takes completed user query + its SQL result
- ✅ Generates 3-5 follow-up question suggestions using LLM
- ✅ Validates each suggestion by executing the SQL
- ✅ Returns only questions with valid, working results
- ✅ Stores suggestions in NoSQL for later analysis

---

## Folder Structure

```
app/core/suggestionsAgent/
└── (files inside suggestionsAgent.py)

Related:
├── app/routers/suggestions.py      # API endpoints
├── app/core/prompts/{dbname}.py    # LLM prompts
└── app/core/schema_strings/        # Database schemas
```

---

## How It Works

```
User: "Show NSAT by account"
(already executed)
  ↓
1. Fetch Original Query
   - Get original SQL + result from database
   ↓
2. Load LLM Config
   - Read database-specific model from clientConfig.yaml
   ↓
3. Generate Suggestions (LLM)
   - Schema + filters + original query
   → "Show NSAT trend over quarters"
   → "Top accounts by NSAT change"
   → "NSAT by region breakdown"
   ↓
4. Validate Each Suggestion
   - Execute each suggested SQL in parallel
   - Keep only if execution succeeds
   ↓
5. Store & Return
   - Save to NoSQL (MongoDB)
   - Return list of working suggestions
   ↓
Returns: List of question strings
```

---

**Returns**:
```
{
  "suggestions": [
    "Show NSAT trend over quarters",
    "Top accounts by NSAT change",
    "NSAT by region breakdown"
  ]
}
```

### 2. **Analyze Suggestion** (POST `/egai/getSuggestionAnalysis`)

When user clicks a suggestion, get full analysis:

**Returns**:
```
{
  "query_key": "new_transaction_id",
  "suggestion_query": "Show NSAT trend over quarters",
  "sql": "SELECT Quarter, NSAT FROM...",
  "table": [...],              # Result rows
  "plotlycharts": [...],       # Graph objects
  "drilldown_features": [...], # Drill-down options
  "approach": "Analysis..."
}
```

## How Suggestions Are Generated

1. **LLM sees**:
   - Database schema
   - Original user question
   - Original SQL code
   - Applied filters

2. **LLM generates** 3-5 follow-up questions that:
   - Explore deeper insights
   - Use different dimensions
   - Find trends/comparisons
   - Validate data quality

3. **System executes** all suggestions to verify they work

4. **Returns only** suggestions with successful SQL execution

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No suggestions returned | Original query may be too complex or unique |
| Wrong suggestions | Check schema definition, may be missing table context |
| Suggestions fail to execute | Schema changed? Verify tables & columns exist |
| Slow response | Too many rows? Add filters to original query |

---