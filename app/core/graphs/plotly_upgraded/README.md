# Plotly Upgraded

This package is a non-breaking, isolated upgrade path for graph generation.
It does not modify or replace modules under `app/core/graphs/plotly`.

## Entry Point

- `generate_graphs` from `base.py`

## Architecture

This package now follows a layered and extensible design:

1. `base.py` (Facade)
- Single integration entrypoint.
- Handles profile inference, default planning, and response formatting.

2. `strategies.py` (Strategy Pattern)
- Each graph type has a strategy class.
- New graph types can be added without modifying existing strategy classes.

3. `composers.py` (Composition Service)
- Composes complete figures from reusable traces.
- Keeps chart-level orchestration separate from trace details.

4. `trace_factory.py` (Factory Pattern)
- Builds standardized Plotly traces (`Bar`, `Scatter`, `Pie`, `Funnel`, `Waterfall`).
- Ensures consistency of trace creation across all chart types.

5. `architecture.py` (Contracts)
- Contains context and protocol abstractions.
- Supports dependency inversion between dispatcher, strategies, and composer.

## SOLID Alignment

- Single Responsibility Principle:
    - Dispatcher, strategy selection, composition, and trace creation are separate concerns.
- Open/Closed Principle:
    - Add new strategies or traces without changing existing implementations.
- Liskov Substitution Principle:
    - Strategies are interchangeable via a common contract.
- Interface Segregation Principle:
    - Strategies depend on focused composer methods, not a monolithic API surface.
- Dependency Inversion Principle:
    - High-level flow depends on contracts/protocols, not concrete graph functions.

## Supported Graph Families

- bar
- horizontal_bar
- grouped_bar
- stacked_bar
- line
- area
- scatter
- pie
- donut
- treemap
- sunburst
- funnel
- waterfall
- pareto
- gauge

## How To Add A New Graph Type

1. Add/normalize graph key in `constants.py` (if alias needed).
2. Add a strategy class in `strategies.py` and register it in `StrategyRegistry`.
3. Implement composer method in `composers.py`.
4. Reuse trace constructors from `trace_factory.py`.

## Example

```python
from app.core.graphs.plotly_upgraded import generate_graphs

graphs = generate_graphs(df, graph_title="Sales Overview", python=True)
```
