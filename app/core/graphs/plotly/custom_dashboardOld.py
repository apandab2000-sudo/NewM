import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import plotly.express as px
from itertools import product

from .helper import DataCorrection, color_palette, get_dticks, get_bargap

##########1)colour change - 8-06
def get_ranked_bar_colors(n: int):
    """
    Returns clean dashboard-friendly colors for ranked bar charts.
    Works well for vertical and horizontal bar charts.
    """
    beautiful_palette = [
        "#0D5265",  # deep teal
        "#00739D",  # ocean blue
        "#01A982",  # green
        "#32DAC8",  # aqua
        "#7630EA",  # purple
        "#C140FF",  # violet
        "#FF8300",  # orange
        "#FEC901",  # yellow
        "#00C8FF",  # sky blue
        "#6633BC",  # royal purple
        "#008567",  # dark green
        "#C54E4B",  # muted red
        "#FC5A5A",  # coral
        "#FFEB59",  # light yellow
        "#8D741C",  # brown-gold
        "#00E8CF"   # cyan
    ]

    return [beautiful_palette[i % len(beautiful_palette)] for i in range(n)]

######end

def get_2d_bar_chart(df: pd.DataFrame, numerical_columns: list,  datetime_columns: list = [], 
    categorical_columns: list = [], graph_label=''):
    
    cat_cols = categorical_columns
    date_cols = datetime_columns
    num_cols = numerical_columns
    orientation = "v" 
    
    if len(cat_cols) > 0:
        primary_col = cat_cols[0]
    else:
        primary_col = date_cols[0]

    tooltip_list = [primary_col]
    fig = go.Figure()

    if orientation == "v":
        hovertemplate = primary_col + "=%{customdata[0]}: <br>" + num_cols[0] + "=%{y}<br><br>"
        fig.add_trace(
            go.Bar(
                x=df[primary_col],
                y=df[num_cols[0]],
                marker_color=color_palette[0],
                # texttemplate="%{y}",
                texttemplate="%{y:.2s}",
                customdata=df[tooltip_list],
                hovertemplate=hovertemplate,
                name="."
            )
        )
        if len(cat_cols) > 0:
            fig.update_xaxes(
                tickvals=list(range(df.shape[0])),
                ticktext=[label if len(label) <= 20 else label[:20] for label in df[primary_col].values.tolist()]
            )
        if len(cat_cols) > 0:
            fig.update_xaxes(title=primary_col, linewidth=1.2)
        else:
            d_ticks = get_dticks(df, date_cols[0])
            fig.update_xaxes(title=date_cols[0], linewidth=1.2, showgrid=False, tick0=df[date_cols[0]].min(),
                             tickformat="%b %Y", dtick=d_ticks)
        fig.update_yaxes(title=num_cols[0], showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    else:
        # Sorting for horizontal graph
        df["dummy"] = df.loc[:, num_cols].sum(axis=1)
        df = df.sort_values("dummy", ascending=True)
        df = df.drop("dummy", axis=1)

        hovertemplate = primary_col + "=%{customdata[0]}: <br>" + num_cols[0] + "=%{x}<br><br>"
        fig.add_trace(
            go.Bar(
                y=df[primary_col],
                x=df[num_cols[0]],
                marker_color=color_palette[0],
                # texttemplate="%{x}",
                texttemplate="%{x:.2s}",
                customdata=df[tooltip_list],
                hovertemplate=hovertemplate,
                orientation="h",
                name="."
            )
        )
        if len(cat_cols) > 0:
            fig.update_yaxes(
                tickvals=list(range(df.shape[0])),
                ticktext=[label if len(label) <= 30 else label[:30] for label in df[primary_col].values.tolist()]
            )
        fig.update_yaxes(title=primary_col, linewidth=1.2, ticklabelstandoff=10)
        fig.update_xaxes(title=num_cols[0], showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        # fig.update_layout(yaxis=dict(autorange="reversed"))
    num_unique = df.shape[0]
    gap = get_bargap(num_unique, orientation=orientation)
    if graph_label:
        text = graph_label

    fig.update_layout(bargap=gap, title=text)
    return fig

def get_4d_plus_choropleth_map(df, numerical_columns, categorical_columns, graph_label=''):
    if graph_label:
        text = graph_label
    else:
        text = f"{', '.join(numerical_columns).replace('_', ' ')} by Country"
    fig = px.choropleth(
        df,
        locations=categorical_columns[0],
        locationmode='country names',
        color=numerical_columns[0],
        hover_name=categorical_columns[0],
        color_continuous_scale="Mint",
        title=text,
        #labels={col: col.replace('_', ' ') for col in numerical_columns}
    )

    # Add dropdown for numerical columns
    fig.update_layout(
        updatemenus=[{
            "buttons": [
                {
                    "method": "update",
                    "label": col.replace('_', ' '),
                    "args": [
                        {"z": [df[col]], "color": [df[col]]}
                    ]
                } for col in numerical_columns
            ],
            "x": 1,
            "y": 1,
            "showactive": True,
        }],
        coloraxis_colorbar=dict(
            title=""  # Setting an empty title to hide the name above the color bar
        )
    )

    fig.update_geos(
        showland=True,
        landcolor='lightgray',
        subunitcolor='gray',
        countrycolor='gray',
        showframe=False
    )
    
    return fig

def get_4d_plus_choropleth_map1(df, numerical_columns, categorical_columns, graph_label=''):
    # categorical_col = df.select_dtypes(include='object').columns.tolist()
    # numerical_cols = df.select_dtypes(include='number').columns.tolist()

    fig = go.Figure()

    # Create traces for each numerical column
    for i, col in enumerate(numerical_columns):
        fig.add_trace(
            go.Choropleth(
                locations=df[categorical_columns[0]],
                locationmode='country names',
                z=df[col],
                hoverinfo='location+z',
                colorbar_title=col,
                colorscale="Mint",  # You can customize the colorscale
                visible=(i==0),  # Only the first trace is visible initially
                
            )
        )

    # Create update menus for filtering the numerical columns
    updatemenus = [
        {
            "buttons": [
                {
                    "method": "update",
                    "label": col,
                    "args": [
                        {"visible": [j == i for j in range(len(numerical_columns))]},  # Show only the selected column
                    ],
                } for i, col in enumerate(numerical_columns)
            ],
            "x": 1,
            "y": 1,
            "showactive": True,
        }
    ]

    if graph_label:
        text = graph_label
    else:
        text = f"{', '.join(numerical_columns).replace('_', ' ')} by {categorical_columns[0]}"
    # Add filters with improved styling
    fig.update_layout(
        coloraxis_colorbar=dict(
            title=""  # Setting an empty title to hide the name above the color bar
        ),
        updatemenus=updatemenus,
        #title='Total Invites and Responses by Country',
        title=dict(
                text=text,  # Title text
                x=0,
                y=0.96,
                font_color="#1E78B4",
                #xanchor="left",
                font_size=10,
                font_weight=800
            ),
        geo=dict(
            scope='world',
            showland=True,
            landcolor='lightgray',
            subunitcolor='gray',
            countrycolor='gray',
            showframe=False, 
        )
    )
    return fig


def get_3d_bar_and_line_chart(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    temp = df.copy()
    n_col_1, n_col_2 = numerical_columns
    c_col = categorical_columns[0]

    x_axis_labels = temp[c_col].values.tolist()
    hovertext_1 = [f"{label}: {value}" for label, value in zip(x_axis_labels, temp[n_col_1].values.tolist())]
    hovertext_2 = [f"{label}: {value}" for label, value in zip(x_axis_labels, temp[n_col_2].values.tolist())]

    num_unique = df[c_col].nunique()
    gap = get_bargap(num_unique)

    fig = go.Figure()

    fig.add_trace(go.Bar(x=temp[c_col], y=temp[n_col_1],
                     name=n_col_1, marker_color=color_palette[1],
                    #  texttemplate="%{y}",
                     texttemplate="%{y:.2s}",
                     text=temp[n_col_1],
                     textposition="auto",
                     hovertext=hovertext_1,
                     hoverinfo="text"
                     ))
    fig.add_trace(go.Scatter(x=temp[c_col], y=temp[n_col_2],
                         mode='lines+markers+text', line=dict(shape="spline"),
                         name=n_col_2, marker_color=color_palette[3],
                        #  texttemplate="%{y}",
                         texttemplate="%{y:.2s}",
                         text=temp[n_col_2],
                         textposition="top center",
                         hovertext=hovertext_2,  
                         hoverinfo="text"
                         ))
    if graph_label:
        text = graph_label
    else:
        text= f"{n_col_1}, {n_col_2} across {c_col}"
    fig.update_layout(
        yaxis=dict(title=n_col_1 + "<br> and " + n_col_2),
        xaxis=dict(title=c_col),
        title=text,
        bargap=gap
    )

    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2,
                     tickvals=list(range(len(x_axis_labels))),  # Position of ticks
                    ticktext = [
                        label if isinstance(label, str) and len(label) <= 20 else (label[:20] if isinstance(label, str) else label) 
                        for label in x_axis_labels
                    ]
                    # ticktext = [
                    #     label if isinstance(label, str) and len(label) <= 14 else (label[:12] + '..' if isinstance(label, str) else label) 
                    #     for label in x_axis_labels
                    # ]
                     )
    fig.update_traces(cliponaxis=False)
    return fig

def get_quarter(x):
    if x.month == 1:
        return "Q1 " + str(x.year)
    if x.month == 4:
        return "Q2 " + str(x.year)
    if x.month == 7:
        return "Q3 " + str(x.year)
    if x.month == 10:
        return "Q4 " + str(x.year)
    return x

def get_3d_sunburst_custom(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    print(df.dtypes)
    print(numerical_columns, categorical_columns)
    # print(df)
    text = ''

    # if graph_label == 'Sentiment Distribution for Previous Quarter (Official vs Un-Official)':
    #     text = 'Sentiment Distribution for Previous Quarter (Official vs Un-Official)'
    # else:
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            text = graph_label
    else:
        text = f'{categorical_columns[1]} by {categorical_columns[0]}'
    df['Percentage'] = (df[numerical_columns[0]] / df[numerical_columns[0]].sum()) * 100
    fig = px.sunburst(
        df,
        path=[categorical_columns[0], categorical_columns[1]],  # Define the hierarchy levels
        values=numerical_columns[0],                 # Define the value for each slice (can also use 'Percentage' if preferred)
        hover_data={'Percentage': True, **{numerical_columns[0]: False}},      # Show percentage on hover
        color_discrete_sequence=color_palette,
        title=text,
    ) # color_palette[::2]

    fig.update_traces(
        insidetextorientation='auto',  # Automatically adjust text orientation
        textfont=dict(size=10),  # Set font size for readability
        selector=dict(type='sunburst')  # Apply changes to sunburst chart
    )

    return fig

def get_4d_cat_bars(df: pd.DataFrame, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], barmode: str = "group",
                    orientation="v", tooltip_list=None, graph_label=''):
    
    temp = df.copy()
    num_unique = temp[categorical_columns[0]].nunique()
    x_axis_labels = temp[categorical_columns[0]].values.tolist()
    
    gap = get_bargap(num_unique, orientation)

    fig = go.Figure()
    for i, n in enumerate(numerical_columns):
        hovertext_1 = [f"{label}, {value}" for label, value in zip(x_axis_labels, temp[n].values.tolist())]
        fig.add_trace(go.Bar(x=temp[categorical_columns[0]], y=temp[n], 
                             marker_color=color_palette[i], name=n, 
                             textfont_color = "#666666", 
                            #  texttemplate = "%{y}",
                             texttemplate="%{y:.2s}",
                             text = temp[n],
                             textposition="outside",
                             hovertext=hovertext_1,  # Full label appears on hover
                             hoverinfo="text"  # Ensure hover shows the full label
                             ))
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            text = graph_label 
    else:
        text = f'{categorical_columns[0]} vs {", ".join(numerical_columns)}'
    fig.update_layout(
        title=text,
        yaxis=dict(title=f"{', '.join(numerical_columns)}"), #<br>
        xaxis=dict(title=categorical_columns[0]),
        bargap=gap
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    # fig.update_xaxes(linewidth=1.2)
    fig.update_xaxes(
        linewidth=1.2,
        tickvals=list(range(len(x_axis_labels))),  # Position of ticks
        ticktext=[
            label if len(label) <= 20 else label[:20] for label in x_axis_labels
        ],  # Show full label if it's short, else show a shortened version
        #tickangle=-45  # Rotate labels for better visibility
    )
    fig.update_traces(cliponaxis=False)
    return fig


def get_4d_plus_stacked_area_graph(df, numerical_columns, datetime_columns, graph_label=''):
    date_column = datetime_columns[0]

    # df[date_column] = pd.to_datetime(df[date_column], errors='coerce')

    # alternate_colors = color_palette[::2]
    
    fig = go.Figure()

    for i, col in enumerate(numerical_columns):
        fig.add_trace(go.Scatter(
            x=df[date_column], y=df[col],
            mode='lines', name=col,
            line=dict(width=0.5, color=color_palette[i]),
            fill='tonexty'
        ))

    if graph_label:
        text = graph_label
    else:
        text = f'{", ".join(numerical_columns)} across {date_column}'
    fig.update_layout(
        title=text,
        xaxis_title=date_column,
        yaxis_title=", ".join(numerical_columns),
        showlegend=True,
        hovermode="x unified"
    )

    return fig

def create_lines_plot(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    d_col = datetime_columns[0]
    fig = go.Figure()
    # Convert numerical x-axis to string for categorical display
    #if datetime_columns:
    df[d_col] = df[d_col].astype(str)
    for i, col in enumerate(numerical_columns):
        fig.add_trace(go.Scatter(
            x=df[d_col], y=df[col],
            mode='lines+markers+text', name=col,
            line=dict(width=0.8, color=color_palette[i], shape="spline")
        )) #color_palette[::2][i]
    if graph_label:
        text = graph_label
    else:
        text = f'{", ".join(numerical_columns)} across {d_col}'
    
    fig.update_layout(
        title=text, 
        xaxis_title=d_col,
        yaxis_title=f"{', '.join(numerical_columns)}",#<br>
        showlegend=True,
        hovermode="x unified"
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(linewidth=1.2, showgrid=False, tick0=df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    

    # d_ticks = get_dticks(df, d_col)
    # fig.update_xaxes(title=d_col, linewidth=1.2, showgrid=False, tick0=df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    return fig

def get_bargap(num_unique: int, orientation="v"):
    if orientation == "v":
        if num_unique < 3:
            gap = 0.8
        elif num_unique < 5:
            gap = 0.6
        elif num_unique < 10:
            gap = 0.5
        elif num_unique <= 15:
            gap = 0.2
        else:
            gap = None
    else:
        if num_unique < 3:
            gap = 0.6
        elif num_unique < 5:
            gap = 0.5
        else:
            gap = None
    return gap

def get_2d_donut_chart(df: pd.DataFrame, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            text = graph_label
    else:
        text = f"{numerical_columns[0]} across {categorical_columns[0]}"
    df = df.sort_values(categorical_columns[0])
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=df[categorical_columns[0]], values=df[numerical_columns[0]], hole=0.5,
                    name=text, 
                         marker_colors = color_palette, textinfo='label+percent',
                        textposition="outside",
                        hovertemplate='%{label}<br>Count: %{value}<br>Percent: %{percent}'))
    fig.update_layout(showlegend=False, title=text)
    return fig #color_palette[::-2]

def get_2d_pie_chart(df: pd.DataFrame, num_cols, cat_cols, graph_label=''):
    if graph_label:
        text = graph_label
    else:
        text = f"{num_cols[0]} across {cat_cols[0]}"
    fig = go.Figure(data=go.Pie(labels=df[cat_cols[0]], values=df[num_cols[0]], marker_colors=[color_palette[-1], color_palette[5], color_palette[0]], 
                                hovertemplate='%{label}<br>Count: %{value}<br>Percent: %{percent}'))
    fig.update_layout(title=text)
    return fig

def get_2d_vertical_bar_chart(df: pd.DataFrame, numerical_columns: list=[], categorical_columns: list=[], datetime_columns: list=[], graph_label=''):
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    
    # color_s = [color_palette[0], color_palette[8], color_palette[3]]
    # random.shuffle(color_s)
    x_axis_labels = df[categorical_columns[0]].values.tolist()
    hovertext_1 = [f"{label}, {value}" for label, value in zip(x_axis_labels, df[numerical_columns[0]].values.tolist())]
    #old code-
    # fig = go.Figure(data=go.Bar(x=df[categorical_columns[0]], y=df[numerical_columns[0]],
    #                             marker_color=color_palette[0],
    #                             name=categorical_columns[0],
    #                             hovertext=hovertext_1,  # Full label appears on hover
    #                             hoverinfo="text",  # Ensure hover shows the full label
    #                             text=df[numerical_columns[0]],
    #                             textposition="outside",
    #                             showlegend=False
    #                             ))
    #######2) colour change- -06
    bar_colors = get_ranked_bar_colors(len(df))

    fig = go.Figure(data=go.Bar(
        x=df[categorical_columns[0]],
        y=df[numerical_columns[0]],
        marker_color=bar_colors,
        marker_line_color="white",
        marker_line_width=1,
        name=categorical_columns[0],
        hovertext=hovertext_1,
        hoverinfo="text",
        text=df[numerical_columns[0]],
        textposition="outside",
        textfont=dict(color="#444444", size=10),
        showlegend=False
    ))
    ###### change end
    
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"

    fig.update_layout(
        title=title_text,
        xaxis=dict(title=categorical_columns[0]),
        yaxis=dict(title=numerical_columns[0]),
        bargap=gap
    )
    fig.update_xaxes(
        showgrid=False,
        linewidth=0.8,
        tickvals=list(range(len(x_axis_labels))),  # Position of ticks
        ticktext=[
            label if len(label) <= 20 else label[:20] for label in x_axis_labels
        ],  # Show full label if it's short, else show a shortened version
        #tickangle=-45  # Rotate labels for better visibility
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_traces(cliponaxis=False)
    return fig

def get_pretto_chart_custom(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    df["dummy"] = df.loc[:, numerical_columns].sum(axis=1)
    df = df.sort_values("dummy", ascending=False)
    df = df.drop("dummy", axis=1)
    text = ''
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    df["cum_sum"] = df[numerical_columns[0]].cumsum()
    df["percentage"] = round(df["cum_sum"] / df[numerical_columns[0]].sum() * 100)
    average = round(df[numerical_columns[0]].mean(), 2)

    x_axis_labels = df[categorical_columns[0]].values.tolist()
    hovertext_1 = [f"{label}, {value}" for label, value in zip(x_axis_labels, df[numerical_columns[0]].values.tolist())]
    hovertext_2 = [f"{label}, {value}" for label, value in zip(x_axis_labels, df["percentage"].values.tolist())]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df[categorical_columns[0]], y=df[numerical_columns[0]], 
                         yaxis="y",
                         name=numerical_columns[0], marker_color=color_palette[0], 
                        textfont_color = "#666666",
                        text = df[numerical_columns[0]], 
                        # texttemplate = "%{y}",
                        texttemplate="%{y:.2s}",
                        textposition = "outside",
                        hovertext=hovertext_1,  # Full label appears on hover
                        hoverinfo="text"  # Ensure hover shows the full label
                        ),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df[categorical_columns[0]], y=df["percentage"], 
                             yaxis="y2", line=dict(shape="spline"),
                            #  mode = "lines+markers+text",
                            mode = "lines+markers",
                             name="cumulative_percentage", marker_color=color_palette[-3], 
                             textfont_color = "#666666",
                            #  text = df["percentage"], texttemplate = "%{y}", 
                             textposition = "top center",
                             hovertext=hovertext_2,  # Full label appears on hover
                             hoverinfo="text"  # Ensure hover shows the full label
                             ),
                  secondary_y=True)
    fig.add_hline(average, annotation_text=f"Avg({numerical_columns[0]}) = {average}", line_dash="dash", line_color="#DCDCDC",
                  annotation_position="right top")
    # if graph_label == 'Top 20 Themes in Previous Quarter (Official)':
    #     text='Top 20 Themes in Previous Quarter (Official)'
    # elif graph_label == 'Top 30 Sub Themes in Previous Quarter (Official)':
    #     text='Top 30 Sub Themes in Previous Quarter (Official)'
    # else:
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in datetime_columns[0].lower():
                text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            text = graph_label
    else:
        text = f"{numerical_columns[0]} across {categorical_columns[0]}"
    fig.update_layout(
        title=text,
        yaxis=dict(title=numerical_columns[0]),
        yaxis2=dict(title="cumulative_percentage"),
        xaxis=dict(title=categorical_columns[0]),
        bargap=gap
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    # fig.update_xaxes(linewidth=1.2)
    fig.update_xaxes(linewidth=1.2,
                    ticklabelstandoff=10,
                    tickvals=list(range(len(x_axis_labels))),  # Position of ticks
                    ticktext=[
                        label if len(label) <= 20 else label[:20] for label in x_axis_labels
                    ]
                    )
    fig.update_traces(cliponaxis=False)
    return fig

def get_combined_pretto_and_vertical_stack_chart_custom(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    # Aggregate and sort data by Theme
    theme_counts = (
        df.groupby(categorical_columns[0])[numerical_columns[0]].sum()
        .reset_index()
        .sort_values(by=numerical_columns[0], ascending=False)
    )
    
    # Calculate cumulative count and cumulative percentage
    theme_counts["Cumulative_Count"] = theme_counts[numerical_columns[0]].cumsum()
    theme_counts["Cumulative_Percentage"] = (
        theme_counts["Cumulative_Count"] / theme_counts[numerical_columns[0]].sum() * 100
    )
    
    # Average line
    average = round(theme_counts[numerical_columns[0]].mean(), 2)

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Add stacked bar traces
    # sentiments = df["Sentiment"].unique()
    # "#01A982", "#FF8300", "#00739D"
    sentiment_order = ["Negative", "Neutral", "Positive", "Mixed"]
    color_palette_sentiment = [color_palette[1], color_palette[2], color_palette[0], color_palette[3]] #["#FF8300", "#00739D", "#01A982"] #["#FF8300", "#00739D", "#01A982"]  # Colors for sentiments
    
    sentiment_colors = {
        "Negative": color_palette[1], 
        "Neutral": color_palette[2], 
        "Positive": color_palette[0], 
        "Mixed": color_palette[3]
    }
    # Reorder the sentiment data based on the theme_counts order
    theme_order = theme_counts[categorical_columns[0]].values
    theme_order_mapping = {theme: index for index, theme in enumerate(theme_order)}

    
    for i, sentiment in enumerate(df[categorical_columns[1]].unique()):
        # sentiment = row["Sentiment"] 
        sentiment_data = df[df[categorical_columns[1]] == sentiment]
        customdata = sentiment_data[[categorical_columns[0], numerical_columns[0]]].copy()
        customdata["Sentiment"] = sentiment
        customdata = customdata.to_numpy()

        fig.add_trace(
            go.Bar(
                x=sentiment_data[categorical_columns[0]],
                y=sentiment_data[numerical_columns[0]],
                name=sentiment,
                marker_color=sentiment_colors[sentiment],
                text=sentiment_data[numerical_columns[0]],
                # texttemplate="%{y}",
                texttemplate="%{y:.2s}",
                # hovertemplate= "Theme: %{x}<br>Sentiment Count: %{y}",
                customdata=customdata,
                hovertemplate=(
                    r"Theme: %{customdata[0]}"
                    r"<br>Sentiment Count: %{customdata[1]}"
                    r"<br>Sentiment: %{customdata[2]}"
                    r"<extra></extra>"
                ),
                textposition="auto"
            ),
            secondary_y=False,
        )
    
    fig.update_layout(
        xaxis=dict(
            categoryorder="array",
            categoryarray=theme_order  # Set the sorted order of themes here
        )
    )
    # Add Pareto line
    fig.add_trace(
        go.Scatter(
            x=theme_counts[categorical_columns[0]],
            y=theme_counts["Cumulative_Percentage"],
            mode="lines+markers",
            textfont_color = "#666666",
            name="Cumulative Percentage",
            # line=dict(color="orange", width=2),
            marker_color=color_palette[6],
            hovertemplate="Theme: %{x}<br>Cumulative Percentage: %{y:.2f}%",
        ),
        secondary_y=True,
    )

    # Add average line
    fig.add_hline(
        y=average,
        line_dash="dash",
        line_color="#DCDCDC",
        annotation_text=f"Avg({numerical_columns[0]}) = {average}",
        annotation_position="right top",
    )

    # Update layout
    # text = graph_label if graph_label else f"{numerical_columns[1]} across {categorical_columns[0]}"
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"

    x_vals = list(theme_order)
    tickvals = x_vals
    ticktext = [x if len(x) <= 20 else x[:20] for x in x_vals]

    # fig.update_xaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_yaxes(showgrid=False, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=0.8, showgrid=False)
    fig.update_layout(
        title=title_text,
        barmode="stack",
        xaxis_title=categorical_columns[0],
        yaxis_title=numerical_columns[0],
        yaxis2=dict(title="Cumulative Percentage"),
        xaxis_tickangle=45,
        xaxis=dict(
            categoryorder="array",
            categoryarray=theme_order,
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext
        )
    )
    
    fig.update_traces(cliponaxis=False)
    return fig

def get_2d_area_chart(df: pd.DataFrame, num_cols, datetime_columns):
    fig = go.Figure(
        data=go.Scatter(x=df[datetime_columns[0]], y=df[num_cols[0]], line=dict(shape="spline"),
                        fill="tonexty", mode="lines", line_color=color_palette[0]))
    fig.update_layout(
        title=f"{num_cols[0]} across {datetime_columns[0]}",
        yaxis=dict(title=num_cols[0]),
        xaxis=dict(title=datetime_columns[0])
    )
    return fig

def get_2d_horizontal_bar_chart(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    df["dummy"] = df.loc[:, numerical_columns].sum(axis=1)
    df = df.sort_values("dummy", ascending=True)
    df = df.drop("dummy", axis=1)

    num_unique = df.shape[0]
    gap = get_bargap(num_unique, orientation="h")
    y_axis_labels = df[categorical_columns[0]].values.tolist()
    hovertext_1 = [f"{label}, {value}" for label, value in zip(y_axis_labels, df[numerical_columns[0]].values.tolist())]
    #oldcode-
    # bar_colors = [color_palette[0] if value >= 0 else color_palette[1] for value in df[numerical_columns[0]]] ##added red color for negative values
    # fig = go.Figure(data=go.Bar(y=df[categorical_columns[0]], x=df[numerical_columns[0]],
    #                             textfont_color="#666666",
    #                             text=df[numerical_columns[0]], 
    #                             # texttemplate="%{x}",
    #                             texttemplate="%{x:.2s}",
    #                             textposition="outside",
    #                             textfont=dict(size=10),
    #                             orientation="h", marker_color=bar_colors,
    #                             hovertext=hovertext_1,  # Full label appears on hover
    #                             hoverinfo="text",  # Ensure hover shows the full label
    #                             showlegend=False
    #                             ))
    #######3) colour change- 8-06
    bar_colors = get_ranked_bar_colors(len(df))

    fig = go.Figure(data=go.Bar(
        y=df[categorical_columns[0]],
        x=df[numerical_columns[0]],
        text=df[numerical_columns[0]],
        texttemplate="%{x:.2s}",
        textposition="outside",
        textfont=dict(color="#444444", size=10),
        orientation="h",
        marker_color=bar_colors,
        marker_line_color="white",
        marker_line_width=1,
        hovertext=hovertext_1,
        hoverinfo="text",
        showlegend=False
    ))
    #####changes end


    
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"
    fig.update_layout(
        title=title_text,
        xaxis=dict(title=numerical_columns[0]),
        yaxis=dict(title=categorical_columns[0]),
        bargap=gap, showlegend=False
    )
    fig.update_xaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_yaxes(linewidth=1.2, 
                     ticklabelstandoff=10,
                     tickvals=list(range(len(y_axis_labels))),
                     ticktext = [
                        label if isinstance(label, str) and len(label) <= 30 else (label[:30] if isinstance(label, str) else label) 
                        for label in y_axis_labels
                    ]
                     )
                    
    fig.update_traces(cliponaxis=False)
    return fig

def get_custom_bar_chart_with_goal(df, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=''):
    
    fig = go.Figure()
    print(list(df[datetime_columns[0]].values))
    print(list(df[numerical_columns[0]].values))
    # date_str_list = [i.strftime('%b %Y') for i in list(df[datetime_columns[0]].values)]
    # print(date_str_list)
    # df[datetime_columns[0]] = df[datetime_columns[0]].astype(str)
    fig.add_trace(
        go.Bar(
            x=df[datetime_columns[0]],#df[datetime_columns[0]],
            y=df[numerical_columns[0]], #df[numerical_columns[0]],
            name="Selling Time %",
            text=[f"{v:.2f}%" for v in df[numerical_columns[0]]],
            textposition="auto",
            marker_color=color_palette[0],
            # width=0.4
        ),
    )

    
    goal = 65
    fig.add_shape(
        type="line",
        # x0=-0.5, x1=0.5,
        xref="x",
        yref="y",
        x0=df[datetime_columns[0]].min(),
        x1=df[datetime_columns[0]].max(),
        y0=goal, y1=goal,
        line=dict(color=color_palette[4], width=2),
        name='Goal'
    )

    fig.add_annotation(
        x=df[datetime_columns[0]].min(),
        y=goal,
        text=f"Goal {goal}%",
        showarrow=False,
        yshift=10,
        # font=dict(color=color_palette[4])
    )

    # df[datetime_columns[0]] = df[datetime_columns[0]].astype(str)
    d_ticks = get_dticks(df, datetime_columns[0])
    fig.update_xaxes(linewidth=1.2, showgrid=False, tick0=df[datetime_columns[0]].min(), tickformat="%b %Y", dtick=d_ticks)

    if graph_label:
        title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {datetime_columns[0]}"

    fig.update_layout(
        title=title_text,
        yaxis=dict(title=numerical_columns[0]),
        xaxis=dict(title=datetime_columns[0]),
        height=400
    )

    

    return fig

def get_2d_line_chart(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns:list=[], graph_label=''):
    negative_mask = df[numerical_columns[0]] < 0
    # red for negative values, blue for positive values
    colors = [color_palette[1] if is_negative else color_palette[0] for is_negative in negative_mask]

    fig = go.Figure(data=go.Scatter(x=df[datetime_columns[0]], y=df[numerical_columns[0]],
                                    textfont_color="#666666",
                                    text=df[numerical_columns[0]], 
                                    # texttemplate="%{y}",
                                    texttemplate="%{y:.2s}",
                                    textposition="top center",
                                    mode="lines+markers+text", 
                                    marker=dict(color=colors),
                                    line=dict(color=color_palette[1], width=2, shape="spline")))
    if graph_label:
        title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {datetime_columns[0]}"
    fig.update_layout(
        title=title_text,
        yaxis=dict(title=numerical_columns[0]),
        xaxis=dict(title=datetime_columns[0])
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2, showgrid=False)
    return fig

def get_2d_line_chart_cat(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns:list=[], graph_label=''):
    negative_mask = df[numerical_columns[0]] < 0
    # red for negative values, blue for positive values
    colors = [color_palette[1] if is_negative else color_palette[0] for is_negative in negative_mask]
    x_axis_labels = df[categorical_columns[0]].values.tolist()
    hovertext_1 = [f"{label}, {value}" for label, value in zip(x_axis_labels, df[numerical_columns[0]].values.tolist())]
    fig = go.Figure(data=go.Scatter(x=df[categorical_columns[0]], y=df[numerical_columns[0]],
                                    textfont_color="#666666",
                                    text=df[numerical_columns[0]], 
                                    # texttemplate="%{y}",
                                    texttemplate="%{y:.2s}",
                                    textposition="top center",
                                    mode="lines+markers+text", 
                                    marker=dict(color=colors),
                                    line=dict(color=color_palette[1], width=2, shape="spline"),
                                    hovertext=hovertext_1,  # Full label appears on hover
                                    hoverinfo="text"  # Ensure hover shows the full label
                                    ))
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"
    fig.update_layout(
        title=title_text,
        yaxis=dict(title=numerical_columns[0]),
        xaxis=dict(title=categorical_columns[0])
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2, showgrid=False,
                     tickvals=list(range(len(x_axis_labels))),  # Position of ticks
                    ticktext = [
                        label if isinstance(label, str) and len(label) <= 20 else (label[:20] if isinstance(label, str) else label) 
                        for label in x_axis_labels
                    ])
    fig.update_traces(cliponaxis=False)
    return fig

def get_2d_line_chart1(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns:list=[], graph_label=''):
    fig = go.Figure(data=go.Scatter(x=df[datetime_columns[0]], y=df[numerical_columns[0]],
                                        mode='lines+markers+text', 
                                       line=dict(color=color_palette[0], shape="spline"),
                                       textfont_color = "#666666",
                                        text = df[numerical_columns[0]], 
                                        # texttemplate = "%{y}", 
                                        texttemplate="%{y:.2s}",
                                        textposition = "top center"))
    if graph_label:
        text = graph_label
    else:
        text = f"{numerical_columns[0]} across {datetime_columns[0]}"
    fig.update_layout(
        title=text, 
        xaxis_title=datetime_columns[0],
        yaxis_title=numerical_columns[0],
    )
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2)
    return fig

def get_custom_gauge_chart1(df: pd.DataFrame, num_cols: list, graph_label=""):
    if graph_label:
        title_text = graph_label
    else:
        title_text = str(num_cols[0])
    col_name = ''
    if 'NPS' in df.columns:
        col_name = 'NPS'
    else:
        col_name = 'NSAT'
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        number = {"font_size": 64},
        value=df.iloc[0][col_name],
        gauge = {'axis': {'visible': False},'bar':{'color':'#003f88'}},
        delta = {'reference': df.iloc[1][col_name]},
        title = {"text":"", "font_size":36}
        ))
    return fig

def get_custom_gauge_chart(df: pd.DataFrame, num_cols: list, graph_label=""):
    if graph_label:
        title_text = graph_label
    else:
        title_text = str(num_cols[0])
    col_name = ''
    col_name1 = ''
    if 'NPS' in df.columns:
        col_name = 'NPS'
        col_name1 = 'Fiscal Year'
        # df_sorted = df.sort_values(by=col_name1, ascending=False)
        df = df.dropna(subset=[col_name1])
    else:
        col_name = 'NSAT'
        # col_name1 = 'Fiscal Quarter'
        if 'Fiscal Quarter' in df.columns:
            col_name1 = 'Fiscal Quarter'
            df[col_name1] = pd.to_datetime(df[col_name1]).dt.strftime('%Y-%m-%d')
        else:
            col_name1 = 'Fiscal Year'
        # df[col_name1] = pd.to_datetime(df[col_name1]).dt.strftime('%Y-%m-%d')
        # df_sorted = df.sort_values(by=col_name1, ascending=False)
        df = df.dropna(subset=[col_name1])
    fig = go.Figure(go.Indicator(
        mode = "number+delta",
        value = df.iloc[-1][col_name],  # Current NSAT value
        delta = {"reference": df.iloc[-2][col_name], "valueformat": ".0f"},  # Previous NSAT value for delta
        number={"font": {"color": color_palette[1], "size": 64}},
        title = {"text": title_text, "font": {"size": 30}},
        domain = {'y': [0, 1], 'x': [0.25, 0.75]}  # Positioning of the gauge
    ))
    # Add a scatter plot for NSAT over fiscal quarters
    fig.add_trace(go.Scatter(
        x = df[col_name1],  # Use Fiscal_Quarter as x-axis
        y = df[col_name],  # Plot NSAT values
        mode = 'lines',
        name = col_name,
        line=dict(color='#D3D3D3'),  # Color of the trend line
    ))
    # Update layout settings
    fig.update_layout(
        template="simple_white",
        # title="NSAT Indicator Chart",  # Chart title
        xaxis=dict(
            showticklabels=False,  # Hide x-axis tick labels
            showgrid=False,        # Hide x-axis gridlines
            zeroline=False,        # Hide x-axis zero line
            showline=False,
            ticks="" # Hide x-axis line
        ),
        yaxis=dict(
            showticklabels=False,  # Hide y-axis tick labels
            showgrid=False,        # Hide y-axis gridlines
            zeroline=False,        # Hide y-axis zero line
            showline=False,
            ticks="" # Hide y-axis line
        )
    )
    return fig


def get_custom_multiline_scatter_graph(df, graph_label=""):
    df["Fiscal Quarter"] = pd.to_datetime(df["Fiscal Quarter"]).dt.strftime('%Y-%m-%d')
    metrices = ["Ease and Speed of Quote Process eCommerce", "Ease and Speed of Quote Process GCPQ", 
            "Online Purchasing Experience", "Ease of Order Placement", "Information regarding the Order Status",
           "Order Care Agent / CSM (Customer Support Manager)", "Accuracy of Order Delivery", 
           "Speed of Order Delivery", "Accounts Operations Manager"]

    fig = make_subplots(rows=len(metrices), cols=2, shared_xaxes=True, column_widths=[0.9, 0.1], horizontal_spacing=0,
                        vertical_spacing=0, specs=[[{"type": "bar"}, {"type": "indicator"}] for i in range(len(metrices))])


    for i, metric in enumerate(metrices):
        temp = df[df["Metric"]==metric]
        fig.add_trace(go.Scatter(x=temp["Fiscal Quarter"], y=temp["NSAT"], 
                                mode="lines", name=metric, marker_color = color_palette[i]), row=i+1, col=1)
        fig.add_trace(go.Indicator(
                                mode = "number+delta",
                                number = {"font_size": 16},
                                value=temp.iloc[-1]["NSAT"],
                                delta = {'reference': temp.iloc[-2]["NSAT"], "position": "right"},
        ), row=i+1, col=2)
        fig.add_annotation( 
            x=0.05, y=temp["NSAT"].mean(),
                            text=metric+"  ", 
                            showarrow=False, xanchor='right', yanchor='middle',
                            row=i+1, col=1)
    if graph_label:
        title_text = graph_label
    else:
        title_text = ""

    fig.update_yaxes(showticklabels=False, ticks="", showline=False)
    fig.update_xaxes(type="category", ticks="", showline=False)
    # min_x = df["Fiscal Quarter"].min()
    # max_x = df["Fiscal Quarter"].max()
    # fig.update_xaxes(range=[min_x, max_x], ticks="", showline=False)
    # fig.update_xaxes(ticks="", showline=False)
    fig.update_layout(title_text="", showlegend=False, template="simple_white")
    return fig

def get_custom_multiline_scatter_graph_for_px(df, graph_label=""):
    # df["Fiscal Year"] = pd.to_datetime(df["Fiscal Year"]).dt.strftime('%Y-%m-%d')
    

    color_palette = [
        "#00296b", "#003f88", "#00509d", "#fdc500", "#ffd500","#67b99a","#469d89","#036666","#f9a620","#fa442a", "#00296b", "#003f88", "#00509d"
    ]

    col_name = ''
    if 'NPS' in df.columns:
        col_name = 'NPS'
        metrices =["Recommend HPE to your customers"]
    else:
        col_name = 'NSAT'
        metrices =["Partner Ready Portal", "Pricing Process", "Price Competitiveness", "Deal Registration", 
    "Order Care Support", "Order Status Information", "Product Delivery Experience",
    "Partner Compensation", "Physical Claims", "Financial Claims", 
    "Market Development Funds(MDF)", "Joint Business Planning (JBP)", "pAOM Interaction"]

    fig = make_subplots(rows=len(metrices), cols=2, shared_xaxes=True, column_widths=[0.9, 0.1], horizontal_spacing=0,
                        vertical_spacing=0, specs=[[{"type": "bar"}, {"type": "indicator"}] for i in range(len(metrices))])


    for i, metric in enumerate(metrices):
        temp = df[df["Metric"]==metric]
        fig.add_trace(go.Scatter(x=temp["Fiscal Year"], y=temp[col_name], 
                                mode="lines", name=metric, marker_color = color_palette[i]), row=i+1, col=1)
        fig.add_trace(go.Indicator(
                                mode = "number+delta",
                                number = {"font_size": 16},
                                value=temp.iloc[-1][col_name],
                                delta = {'reference': temp.iloc[-2][col_name], "position": "right"},
        ), row=i+1, col=2)
        fig.add_annotation( 
            x=0.01, y=temp[col_name].mean(),
                            text=metric+"  ", 
                            showarrow=False, xanchor='right', yanchor='middle',
                            row=i+1, col=1)
    if graph_label:
        title_text = graph_label
    else:
        title_text = ""

    fig.update_yaxes(showticklabels=False, ticks="", showline=False)
    fig.update_xaxes(type="category", ticks="", showline=False)
    # min_x = df["Fiscal Quarter"].min()
    # max_x = df["Fiscal Quarter"].max()
    # fig.update_xaxes(range=[min_x, max_x], ticks="", showline=False)
    # fig.update_xaxes(ticks="", showline=False)
    fig.update_layout(title_text="", showlegend=False, template="simple_white")
    return fig

def get_3d_multiple_lines_date(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    d_col = datetime_columns[0]
    n_col = numerical_columns[0]
    c_col = categorical_columns[0]

    x_axis_labels = df[datetime_columns[0]].values.tolist()
    if graph_label:
        title_text = graph_label
        # print("************** title_text ************",title_text)
    else:
        title_text = f"{numerical_columns[0]} across {datetime_columns[0]}"
        # print("^^^^^^^^^^^^^^^ title_text ^^^^^^^^^^^^^^^^^^",title_text)

    x_axis_labels = df[datetime_columns[0]].values.tolist()

    if 'audience' in [i.lower() for i in categorical_columns]:
        color_mapping = {
            'HPE Customer': color_palette[0],
            'HPE Channel Partner': color_palette[1],
            'Others': color_palette[2],
            'HPE Operations': color_palette[0],
            'HPE Sales': color_palette[1],
            'Aruba Services': color_palette[2],
            'Aruba Sales': color_palette[3],
        }
    elif 'segment' in [i.lower() for i in categorical_columns]:
        color_mapping = {
            'HPE Core Business': color_palette[0],
            'HPE GreenLake': color_palette[1],
            'Both': color_palette[2]
        }
    else:
        color_mapping = {}
    if color_mapping:
        fig = px.line(data_frame=df, x=d_col, y=n_col, color=c_col, markers=True, text=n_col,
                        color_discrete_map=color_mapping, line_shape="spline")  # textposition="top center"
    else:
        fig = px.line(data_frame=df, x=d_col, y=n_col, color=c_col, markers=True, text=n_col,
                  color_discrete_sequence=color_palette, line_shape="spline")  # textposition="top center"
    # fig.update_layout(title=f"{n_col} by {c_col} across {d_col}")
    fig.update_layout(title=title_text)
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)

    df[d_col] = pd.to_datetime(df[d_col], errors='coerce')
    unique_dates = df[d_col].dropna().unique()
    # print("^^^^^^^^^^^^ unique_dates ^^^^^^^^^^",unique_dates)
    
    # if 'year' in d_col.lower():
    #     fig.update_xaxes(linewidth=0.8, showgrid=False, type='date', tickformat='%Y-%m-%d', tickvals=x_axis_labels,
    #                     ticktext=x_axis_labels)
    # else:
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(linewidth=0.8, showgrid=False, 
                        tick0=df[d_col].min(), tickformat="%b %Y", dtick=d_ticks)
    
    fig.update_traces(text=None, hovertemplate=f'{d_col}: %{{x}}<br>{n_col}: %{{y}}<br>{c_col}: %{{fullData.name}}')
    fig.update_traces(cliponaxis=False)
    return fig


def get_3d_vertical_bar_date(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    barmode="group"
    if barmode == "stack":
        num_unique = df[datetime_columns[0]].nunique()
    else:
        num_unique = df.shape[0]
    gap = get_bargap(num_unique)
    temp = df.copy()
    d_col = datetime_columns[0]
    n_col = numerical_columns[0]
    c_col = categorical_columns[0]

    tooltip_list = datetime_columns + categorical_columns + numerical_columns
    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, j in enumerate(df[c_col].unique()):
        temp = df[df[c_col] == j]
        fig.add_trace(
            go.Bar(
                x=temp[d_col],
                y=temp[n_col],
                # texttemplate="%{y}",
                texttemplate="%{y:.2s}",
                offsetgroup=i + 1,
                text=temp[n_col],
                marker_color=color_palette[i % len(color_palette)],#color_palette[i],
                customdata=temp[tooltip_list],
                hovertemplate=hover_template,
                name=j,
            )
        )
    fig.update_yaxes(
        title=n_col,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(
        title=d_col,
        linewidth=1.2,
        tick0=df[d_col].min(),
        tickformat="%b %Y",
        dtick=d_ticks
    )
    fig.update_layout(bargap=gap, barmode=barmode, title=graph_label)
    return fig

def get_3d_multiple_lines(df: pd.DataFrame, numerical_columns:list=[], datetime_columns:list=[], categorical_columns:list=[], graph_label=""):
    d_col = datetime_columns[0]
    n_col = numerical_columns[0]
    c_col = categorical_columns[0]

    fig = px.line(data_frame=df, x=d_col, y=n_col, color=c_col, markers=True, text=n_col,
                  color_discrete_sequence=color_palette, line_shape="spline")  # textposition="top center"
    if graph_label:
        title = graph_label
    else:
        title = f"{n_col} by {c_col} across {d_col}"
    fig.update_layout(title=title)
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)

    # unique_dates = df[d_col].dropna().unique()
    fig.update_xaxes(linewidth=0.8, showgrid=False)

    fig.update_traces(text=None, hovertemplate=f'{d_col}: %{{x}}<br>{n_col}: %{{y}}<br>{c_col}: %{{fullData.name}}')
    fig.update_traces(cliponaxis=False)
    return fig

def get_3d_linechart(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    temp = df.copy()
    n_col_1, n_col_2 = numerical_columns
 
    if categorical_columns:
        primary_col = categorical_columns[0]
        x_axis_labels = temp[primary_col].values.tolist()
        hovertext_1 = [f"{label}: {value}" for label, value in zip(x_axis_labels, temp[n_col_1].values.tolist())]
        hovertext_2 = [f"{label}: {value}" for label, value in zip(x_axis_labels, temp[n_col_2].values.tolist())]
    else:
        primary_col = datetime_columns[0]
        x_axis_labels = []
        hovertext_1, hovertext_2 = None, None
 
    temp = df.copy()
 
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=temp[primary_col], y=temp[n_col_1],
                             #  yaxis="y2",
                             name=n_col_1, mode='lines+markers+text',
                             line=dict(shape="spline"), marker_color=color_palette[0],
                            #  texttemplate="%{y}",
                             texttemplate="%{y:.2s}",
                             text=temp[n_col_1],
                             textposition="top center",
                             hovertext=hovertext_1 if hovertext_1 else None,
                             hoverinfo="text" if hovertext_1 else None
                             ))
 
    fig.add_trace(go.Scatter(x=temp[primary_col], y=temp[n_col_2],
                             #  yaxis="y2",
                             name=n_col_2, mode='lines+markers+text',
                             line=dict(shape="spline"), marker_color=color_palette[1],
                            #  texttemplate="%{y}",
                             texttemplate="%{y:.2s}",
                             text=temp[n_col_2],
                             textposition="top center",
                             hovertext=hovertext_2 if hovertext_2 else None,
                             hoverinfo="text" if hovertext_2 else None))
    fig.update_layout(
        yaxis=dict(title=n_col_1 + "<br> and " + n_col_2),
        xaxis=dict(title=primary_col), title=f"{n_col_1}, {n_col_2} across {primary_col}")
 
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    if x_axis_labels:
        fig.update_xaxes(linewidth=1.2, showgrid=False,
                         tickvals=list(range(len(x_axis_labels))),  # Position of ticks
                         ticktext=[
                             label if isinstance(label, str) and len(label) <= 20 else (
                                 label[:20] if isinstance(label, str) else label)
                             for label in x_axis_labels
                         ]
                         )
    else:
        fig.update_xaxes(linewidth=1.2, showgrid=False)
    fig.update_traces(cliponaxis=False)
    return fig


def get_3d_vertical_cat_bars(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    df["dummy"] = df.loc[:, numerical_columns].sum(axis=1)
    df = df.sort_values("dummy", ascending=False)
    df = df.drop("dummy", axis=1)
    
    barmode = "group"
    orientation = "v"

    n_col = numerical_columns[0]
    c_col_1, c_col_2 = categorical_columns

    # Determine primary and secondary categorical columns
    # if df[c_col_1].nunique() >= df[c_col_2].nunique():
        # primary_c_col = c_col_1
        # secondary_c_col = c_col_2
    # else:
    primary_c_col = c_col_2
    secondary_c_col = c_col_1

    # Add truncated column for display on x-axis
    # df['Attribute'] = df[primary_c_col].str[:10]  # Display only the first 10 characters
    df['Category'] = df[primary_c_col].apply(
        lambda label: label if isinstance(label, str) and len(label) <= 20 else (
            label[:20] if isinstance(label, str) else label
        )
    )

    # Calculate gap for bar chart
    num_unique = df.shape[0]
    gap = get_bargap(num_unique)

    # Sort values based on 'HPE Customer' if 'audience' exists
    audience_col = None
    for col in categorical_columns:
        if col.lower() == 'audience':
            audience_col = col
            break        

    if audience_col:
        df[audience_col] = pd.Categorical(
            df[audience_col],
            categories=['HPE Customer', 'HPE Channel Partner', 'Others', 'HPE Operations',
                        'HPE Sales', 'Aruba Services', 'Aruba Sales'],
            ordered=True
        )
        df = df.sort_values([audience_col, n_col], ascending=[True, False])
        color_mapping = {
            'HPE Customer': color_palette[0],
            'HPE Channel Partner': color_palette[1],
            'Others': color_palette[2],
            'HPE Operations': color_palette[0],
            'HPE Sales': color_palette[1],
            'Aruba Services': color_palette[2],
            'Aruba Sales': color_palette[3],
        }
        # Create the bar chart
        fig = px.bar(
            data_frame=df,
            x='Category',  # Use truncated labels for x-axis
            y=n_col,
            color=secondary_c_col,
            barmode=barmode,
            orientation=orientation,
            color_discrete_map=color_mapping,
            text=n_col,
            hover_data={primary_c_col: True},  # Include full labels in hover text
        )
    else:
        fig = px.bar(
            data_frame=df,
            x='Category',  # Use truncated labels for x-axis
            y=n_col,
            color=secondary_c_col,
            barmode=barmode,
            orientation=orientation,
            color_discrete_sequence=color_palette,
            text=n_col,
            hover_data={primary_c_col: True},  # Include full labels in hover text
        )

    fig.update_traces(textposition='outside')
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2)

    # Add title
    if graph_label:
        print(datetime_columns)
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"

    fig.update_layout(title=title_text, bargap=gap)
    fig.update_traces(cliponaxis=False)
    return fig

def get_3d_vertical_cat_bars1(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    barmode = "group"
    orientation ="v"

    n_col = numerical_columns[0]
    c_col_1, c_col_2 = categorical_columns

    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length >= c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1
    temp = df.copy()

    # if barmode == "stack":
    #     num_unique = temp[primary_c_col].nunique()
    # else:
    num_unique = temp.shape[0]
    # gap = get_bargap(num_unique, orientation)
    gap = get_bargap(num_unique)

    # if orientation == "v":
    fig = px.bar(data_frame=temp, x=primary_c_col, y=n_col, color=secondary_c_col,
                    barmode=barmode, orientation=orientation,
                    color_discrete_sequence=color_palette, text=n_col
                    )
    fig.update_traces(textposition='outside')
    fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    fig.update_xaxes(linewidth=1.2,
                        )

    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                title_text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                title_text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            title_text = graph_label
        # print("************** title_text ************",title_text)
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"
        # print("^^^^^^^^^^^^^^^ title_text ^^^^^^^^^^^^^^^^^^",title_text)

    # fig.update_layout(title=f"{n_col} across {c_col_1} and {c_col_2}", bargap=gap)
    fig.update_layout(title=title_text, bargap=gap)
    return fig


def get_3d_hori_cat_bars(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    df["dummy"] = df.loc[:, numerical_columns].sum(axis=1)
    df = df.sort_values("dummy", ascending=True)
    df = df.drop("dummy", axis=1)

    barmode = "group"
    orientation ="h"
    n_col = numerical_columns[0]
    c_col_1, c_col_2 = categorical_columns
    
    all_combinations = pd.DataFrame(list(product(df[c_col_1].unique(), df[c_col_2].unique())), columns=[c_col_1, c_col_2])
    df = all_combinations.merge(df, on=[c_col_1, c_col_2], how='left').fillna({n_col: 0})
    df[n_col] = df[n_col].astype(int)
    print(df)

    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length >= c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1

    temp = df.copy()

    if barmode == "group":
        num_unique = temp[primary_c_col].nunique()
    else:
        num_unique = temp.shape[0]
    # gap = get_bargap(num_unique, orientation)
    gap = get_bargap(num_unique)

    # Sort values based on 'HPE Customer' if 'audience' exists
    audience_col = None
    for col in categorical_columns:
        if col.lower() == 'audience':
            audience_col = col
            break
    
    if audience_col:
        temp[audience_col] = pd.Categorical(
            temp[audience_col],
            categories=['HPE Customer', 'HPE Channel Partner', 'Others', 'HPE Operations',
                        'HPE Sales', 'Aruba Services', 'Aruba Sales'],
            ordered=True
        )
        temp = temp.sort_values([audience_col, n_col], ascending=[True, True])

        color_mapping = {
            'HPE Customer': color_palette[0],
            'HPE Channel Partner': color_palette[1],
            'Others': color_palette[2],
            'HPE Operations': color_palette[0],
            'HPE Sales': color_palette[1],
            'Aruba Services': color_palette[2],
            'Aruba Sales': color_palette[3],
        }
        fig = px.bar(data_frame=temp, y=primary_c_col, x=n_col, color=secondary_c_col,
                    barmode=barmode, orientation=orientation,
                    color_discrete_map=color_mapping, text=n_col
                    )
    else:
        fig = px.bar(data_frame=temp, y=primary_c_col, x=n_col, color=secondary_c_col,
                    barmode=barmode, orientation=orientation,
                    color_discrete_sequence=color_palette, text=n_col
                    )

    fig.update_traces(textposition='outside')
    fig.update_xaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)  # need clarification
    fig.update_yaxes(linewidth=1.2, ticklabelstandoff=10, ticklen=0)

    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if df[d_col].nunique() == 1:
                # unique_value = df[d_col].unique()[0]
                unique_value = int(df[d_col].dropna().unique()[0])
                if 'year' in d_col.lower():
                    title_text = graph_label + " - " +'FY '+str(unique_value)
                elif 'quarter' in d_col.lower():
                    updated_unique_value = get_quarter(unique_value)
                    # df[d_col] = df[d_col].apply(get_quarter)
                    title_text = graph_label + " - " +str(updated_unique_value)
                else:
                    title_text = graph_label + " - " +str(unique_value)
        
        # if datetime_columns:
        #     d_col = datetime_columns[0]
        #     if 'year' in d_col.lower():
        #         title_text = graph_label + " - " +'FY '+str(int(df[d_col].unique()[0]))
        #     elif 'quarter' in d_col.lower():
        #         df[d_col] = df[d_col].apply(get_quarter)
        #         title_text = graph_label + " - " +str(df[d_col].unique()[0])
        #     else:
        #         title_text = graph_label + " - " +str(df[d_col].unique()[0])
        # else:
        #     title_text = graph_label
        # # print("************** title_text ************",title_text)
    else:
        title_text = f"{numerical_columns[0]} across {categorical_columns[0]}"
        # print("^^^^^^^^^^^^^^^ title_text ^^^^^^^^^^^^^^^^^^",title_text)

    # fig.update_layout(title=f"{n_col} across {c_col_1} and {c_col_2}", bargap=gap)
    fig.update_layout(title=graph_label, bargap=gap)
    # fig.update_layout(yaxis=dict(autorange="reversed"))

    return fig

def get_4d_multiple_lines(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label='',tooltip_list=None, draw_area=False):
    if tooltip_list is None:
        tooltip_list = []

    d_col = datetime_columns[0]
    n_col = numerical_columns[0]
    c_col = categorical_columns[0]

    hover_main = "%{y}<br>"
    hover_template_add = "<br>".join([f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, j in enumerate(df[c_col].unique()):
        temp = df[df[c_col] == j]
        fig.add_trace(
            go.Scatter(
                x=temp[d_col],
                y=temp[n_col],
                line=dict(shape="spline"),
                mode="lines+markers",
                marker_color=color_palette[i],
                customdata=temp[tooltip_list],
                hovertemplate=hover_template,
                name=j,
                fill="tonexty" if draw_area else None
            )
        )
    fig.update_yaxes(
        title=n_col,
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(
        title=d_col,
        linewidth=1.2,
        tick0=df[d_col].min(),
        # tickformat="%b %Y",
        tickformat="%b %Y",
        dtick=d_ticks
    )
    if graph_label:
        title = graph_label
    else:
        title = f'{n_col} across {d_col}'
    fig.update_layout(title=title)
    return fig


def get_4d_vertical_bar_chart(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], barmode: str = "group", graph_label='', tooltip_list=None):
    
    temp = df.copy()
    if tooltip_list is None:
        tooltip_list = []

    if barmode == "stack":
        num_unique = temp.shape[0]
    else:
        num_unique = temp.shape[0] * len(numerical_columns)
    gap = get_bargap(num_unique)

    if len(categorical_columns) > 0:
        c_col = categorical_columns[0]
    else:
        c_col = datetime_columns[0]

    hover_main = "%{y}<br><br>"
    hover_template_add = "<br>".join([f"{t}: " + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    # Add a trace for each numerical column
    for i, n_col in enumerate(numerical_columns):
        fig.add_trace(go.Bar(
            x=temp[c_col],
            y=temp[n_col],
            customdata=temp[tooltip_list],
            hovertemplate=hover_template,
            offsetgroup=i + 1,  # Offset groups for side-by-side bars
            name=n_col,
            marker_color=color_palette[i],
            text=temp[n_col],
            # texttemplate="%{y}",
            texttemplate="%{y:.2s}",
        ))
    fig.update_yaxes(
        title="<br>".join(numerical_columns),
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )

    if len(categorical_columns) > 0:
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tickvals=list(range(temp.shape[0])),
            ticktext=[label if len(label) <= 20 else label[:20] for label in temp[c_col].values.tolist()]
        )
    else:
        d_ticks = get_dticks(df, c_col)
        fig.update_xaxes(
            title=c_col,
            linewidth=1.2,
            tick0=df[c_col].min(),
            tickformat="%b %Y",
            dtick=d_ticks
        )
    if graph_label:
        title = graph_label
    # else:
    #     title = f"{n_col} by {c_col} across {d_col}"
    # fig.update_layout(title=title)
    fig.update_layout(bargap=gap, barmode=barmode, title=title, showlegend=True)
    return fig


def get_3d_cat_bars(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], barmode: str = "stack", orientation="v", graph_label=''):
    n_col = numerical_columns[0]
    c_col_1, c_col_2 = categorical_columns

    c_col_1_unique_length = df[c_col_1].nunique()
    c_col_2_unique_length = df[c_col_2].nunique()

    if c_col_1_unique_length >= c_col_2_unique_length:
        primary_c_col = c_col_1
        secondary_c_col = c_col_2
    else:
        primary_c_col = c_col_2
        secondary_c_col = c_col_1
    temp = df.copy()

    if barmode == "stack":
        num_unique = temp[primary_c_col].nunique()
    else:
        num_unique = temp.shape[0]
    gap = get_bargap(num_unique)

    tooltip_list = categorical_columns + numerical_columns

    fig = go.Figure()
    if orientation == "v":
        hover_main = "%{y}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
        hover_template = hover_main + hover_template_add

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            fig.add_trace(
                go.Bar(
                    x=temp2[primary_c_col],
                    y=temp2[n_col],
                    offsetgroup=i + 1,
                    marker_color=color_palette[i],
                    # texttemplate="%{y}",
                    texttemplate="%{y:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    name=j
                )
            )

        fig.update_yaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
        lables = []
        for i in temp[primary_c_col]:
            if i not in lables:
                lables.append(i)
        # print("^^^^^^^^^^^^^^ lables",lables)
        fig.update_xaxes(
            title=primary_c_col,
            linewidth=1.2,
            tickvals=list(range(temp[primary_c_col].nunique())),
            ticktext=[label if len(label) <= 20 else label[:20] for label in lables]
        )
    else:
        # Sorting for horizontal graph
        temp["dummy"] = temp.loc[:, numerical_columns].sum(axis=1)
        temp = temp.sort_values("dummy", ascending=True)
        temp = temp.drop("dummy", axis=1)

        hover_main = "%{x}<br>"
        hover_template_add = "<br>".join(
            [f"{t}=" + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
        hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
        hover_template = hover_main + hover_template_add

        for i, j in enumerate(temp[secondary_c_col].unique()):
            temp2 = temp[temp[secondary_c_col] == j]
            fig.add_trace(
                go.Bar(
                    y=temp2[primary_c_col],
                    x=temp2[n_col],
                    offsetgroup=i + 1,
                    marker_color=color_palette[i],
                    # texttemplate="%{x}",
                    texttemplate="%{x:.2s}",
                    text=temp2[n_col],
                    customdata=temp2[tooltip_list],
                    hovertemplate=hover_template,
                    orientation=orientation,
                    name=j
                )
            )
        fig.update_xaxes(title=n_col, showgrid=True, ticklabelstandoff=10, showline=False,
                         ticklen=0)  # need clarification
        lables = []
        for i in temp[primary_c_col]:
            if i not in lables:
                lables.append(i)

        fig.update_yaxes(
            title=primary_c_col,
            linewidth=1.2,
            ticklabelstandoff=10,
            tickvals=list(range(temp[primary_c_col].nunique())),
            ticktext=[label if len(label) <= 30 else label[:30] for label in lables]
        )
    # if graph_label:
    #     title = graph_label
    if graph_label:
        if datetime_columns:
            d_col = datetime_columns[0]
            if 'year' in d_col.lower():
                text = graph_label + " - " +'FY '+str(df[d_col].unique()[0])
            elif 'quarter' in d_col.lower():
                df[d_col] = df[d_col].apply(get_quarter)
                text = graph_label + " - " +str(df[d_col].unique()[0])
            else:
                text = graph_label + " - " +str(df[d_col].unique()[0])
        else:
            text = graph_label
    else:
        text = f"{numerical_columns[0]} across {categorical_columns[0]}"
    fig.update_layout(bargap=gap, barmode=barmode, title =text)
    return fig

def generate_custom_kpi_graphs(user_query: str, df: pd.DataFrame, graph_details = dict, python=False):
    dc = DataCorrection(df)
    dc.correct_columns_names()
    dc.extract_datatype_based_columns()
    dc.correct_data_with_datetime_columns()
    # dc.correct_categorical_long_context()
    
    # if rows > 20:
    #     df = df.iloc[:20]

    fig = None
    graph_type = graph_details["graph_type"]
    if "pretto_and_vertical_stack" in graph_type.lower() or "hori_cat_bars" in graph_type.lower():
        # df = dc.process_dataframe()
        df = dc.df
    else:
        df = dc.sorting_dataframe()
        # df = dc.process_dataframe()

    numerical_columns = dc.numerical_columns
    categorical_columns = dc.categorical_columns
    datetime_columns = dc.datetime_columns

    df = df.dropna(subset=categorical_columns+datetime_columns)

    df = df.replace({pd.NA: None})

    rows, columns = df.shape

    if datetime_columns:
        d_col = datetime_columns[0]
        if df[d_col].nunique() == 1:
            unique_value = df[d_col].unique()[0]
            if 'year' in d_col.lower():
                user_query = user_query + " - " +'FY '+str(unique_value)
            elif 'quarter' in d_col.lower():
                updated_unique_value = get_quarter(unique_value)
                # df[d_col] = df[d_col].apply(get_quarter)
                user_query = user_query + " - " +str(updated_unique_value)
            else:
                user_query = user_query + " - " +str(unique_value)
    print(user_query)
    graph_label = graph_details["graph_label"]
    show_legend = False if graph_details.get("show_legend", "").lower().strip() == "false" else True
    
    fig = eval(f'{graph_type}(df, numerical_columns=numerical_columns, datetime_columns=datetime_columns, categorical_columns=categorical_columns, graph_label=graph_label)')
    graphs_list = [{"graph_id": 0, "type": graph_type, "graph": fig}] if fig else []

    

    if graphs_list:
        for i in range(len(graphs_list)):
            fig = graphs_list[i]["graph"]
            fig.update_layout(
                template="simple_white",
                margin=dict(l=0, r=0, b=0, t=10, pad=0),
                height=350,
                font=dict(
                    family="open sans, Helvetica Neue, Helvetica, Arial, sans-serif"
                    # color=color_palette[0]
                ),
                title=dict(
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
                showlegend=show_legend,
                legend=dict(
                    orientation="h",
                    xref="container",
                    yref="container",
                    yanchor="auto",
                    xanchor="auto",
                    #                     y=-0.4,
                    #                     xanchor="left",
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
    return graphs_list, user_query


def get_funnel_chart(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label=''):
    fig = go.Figure()

    cat_col = categorical_columns[0]
    num_cols = numerical_columns

    cat_unique_values = df[cat_col].unique()

    print(cat_unique_values)

    for i in range(df[cat_col].nunique()):
        print(i)
        temp = df[df[cat_col]==cat_unique_values[i]]
        temp = temp.drop(cat_col, axis=1) 
        fig.add_trace(
            go.Funnel(
                name = cat_unique_values[i],
                orientation="h",
                y = num_cols,
                x = temp.iloc[0][num_cols].values,
                textinfo = "value+percent previous",
                hoverinfo= "name+x+y+text+percent initial+percent previous",
                marker_color = color_palette[i]
            )
        )
    fig.update_yaxes(showline=False, ticklen=0)
    fig.update_layout(title=graph_label)
    return fig


def get_4d_multiple_lines_multiple_num(df: pd.DataFrame, numerical_columns: list=[], datetime_columns: list=[], categorical_columns: list=[], graph_label='', tooltip_list=None):
    date_cols = datetime_columns
    num_cols = numerical_columns
    
    temp = df.copy()
    if tooltip_list is None:
        tooltip_list = []

    d_col = date_cols[0]

    hover_main = "%{y}<br><br>"
    hover_template_add = "<br>".join([f"{t}: " + "%(customdata[{i}])".format(i=i) for i, t in enumerate(tooltip_list)])
    hover_template_add = hover_template_add.replace("(", "{").replace(")", "}")
    hover_template = hover_main + hover_template_add

    fig = go.Figure()
    for i, n_col in enumerate(num_cols):
        fig.add_trace(go.Scatter(
            x=temp[d_col],
            y=temp[n_col],
            customdata=temp[tooltip_list],
            name=n_col,
            mode='lines+markers',
            line=dict(shape="spline"),
            marker_color=color_palette[i],#color_palette[i],
            hovertemplate=hover_template
        ))
    fig.update_yaxes(
        title="<br>".join(num_cols),
        showgrid=True,
        ticklabelstandoff=10,
        showline=False,
        ticklen=0
    )
    d_ticks = get_dticks(df, d_col)
    fig.update_xaxes(
        title=d_col,
        linewidth=1.2,
        # tick0=df[d_col].min(),
        # tickformat="%b %Y",
        # dtick=d_ticks
    )
    # fig.update_yaxes(showgrid=True, ticklabelstandoff=10, showline=False, ticklen=0)
    # fig.update_xaxes(linewidth=1.2, showgrid=False)
    fig.update_layout(title=graph_label)
    return fig