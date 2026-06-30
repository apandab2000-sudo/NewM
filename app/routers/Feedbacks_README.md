# Feedbacks Component

## Overview

Records user feedback on AI-generated insights. Supports two feedback types:
- **Positive**: Validating/approving a query result
- **Negative**: Reporting component issues

Simple data capture component with no LLM processing.

## What It Does

- ✅ Record positive feedback (approves a transaction)
- ✅ Record negative feedback (reports issues with components)
- ✅ Store feedback in database for analysis
- ✅ Track which transactions were validated by users

---

## API Endpoints

### **Positive Feedback** (POST `/egai/positiveFeedback`)

User marks a result as valid/approved.

**Input**:
```json
{
  "chat_id": "conversation_uuid",
  "query_key": "transaction_uuid",
  "dbname": "cx_customer_experience",
  "query": "Show NSAT by account",
  "sql": "SELECT account, NSAT FROM..."
}
```

**Returns** (201 Created):
```json
{
  "comments": "Feedback recorded",
  "status": 201,
  "status_message": "Success"
}
```

**What happens**: Sets `validated_transaction=true` in database

---

### **Negative Feedback** (POST `/egai/feedback/negativeFeedback`)

User reports issues with one or more components.

**Input**:
```json
{
  "user_name": "john smith",
  "chat_id": "conversation_uuid",
  "dbname": "cx_customer_experience",
  "query_key": "transaction_uuid",
  "feedback_list": [
    {
      "component": "insights",
      "comment": "Summary was inaccurate, missed regional breakdown"
    },
    {
      "component": "graph",
      "comment": "Chart was hard to read, too many categories"
    }
  ]
}
```

**Returns** (201 Created):
```json
{
  "comments": "Feedback recorded",
  "status": 201,
  "status_message": "Success"
}
```

**What happens**: Stores feedback array as JSON in database

---

## Storage

Feedback stored in SQL database:

```
Table: transactions_new
├─ validated_transaction [Boolean]  # Set by positive feedback
├─ feedback [VARCHAR 4000]          # JSON array from negative feedback
├─ comments [VARCHAR 1000]          # General comments
└─ transaction_id                   # Links to original transaction
```

---


## How Feedbacks Are Used

**Positive Feedback (validated_transaction=true)**:
- Marks high-quality results for model training
- Indicates user approved the analysis
- Used to measure feature satisfaction

**Negative Feedback (feedback_list)**:
- Identifies specific component issues
- Captures user-reported accuracy problems
- Helps prioritize improvements
- Tracks which features need refinement

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Feedback not recorded | Ensure transaction_id/query_key is valid |
| Components not recognized | Use standard component names (see list above) |
| Feedback lost on restart | Feedback persists in SQL database |

---

