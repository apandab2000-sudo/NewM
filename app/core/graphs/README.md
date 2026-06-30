# Graphs Component

## Overview

Automatically generates interactive charts from data. Analyzes table structure and creates appropriate visualizations (bar charts, pie charts, line graphs, etc.) based on data types.

**Tech**: Plotly (primary) + PyEcharts (alternative)

## What It Does

- ✅ Analyzes data columns (numeric, categorical, datetime)
- ✅ Auto-selects best chart type for data
- ✅ Generates 2-4 chart variants per dataset
- ✅ Applies styling (colors, labels, responsive sizing)
- ✅ Returns JSON-serialized chart configs for frontend rendering

## Folder Structure

```
app/core/graphs/
├── plotly/                    # Plotly-based charts
│   ├── base.py               # Main orchestration
│   ├── plotly_graphs_1d.py   # Single column charts
│   ├── plotly_graphs_2d.py   # Two column charts
│   ├── plotly_graphs_3d.py   # Three column charts
│   ├── plotly_graphs_4dplus.py # Complex charts
│   └── helper.py             # Colors & utilities
└── echarts/                   # PyEcharts alternative
    └── graphs.py             # ECharts generator
```

---

## How It Works

```
Input: Pandas DataFrame from SQL query
  ↓
1. Analyze Data
   - Identify column types (numeric, text, date)
   - Check data count & quality
  ↓
2. Classify Dimensions
   - Numeric cols → use for axes/aggregations
   - Categorical → use for grouping/labels
   - Datetime → use for time series
  ↓
3. Detect Chart Needs
   - 1 column → histogram, gauge
   - 2 columns → bar, pie, scatter, line
   - 3+ columns → multi-axis, heatmap
  ↓
4. Generate Charts
   - Create 2-4 variants per dimension combo
   - Apply styling (colors, labels, formatting)
  ↓
5. Format Output
   - Convert charts to JSON serialized configs
   - Add metadata (id, type, title)
  ↓
Returns: List of chart configs (JSON strings for frontend)
```

---

## Output Format

```
[
  {
    "graph": "{json_config}",    # JSON string of chart
    "graph_id": 0,
    "type": "Vertical_Barchart"
  },
  {
    "graph": "{json_config}",
    "graph_id": 1,
    "type": "Pie_Chart"
  }
]
```

Frontend uses these JSON configs to render interactive charts.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No charts generated | Check if data has numeric columns |
| Chart looks empty | Too many rows (>200)? Add filters |
| Wrong chart type | Data types wrong? Check column types |
| Slow rendering | Large dataset? Limit rows or aggregate |

