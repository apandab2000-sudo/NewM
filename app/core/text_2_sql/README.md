# Text-to-SQL Component

## Overview

Converts natural language questions into SQL queries and returns results. Users ask in English, component generates and executes SQL.

**Tech**: OpenAI LLM + SpaCy NLP + Qdrant Vector DB + Redis Cache

## What It Does

- ✅ English question → SQL query
- ✅ Executes on database
- ✅ Auto-corrects errors on retry
- ✅ Caches results (24 hr TTL)
- ✅ Understands business context

## Folder Structure

```
app/core/text_2_sql/
├── text2sql.py            # Main class
├── agent/
│   ├── pipeline.py        # Processing pipeline
│   ├── query_validator.py # Input validation
│   └── error_classes.py   # Exceptions
└── drilldown.py           # Drill-down
```

Related: `app/core/prompts/`, `app/core/schema_strings/`, `business_data/{dataset}/business_context.json`

---

## How It Works

```
User: "Show NSAT by account for Q1 2024"
  ↓
1. Validate Input
   - Check if query is safe & relevant
   - Block malicious patterns (DROP, DELETE, etc.)
  ↓
2. Extract Entities (SpaCy NLP)
   - Identify: NSAT, account, Q1, 2024
  ↓
3. Find Similar Examples (Qdrant vector DB)
   - Search for 5 similar past queries
  ↓
4. Generate SQL (OpenAI GPT-4)
   - Schema + entities + examples → SQL
  ↓
5. Execute & Auto-Correct on error
   - Run SQL, fix if error detected
  ↓
6. Cache Results (Redis - 24 hrs)
   - Store for instant future lookup
  ↓
Returns: SQL Query + Data
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Vector DB unavailable | `curl http://localhost:6333/health` |
| OpenAI error | Verify `OPENAI_API_KEY` in `.env` |
| Column not found | Check schema file |
| SQL timeout | User adds filters |

---

**Dependencies**: openai, sentence-transformers, spacy, qdrant-client, redis, sqlalchemy

