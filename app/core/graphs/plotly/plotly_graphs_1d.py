import random
import plotly.graph_objects as go
import pandas as pd

from .helper import color_palette

def get_gauge_chart(df: pd.DataFrame, num_cols: list, title: str | None = None):
    color_s = [color_palette[0], color_palette[12], color_palette[3]]
    random.shuffle(color_s)
    print("num_cols",num_cols)
    print("df",df)

    if not title:
        title_text = " ".join(num_cols[0].split()[:3]) + "<br>" + " ".join(num_cols[0].split()[3:])
    else:
        title_text = title

    fig = go.Figure(go.Indicator(
        # mode="gauge+number",
        mode = "number",
        number = {"font_size": 36},
        value=df.iloc[0][num_cols[0]],
        # title={'text': f"{num_cols[0]}"},
        title = {"text":title_text, "font_size":20}
        ))
        
    print(fig)
    return fig
