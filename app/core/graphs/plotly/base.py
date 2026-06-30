import pandas as pd
from app.logger import get_logger
from app.core.prompts import PromptGetter
from .helper import DataCorrection, get_most_similar_column_names
from .plotly_graphs_1d import get_gauge_chart
from .plotly_graphs_2d import (
    get_2d_bar_chart,
    get_2d_line_chart,
    get_2d_pie_chart,
    get_pareto_chart,
    get_2d_scatter_plot
)
from .plotly_graphs_3d import (
    get_3d_vertical_bar_chart,
    get_3d_bar_and_line_chart,
    get_3d_horizontal_bar_chart,
    get_3d_vertical_bar_chart_date,
    get_3d_bar_and_line_chart_date,
    get_3d_linechart,
    get_3d_multiple_lines,
    get_3d_multiple_bars,
    get_3d_cat_bars,
    get_3d_treemap
)
from .plotly_graphs_4dplus import (
    get_4d_cat_bars,
    get_4d_multiple_lines,
    get_4d_bar_and_line_chart,
    get_4d_vertical_bar_chart,
    get_4d_multiple_lines_multiple_num
)
from app.core.llms import get_llm_response
from app.core.helper import is_percentage_column


logger = get_logger()




def get_1d_graphs(df: pd.DataFrame, numerical_columns, categorical_columns, datetime_columns) -> list:

    print({
        "num": numerical_columns,
        "cat": categorical_columns,
        "date": datetime_columns
    })
    graphs_list = []

    temp = df.copy()

    if len(numerical_columns) == 1:
        gauge_chart = get_gauge_chart(temp, numerical_columns)
        graphs_list.append({"type": "gauge_chart", "graph": gauge_chart})

    return graphs_list


def get_2d_graphs(df: pd.DataFrame, numerical_columns, categorical_columns, datetime_columns) -> list:
    graphs_list = []

    temp = df.copy()

    if len(numerical_columns) == 2:
        print("CASE OF 2 NUMERIC")
        scatter_plot = get_2d_scatter_plot(temp, numerical_columns)
        graphs_list.append({"type": "scatter_plot", "graph": scatter_plot})

    if len(categorical_columns) == 1 and len(numerical_columns) == 1:
        print("CASE OF 1 CATEGORICAL AND 1 NUMERIC")
        temp = temp[(temp[numerical_columns[0]] != 0) & (temp[categorical_columns[0]].notna())]
        vertical_bar_chart = get_2d_bar_chart(temp, numerical_columns, cat_cols=categorical_columns)
        print("VERICAL BAR CHART GENERATED")
        graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_chart})

        horizontal_bar_chart = get_2d_bar_chart(temp, numerical_columns, categorical_columns, orientation="h")
        graphs_list.append({"type": "horizontal_barchart", "graph": horizontal_bar_chart})

        if temp[categorical_columns[0]].nunique() <= 10:
            pie_chart = get_2d_pie_chart(temp, numerical_columns, categorical_columns)
            graphs_list.append({"type": "Piechart", "graph": pie_chart})

        pareto_chart = get_pareto_chart(temp, numerical_columns, categorical_columns)
        graphs_list.append({"type": "Advanced_Chart", "graph": pareto_chart})

        if temp[categorical_columns[0]].nunique() <= 5:
            graphs_list = [graphs_list[2], graphs_list[1], graphs_list[0], graphs_list[3]]
        elif temp[categorical_columns[0]].nunique() <= 10:
            graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2], graphs_list[3]]

    if len(datetime_columns) == 1 and len(numerical_columns) == 1:
        print("CASE OF 1 DATETIME AND 1 NUMERIC")
        temp = temp[(temp[numerical_columns[0]] != 0) & (temp[datetime_columns[0]].notna())]
        line_chart = get_2d_line_chart(temp, numerical_columns, datetime_columns)
        graphs_list.append({"type": "Line_Chart", "graph": line_chart})

        bar_chart = get_2d_bar_chart(temp, numerical_columns, date_cols=datetime_columns)
        graphs_list.append({"type": "Vertical_Barchart", "graph": bar_chart})

        area_chart = get_2d_line_chart(temp, numerical_columns, datetime_columns, draw_area=True)
        graphs_list.append({"type": "Area_Chart", "graph": area_chart})

    return graphs_list


def get_3d_graphs(df: pd.DataFrame, numerical_columns, categorical_columns, datetime_columns):
    graphs_list = []

    if len(numerical_columns) == 2 and len(categorical_columns) == 1:
        vertical_bar_graph = get_3d_vertical_bar_chart(df, numerical_columns, categorical_columns)
        graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_graph})

        bar_and_line = get_3d_bar_and_line_chart(df, numerical_columns, categorical_columns)
        graphs_list.append({"type": "Bar_and_Line_Chart", "graph": bar_and_line})

        horizontal_bar_graph = get_3d_horizontal_bar_chart(df, numerical_columns, categorical_columns)
        graphs_list.append({"type": "Horizontal_Barchart", "graph": horizontal_bar_graph})

        if df[categorical_columns[0]].nunique() < 8:
            graphs_list = [graphs_list[2], graphs_list[1], graphs_list[0]]
        if df[categorical_columns[0]].nunique() > 20:
            graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2]]

    if len(numerical_columns) == 2 and len(datetime_columns) == 1:
        bar_and_line = get_3d_bar_and_line_chart_date(df, numerical_columns, date_cols=datetime_columns)
        graphs_list.append({"type": "Bar_and_Line_Chart", "graph": bar_and_line})

        linechart = get_3d_linechart(df, numerical_columns, date_cols=datetime_columns)
        graphs_list.append({"type": "Line_Chart", "graph": linechart})

        vertical_bar_graph = get_3d_vertical_bar_chart_date(df, numerical_columns, date_cols=datetime_columns)
        graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_graph})

        if df[datetime_columns[0]].nunique() > 15:
            graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2]]

    if len(numerical_columns) == 1 and len(datetime_columns) == 1 and len(categorical_columns) == 1:
        linechart = get_3d_multiple_lines(df, numerical_columns, categorical_columns, datetime_columns)
        graphs_list.append({"type": "Line_Chart", "graph": linechart})

        barchart = get_3d_multiple_bars(df, numerical_columns, categorical_columns, datetime_columns)
        graphs_list.append({"type": "Vertcial_Grouped_Barchart", "graph": barchart})

        barchart_2 = get_3d_multiple_bars(df, numerical_columns, categorical_columns, datetime_columns, barmode="stack")
        graphs_list.append({"type": "Vertcial_Stacked_Barchart", "graph": barchart_2})

        linechart = get_3d_multiple_lines(df, numerical_columns, categorical_columns, datetime_columns, draw_area=True)
        graphs_list.append({"type": "Area_Chart", "graph": linechart})

    if len(numerical_columns) == 1 and len(categorical_columns) == 2:
        grouped_bars = get_3d_cat_bars(df, numerical_columns, categorical_columns)
        graphs_list.append({"type": "Vertical_Grouped_Barchart", "graph": grouped_bars})

        stacked_bars = get_3d_cat_bars(df, numerical_columns, categorical_columns, barmode="stack")
        graphs_list.append({"type": "Vertical_Stacked_Barchart", "graph": stacked_bars})

        grouped_bars = get_3d_cat_bars(df, numerical_columns, categorical_columns, orientation="h")
        graphs_list.append({"type": "Horizontal_Grouped_Barchart", "graph": grouped_bars})

        stacked_bars = get_3d_cat_bars(df, numerical_columns, categorical_columns, barmode="stack", orientation="h")
        graphs_list.append({"type": "Horizontal_Stacked_Barchart", "graph": stacked_bars})

        if df.shape[0] < 15:
            graphs_list = [graphs_list[2], graphs_list[3], graphs_list[1], graphs_list[0]]
        elif df.shape[0] < 20:
            graphs_list = [graphs_list[1], graphs_list[3], graphs_list[0], graphs_list[2]]

        try:
            treemap = get_3d_treemap(df, numerical_columns, categorical_columns)
            graphs_list.append({"type": "Treemap", "graph": treemap})
        except:
            pass

    return graphs_list


def get_4d_plus_graphs(user_query: str, df: pd.DataFrame,
                       numerical_columns, categorical_columns, datetime_columns):
    graphs_list = []

    if len(categorical_columns) == 1 and len(datetime_columns) == 0:
        main_cols, rest_cols = get_most_similar_column_names(user_query, df.loc[:, numerical_columns], 4)
        barchart = get_4d_vertical_bar_chart(df, main_cols, cat_cols=categorical_columns,
                                             tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Grouped_Barchart", "graph": barchart})

        barchart2 = get_4d_vertical_bar_chart(df, main_cols, cat_cols=categorical_columns, barmode="stack",
                                              tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Stacked_Barchart", "graph": barchart2})

        bar_line = get_4d_bar_and_line_chart(df, main_cols, categorical_columns, tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Bar_And_Line_Chart", "graph": bar_line})

    if len(datetime_columns) == 1 and len(categorical_columns) == 0:
        main_cols, rest_cols = get_most_similar_column_names(user_query, df.loc[:, numerical_columns], 4)
        linechart = get_4d_multiple_lines_multiple_num(df, main_cols, datetime_columns,
                                                       tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Line_Chart", "graph": linechart})

        barchart = get_4d_vertical_bar_chart(df, main_cols, date_cols=datetime_columns,
                                             tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Grouped_Barchart", "graph": barchart})

        bar_line = get_4d_bar_and_line_chart(df, main_cols, date_cols=datetime_columns,
                                             tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Bar_And_Line_Chart", "graph": bar_line})

    if len(categorical_columns) == 2 and len(datetime_columns) == 0:
        main_cols, rest_cols = get_most_similar_column_names(user_query, df.loc[:, numerical_columns])
        barchart = get_4d_cat_bars(df, main_cols, categorical_columns, tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Grouped_Barchart", "graph": barchart})

        barchart = get_4d_cat_bars(df, main_cols, categorical_columns, barmode="stack",
                                   tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Stacked_Barchart", "graph": barchart})

    if len(categorical_columns) == 1 and len(datetime_columns) == 1:
        main_cols, rest_cols = get_most_similar_column_names(user_query, df.loc[:, numerical_columns])
        linechart = get_4d_multiple_lines(df, main_cols, categorical_columns, datetime_columns,
                                          tooltip_list=df.columns.tolist())
        graphs_list.append({"type": "Line_Chart", "graph": linechart})

        areachart = get_4d_multiple_lines(df, main_cols, categorical_columns, datetime_columns,
                                          tooltip_list=df.columns.tolist(),
                                          draw_area=True)
        graphs_list.append({"type": "Area_Chart", "graph": areachart})

    return graphs_list



def limit_axis_values(
    df: pd.DataFrame,
    numerical_columns: list,
    categorical_columns: list,
    datetime_columns: list,
    max_values: int = 20
) -> pd.DataFrame:
    """
    Limit categorical and datetime axis values to a maximum of `max_values`.

    - Categorical columns keep the top values based on the summed value of the
      first numerical column.
    - Datetime columns keep the most recent values.
    - If no numerical column is available, categorical columns keep the first
      values in their existing order.
    """
    limited_df = df.copy()
    primary_numeric_column = numerical_columns[0] if numerical_columns else None

    for column in categorical_columns:
        if column not in limited_df.columns:
            continue

        unique_count = limited_df[column].nunique(dropna=True)

        if unique_count <= max_values:
            continue

        if primary_numeric_column and primary_numeric_column in limited_df.columns:
            top_values = (
                limited_df.groupby(column, dropna=False)[primary_numeric_column]
                .sum()
                .sort_values(ascending=False)
                .head(max_values)
                .index
            )
        else:
            top_values = (
                limited_df.loc[limited_df[column].notna(), column]
                .drop_duplicates(keep="first")
                .head(max_values)
            )

        limited_df = limited_df[limited_df[column].isin(top_values)]

    for column in datetime_columns:
        if column not in limited_df.columns:
            continue

        unique_count = limited_df[column].nunique(dropna=True)

        if unique_count <= max_values:
            continue

        top_values = (
            limited_df.loc[limited_df[column].notna(), column]
            .drop_duplicates()
            .sort_values()
            .tail(max_values)
        )

        limited_df = limited_df[limited_df[column].isin(top_values)]

    return limited_df.reset_index(drop=True)

def limit_categories(
    df: pd.DataFrame,
    cat_cols: list,
    date_cols: list,
    total_allowed: int = 25,
    # position: str = "first"  # "first" or "last"
) -> pd.DataFrame:
    
    df = df.copy()

    cols = cat_cols + date_cols
    if cols:
        top_values_per_col = {}

        # Distribute limit across columns proportionally
        per_col_limit = max(1, total_allowed // len(cols))

        for c in cols:
            col_values = df.loc[df[c].notna(), c].drop_duplicates(keep="first").sort_index()

            if date_cols:
                # If date column present in df -> take last 25 unique values.
                top_values_per_col[c] = col_values.iloc[-per_col_limit:]
            else:
                # If not -> take first 25 unique values.
                top_values_per_col[c] = col_values.iloc[:per_col_limit]    
            

        # Build combined filter mask
        mask = pd.Series(True, index=df.index)
        for c, top_vals in top_values_per_col.items():
            mask &= df[c].isin(top_vals)

        df = df[mask].sort_index().reset_index(drop=True)
    
    else:
        df = df.iloc[:200]

    return df


def limit_categories_bkp(df: pd.DataFrame, cat_cols: list, date_cols: list) -> pd.DataFrame:
    
    df = df.copy()

    cols = cat_cols+date_cols
    if cols:
        cols = cat_cols+date_cols
        # col = date_cols[0]
        # top_dates = df[col].dropna().unique()[:max_unique]
        # df = df[df[col].isin(top_dates)]

        # Get top unique values from each categorical column
        top_values_per_col = {}
        total_allowed = 25

        # Distribute limit across columns proportionally
        per_col_limit = max(1, total_allowed // len(cols))

        for c in cols:
            # top_values_per_col[c] = df[c].value_counts().head(per_col_limit).index
            top_values_per_col[c] = (
                df.loc[df[c].notna(), c]
                .drop_duplicates(keep="first")
                .iloc[:per_col_limit]
                .sort_index()
            )

        # Filter the DataFrame to keep only the top values for each column
        mask = pd.Series(True, index=df.index)
        for c, top_vals in top_values_per_col.items():
            mask &= df[c].isin(top_vals)

        df = df[mask].sort_index().reset_index(drop=True)
    
    else:
        df = df.iloc[:200]

    return df


async def generate_graph_title(user_query: str, df: pd.DataFrame, db_name: str, llm, llm_model):
    columns = df.columns.tolist()
    prompt_getter = PromptGetter(db_name)
    graph_title_sys_prompt = prompt_getter.get_prompt("graph_title_prompt")
    graph_title_sys_prompt = graph_title_sys_prompt.format(columns=columns)
    messages = [
        {"role": "system", "content": graph_title_sys_prompt},
        {"role": "user", "content": user_query},
    ]
    graph_title, token_usage = await get_llm_response(llm, llm_model, messages)
    if graph_title:
        return graph_title["title"], token_usage
    return "", token_usage

def filter_top_combinations(df, cat_cols, max_combinations=25):
    group_counts = df.groupby(cat_cols).size().reset_index(name="count")
    top_combos = group_counts.sort_values("count", ascending=False).head(max_combinations)

    filtered_df = df.merge(top_combos[cat_cols], on=cat_cols, how='inner')
    return filtered_df


def select_graph_numerical_columns(
    user_query: str,
    numerical_columns: list
) -> list:
    """
    Select the numeric columns that should actually be plotted.

    For percentage/rate/share/ratio questions, only percentage-based
    numeric columns are plotted. Count columns remain in the DataFrame
    so they can still be included in hover details and returned tables.

    Examples:
        CheckoutSessions                  -> not plotted
        AbandonedCheckouts                -> not plotted
        CheckoutAbandonmentRatePercent    -> plotted
    """
    if not numerical_columns:
        return numerical_columns

    percentage_columns = [
        column_name
        for column_name in numerical_columns
        if is_percentage_column(column_name)
    ]

    if not percentage_columns:
        return numerical_columns

    normalized_query = str(user_query).lower()

    percentage_query_terms = (
        "percentage",
        "percent",
        "rate",
        "share",
        "ratio",
        "conversion",
        "abandonment",
        "drop-off",
        "dropoff",
    )

    is_percentage_query = any(
        term in normalized_query
        for term in percentage_query_terms
    )

    if is_percentage_query:
        print(
            "[GRAPH NUMERIC SELECTION] "
            f"Percentage question detected. "
            f"Original numeric columns: {numerical_columns}. "
            f"Selected columns: {percentage_columns}"
        )

        return percentage_columns

    return numerical_columns

async def generate_graphs(user_query: str, df: pd.DataFrame, db_name: str="", llm: str="", python=False, filters=[], llm_model: str = "gpt-4.1-mini", al_graph_title: str | None = None):
    dc = DataCorrection(df)
    dc.correct_columns_names()
    dc.extract_datatype_based_columns()
    dc.correct_data_with_datetime_columns()
    # dc.correct_categorical_long_context()
    df = dc.sorting_dataframe()
    # df = dc.process_dataframe()

    numerical_columns = dc.numerical_columns
    categorical_columns = dc.categorical_columns
    datetime_columns = dc.datetime_columns

    # For percentage/rate questions, keep count columns in the DataFrame
    # for tooltip context, but plot only percentage-based measures.
    numerical_columns = select_graph_numerical_columns(
        user_query=user_query,
        numerical_columns=numerical_columns,
    )

    if not al_graph_title:
        graph_title, token_usage = await generate_graph_title(user_query+". Filters= "+str(filters), df, db_name, llm, llm_model)
    else:
        graph_title, token_usage = al_graph_title, {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}

    # Drop datetime columns with only one unique value
    if categorical_columns and datetime_columns:
        datetime_columns_to_drop = [col for col in datetime_columns if len(df[col].unique()) == 1]
        df = df.drop(columns=datetime_columns_to_drop)
        datetime_columns = [col for col in datetime_columns if col not in datetime_columns_to_drop]

    # Remove Null rows  
    df = df.dropna(subset=categorical_columns+datetime_columns)
    print({
        "num": numerical_columns,
        "cat": categorical_columns,
        "date": datetime_columns
    })
    
    df = df.replace({pd.NA: None})

    # Prevent crowded categorical or datetime axes by keeping at most 20 values.
    df = limit_axis_values(
        df=df,
        numerical_columns=numerical_columns,
        categorical_columns=categorical_columns,
        datetime_columns=datetime_columns,
        max_values=20
    )

    rows, columns = df.shape

    # if rows > 25:
    #     df = df.iloc[:25]

    if len(datetime_columns)==0:
        df = df.iloc[:200]
    # df = limit_categories(df, categorical_columns, datetime_columns)

    try:
        if rows >= 1 and columns >= 1:
            if rows == 1:
                # graphs_list = []
                print("CASE of 1D graphs")
                graphs_list = get_1d_graphs(df, numerical_columns, categorical_columns, datetime_columns)
            elif columns == 2:
                # if rows > 25:
                #     df = df.iloc[:25]
                print("CASE of 2D graphs")
                graphs_list = get_2d_graphs(df, numerical_columns, categorical_columns, datetime_columns)
            elif columns == 3:
                # cat_subset = [col for col in categorical_columns+datetime_columns]
                # df = filter_top_4d_combinations(df, cat_subset)
                print("CASE of 3D graphs")
                graphs_list = get_3d_graphs(df, numerical_columns, categorical_columns, datetime_columns)
            elif 4 <= columns <= 10:
                # cat_subset = [col for col in categorical_columns+datetime_columns]
                # df = filter_top_4d_combinations(df, cat_subset)
                print("CASE of 4D graphs")
                graphs_list = get_4d_plus_graphs(user_query, df, numerical_columns,
                                                categorical_columns, datetime_columns)
            else:
                graphs_list = []
        else:
            graphs_list = []
    except Exception as e:
        logger.error(f"Error generating graph for query: '{user_query}': {str(e)}")
        graphs_list = []

    if graphs_list:
        try:
            for i in range(len(graphs_list)):
                fig = graphs_list[i]["graph"]

                fig.update_layout(
                    template="simple_white",
                    margin=dict(l=20, r=20, b=0, t=0, pad=0),
                    height=350,
                    font=dict(
                        family="open sans, Helvetica Neue, Helvetica, Arial, sans-serif",
                    ),
                    title=dict(
                        text=graph_title,
                        x=0,
                        y=0.96,
                        font_color="#1E78B4",
                        xanchor="left",
                        font_size=2,
                        font_weight=800
                    ),
                    legend_grouptitlefont=dict(
                        size=12.8,
                        weight=600
                    ),
                    legend=dict(
                        orientation="h",
                        xref="container",
                        yref="container",
                        yanchor="auto",
                        xanchor="auto",
                        font_size=12,
                        font_weight=400
                    ),
                    xaxis_title=dict(
                        font_size=12.8,
                        font_weight=400
                    ),
                    yaxis_title=dict(
                        font_size=12.8,
                        font_weight=400
                    ),
                    barcornerradius="5%",
                    bargroupgap=0.2
                )
                fig.update_xaxes(tickfont=dict(size=12))
                fig.update_yaxes(tickfont=dict(size=12))
                if python:
                    graphs_list[i]["graph"] = fig
                else:
                    graphs_list[i]["graph"] = fig.to_json()
                graphs_list[i]["graph_id"] = i
        except Exception as e:
            graphs_list =[]
            logger.error(f"Error generating graph for query: '{user_query}': {str(e)}")
    return graphs_list, token_usage
