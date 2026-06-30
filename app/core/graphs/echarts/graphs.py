import numpy as np
import pandas as pd
import json
from pandas.api.types import (
    is_numeric_dtype,
    is_datetime64_any_dtype,
    is_object_dtype, is_string_dtype
)
from typing import List
# from app.core.logger import get_logger
from .echarts_graphs_2d import *
from .echarts_graphs_3d import *
from app.core.prompts import PromptGetter
from app.core.llms import get_llm_response

# from graphs.echarts_graphs_2d import *
# from graphs.echarts_graphs_3d import *
# from graphs.echarts_graphs_4d import *
# from graphs.echarts_graphs_5d import *


from app.logger import get_logger


logger = get_logger()

def is_secondary_axis_required(df, num_cols: List[str], threshold=5):
    num_col_1 = num_cols[0]
    num_col_2 = num_cols[1]
    
    range1 = df[num_col_1].max() - df[num_col_1].min()
    range2 = df[num_col_2].max() - df[num_col_2].min()

    ratio = max(range1, range2) / max(min(range1, range2), 1)
    use_secondary_axis = ratio > threshold # currently keeping threshshold of 5
    return bool(use_secondary_axis)


def datatype_extractor(df: pd.DataFrame):
    numerical_columns = []
    categorical_columns = []
    datetime_columns = []
    
    for col in df.columns:
        col_series = df[col]
        if is_numeric_dtype(col_series): # int, float
            numerical_columns.append(col)
            continue

        if is_datetime64_any_dtype(col_series): # like (2025-10-16 or 2025-10-16 17:00)
            datetime_columns.append(col)
            continue
        
        if is_object_dtype(col_series) or is_string_dtype(col_series): # string
            try:
                # converted = pd.to_datetime(col_series, errors="raise")
                converted = pd.to_datetime(col_series, errors="raise") # like "2025-10-16"
                if not pd.isna(converted).all():
                    df[col] = converted
                    datetime_columns.append(col)
                    continue
            except Exception:
                categorical_columns.append(col)
                continue

        # else:  #
        #     categorical_columns.append(col)  
        #     continue

    return {
        "numerical": numerical_columns,
        "categorical": categorical_columns,
        "datetime": datetime_columns,
    }
# def datatype_extractor(df: pd.DataFrame):
#     numerical_columns = []
#     categorical_columns = []
#     datetime_columns = []
    
#     for col in df.columns:
#         col_series = df[col]
#         if is_numeric_dtype(col_series):
#             numerical_columns.append(col)
#             continue

#         if is_datetime64_any_dtype(col_series):
#             datetime_columns.append(col)
#         else:  # ← ALL STRINGS = CATEGORICAL
#             categorical_columns.append(col)
#             continue

#     return {
#         "numerical": numerical_columns,
#         "categorical": categorical_columns,
#         "datetime": datetime_columns,
#     }

# async def generate_graph_title(user_query: str, df: pd.DataFrame, db_name: str, llm, llm_model):
#     columns = df.columns.tolist()
#     prompt_getter = PromptGetter(db_name)
#     graph_title_sys_prompt = prompt_getter.get_prompt("graph_title_prompt")
#     graph_title_sys_prompt = graph_title_sys_prompt.format(columns=columns)
#     messages = [
#         {"role": "system", "content": graph_title_sys_prompt},
#         {"role": "user", "content": user_query},
#     ]
#     graph_title, token_usage = await get_llm_response(llm, llm_model, messages)
#     if graph_title:
#         return graph_title["title"], token_usage
#     return "", token_usage


async def generate_graph_title(user_query: str | None, df: pd.DataFrame, db_name: str, llm, llm_model):
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


class GraphGenerator:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.column_category_mappings = datatype_extractor(df)

        self.num_cols = self.column_category_mappings["numerical"]
        self.cat_cols = self.column_category_mappings["categorical"]
        self.dt_cols = self.column_category_mappings["datetime"]

    def correct_data_(self):
        # removing rows where categorical/datetime column is null
        self.df = self.df.dropna(axis=0, subset=self.cat_cols+self.dt_cols, how="any")
        
        # removing single value columns
        for c in self.df.columns:
            if self.df[c].nunique()==1:
                self.df = self.df.drop(c, axis=1)
        
        return self.df
    
    def generate_graphs(self):
        print("########### COLUMNS BEFORE CLEANING ##############")
        print(self.column_category_mappings)
        
        self.df = self.correct_data_()
        # print("before", df.head(5))
        
        print("########### COLUMNS AFTER CLEANING ##############")
        self.column_category_mappings = datatype_extractor(self.df)
        self.num_cols = self.column_category_mappings["numerical"]
        self.cat_cols = self.column_category_mappings["categorical"]
        self.dt_cols = self.column_category_mappings["datetime"]
        print(self.column_category_mappings)

        rows, columns = self.df.shape

        if columns == 1:
            logger.error("Only 1 valid column found in data")
            return []
        
        if not self.num_cols:
            logger.error("No Numeric columns in the data")
            return []
        
        if rows==1:
            self.df = self.df[self.num_cols].T.reset_index()
            self.df.columns = ["Catgeory", "Value"]
            self.num_cols = ["Value"]
            self.cat_cols = ["Category"]
            self.dt_cols = []
            rows, columns = self.df.shape

        if columns == 2:
            try:
                print("2D PATH")
                graph_list = self.get_2d_graphs()
                print(f"2D RESULT: {len(graph_list)} charts")
                if not graph_list:
                    logger.error("graphs Note Generated sucessfully - 2D Graphs")
            except Exception as e:
                logger.error("Error Generating Graph with 2 columns")
                graph_list = []
        
        elif columns == 3:
            try:
                print("3D PATH")
                graph_list = self.get_3d_graphs()
                print(f"3D RESULT: {len(graph_list)} charts")
                if not graph_list:
                    logger.error("graphs Note Generated sucessfully - 2D Graphs")
            except Exception as e:
                logger.error("Error Generating Graph with 3 columns")
                graph_list = []
    
        elif columns == 4:
            try:
                print("4D PATH")
                graph_list = self.get_4d_plus_graphs()
                print(f"4D RESULT: {len(graph_list)} charts")
                if not graph_list:
                    logger.error("graphs Note Generated sucessfully - 2D Graphs")
            except Exception as e:
                logger.error("Error Generating Graph with more than 4 columns")
                graph_list = []
        
        else:
            logger.error("Number of columns are beyond accepatable range")
            graph_list = []

        updated_graph_list = [] 
        for i, g in enumerate(graph_list):
            graph = g["graph"].dump_options_with_quotes()
            graph = json.loads(graph)

            for s in graph["series"]:
                if "label" in s.keys():
                    if "formatter" in s["label"].keys():
                        s["label"]["formatter"] = "__FORMAT_FUNC_LABEL__"
                    
                if "itemStyle" in s.keys():
                    if "color" in s["itemStyle"] and "function" in str(s["itemStyle"]["color"]):
                        s["itemStyle"]["color"] = "__FORMAT_FUNC_COLOR__"


            # for s in graph["series"]:
            #     if "label" in s and "formatter" in s["label"]:#new
            #         s["label"]["formatter"] = "{b}"#new
            #     # s["label"]["formatter"] = "__FORMAT_FUNC_LABEL__"
                
            #     if "itemStyle" in s and "color" in s["itemStyle"] and "function(x)" in str(s["itemStyle"]["color"]):
            #         s["itemStyle"]["color"] = "__FORMAT_FUNC_COLOR__"

            if "xAxis" in graph:        
                for s in graph["xAxis"]:
                    if s.get("axisLabel", {}).get("formatter", None):  #
                        s["axisLabel"]["formatter"] = "__FORMAT_FUNC_AXIS__"
 
            if "yAxis" in graph:                          
                for s in graph["yAxis"]:
                    if s.get("axisLabel", {}).get("formatter", None):  
                        s["axisLabel"]["formatter"] = "__FORMAT_FUNC_AXIS__"
            
            g["graph"] = json.dumps(graph)
            g["graph_id"] = i 
            updated_graph_list.append(g)
        return updated_graph_list


    def get_2d_graphs(self):
        graphs_list = []

        temp = self.df.copy()

        if len(self.num_cols) == 2:
            scatter_plot = get_2d_scatter_plot(temp, self.num_cols)
            graphs_list.append({"type": "scatter_plot", "graph": scatter_plot})

        if len(self.cat_cols) == 1 and len(self.num_cols) == 1:
            vertical_bar_chart = get_2d_bar_chart(temp, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_chart})

            horizontal_bar_chart = get_2d_bar_chart(temp, self.cat_cols, self.num_cols, orientation="h")
            graphs_list.append({"type": "horizontal_barchart", "graph": horizontal_bar_chart})

            if temp[self.cat_cols[0]].nunique() <= 10:
                pie_chart = get_2d_pie_chart(temp, self.cat_cols, self.num_cols)
                graphs_list.append({"type": "Piechart", "graph": pie_chart})

            pareto_chart = get_pareto_chart(temp, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Advanced_Chart", "graph": pareto_chart})

            if temp[self.cat_cols[0]].nunique() <= 5:
                graphs_list = [graphs_list[2], graphs_list[1], graphs_list[0], graphs_list[3]]
            elif temp[self.cat_cols[0]].nunique() <= 10:
                graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2], graphs_list[3]]

        if len(self.dt_cols) == 1 and len(self.num_cols) == 1:
            print("Case of 2d graphs with datetime axis")
            try:
                line_chart = get_2d_line_chart(temp, self.dt_cols, self.num_cols)
                graphs_list.append({"type": "Line_Chart", "graph": line_chart})
            except Exception as e:
                logger.warning(f"Error generating line chart - {str(e)}")

            try:
                bar_chart = get_2d_bar_chart(temp, self.dt_cols, self.num_cols)
                graphs_list.append({"type": "Vertical_Barchart", "graph": bar_chart})
            except Exception as e:
                logger.warning(f"Error generating bar chart - {str(e)}")
            
            try:
                area_chart = get_2d_line_chart(temp, self.dt_cols, self.num_cols, draw_area=True)
                graphs_list.append({"type": "Area_Chart", "graph": area_chart})
            except Exception as e:
                logger.warning(f"Error generating area chart - {str(e)}")

        return graphs_list
        
    
    def get_3d_graphs(self):
        graphs_list = []

        if len(self.num_cols) == 2 and len(self.cat_cols) == 1:
            logger.debug("Case of 1 Categorical and 2 numeirc")
            vertical_bar_graph = get_3d_vertical_bar_chart(self.df, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_graph})

            bar_and_line = get_3d_bar_and_line_chart(self.df, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Bar_and_Line_Chart", "graph": bar_and_line})

            horizontal_bar_graph = get_3d_horizontal_bar_chart(self.df, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Horizontal_Barchart", "graph": horizontal_bar_graph})

            if self.df[self.cat_cols[0]].nunique() < 8:
                graphs_list = [graphs_list[2], graphs_list[1], graphs_list[0]]
            if self.df[self.cat_cols[0]].nunique() > 20:
                graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2]]

        if len(self.num_cols) == 2 and len(self.dt_cols) == 1:
            logger.debug("Case of 2 numeirc and 1 datetime")
            bar_and_line = get_3d_bar_and_line_chart_date(self.df, self.dt_cols, self.num_cols)
            graphs_list.append({"type": "Bar_and_Line_Chart", "graph": bar_and_line})

            linechart = get_3d_linechart(self.df, self.dt_cols, self.num_cols)
            graphs_list.append({"type": "Line_Chart", "graph": linechart})

            vertical_bar_graph = get_3d_vertical_bar_chart_date(self.df, self.dt_cols, self.num_cols)
            graphs_list.append({"type": "Vertical_Barchart", "graph": vertical_bar_graph})

            if self.df[self.dt_cols[0]].nunique() > 15:
                graphs_list = [graphs_list[1], graphs_list[0], graphs_list[2]]

        if len(self.num_cols) == 1 and len(self.dt_cols) == 1 and len(self.cat_cols) == 1:
            logger.debug("Case of 1 Categorical, 1 numeirc and 1 datetime")
            
            try:
                linechart = get_3d_multiple_lines(self.df, self.cat_cols, self.dt_cols, self.num_cols)
                graphs_list.append({"type": "Line_Chart", "graph": linechart})
            except Exception as e:
                logger.warning(f"Error generating 3d multiple lines - {str(e)}")

            try:
                barchart = get_3d_multiple_bars(self.df, self.cat_cols, self.dt_cols, self.num_cols)
                graphs_list.append({"type": "Vertcial_Grouped_Barchart", "graph": barchart})
            except Exception as e:
                logger.warning(f"Error generating 3d multiple bars group - {str(e)}")
            
            try:
                barchart_2 = get_3d_multiple_bars(self.df, self.cat_cols, self.dt_cols, self.num_cols, barmode="stack")
                graphs_list.append({"type": "Vertcial_Stacked_Barchart", "graph": barchart_2})
            except Exception as e:
                logger.warning(f"Error generating 3d multiple bars stack - {str(e)}")
            
            try:
                areachart = get_3d_multiple_lines(self.df, self.cat_cols, self.dt_cols, self.num_cols, draw_area=True)
                graphs_list.append({"type": "Area_Chart", "graph": areachart})
            except Exception as e:
                logger.warning(f"Error generating 3d area chart - {str(e)}")
        
        print(f"3D CHECK: num={len(self.num_cols)}, cat={len(self.cat_cols)}")  #
        if len(self.num_cols) == 1 and len(self.cat_cols) == 2:
            logger.debug("Case of 2 Categorical and 1 numeirc")
            print("3d cols................")
            print(f"3D DEBUG: cat_cols={self.cat_cols}, num_cols={self.num_cols}")

            grouped_bars = get_3d_cat_bars(self.df, self.cat_cols, self.num_cols)
            graphs_list.append({"type": "Vertical_Grouped_Barchart", "graph": grouped_bars})

            stacked_bars = get_3d_cat_bars(self.df, self.cat_cols, self.num_cols, barmode="stack")
            graphs_list.append({"type": "Vertical_Stacked_Barchart", "graph": stacked_bars})

            grouped_bars = get_3d_cat_bars(self.df, self.cat_cols, self.num_cols, orientation="h")
            graphs_list.append({"type": "Horizontal_Grouped_Barchart", "graph": grouped_bars})

            stacked_bars = get_3d_cat_bars(self.df, self.cat_cols, self.num_cols, barmode="stack", orientation="h")
            graphs_list.append({"type": "Horizontal_Stacked_Barchart", "graph": stacked_bars})

            if self.df.shape[0] < 15:
                graphs_list = [graphs_list[2], graphs_list[3], graphs_list[1], graphs_list[0]]
            elif self.df.shape[0] < 20:
                graphs_list = [graphs_list[1], graphs_list[3], graphs_list[0], graphs_list[2]]

            try:
                print("3d treemap calling........")
                treemap = get_3d_treemap(self.df, self.cat_cols, self.num_cols)
                graphs_list.append({"type": "Treemap", "graph": treemap})
            except:
                pass

        return graphs_list


    def get_4d_plus_graphs(self):
        return []

    
    def get_5d_plus_graphs(self):
        return []

        
        
