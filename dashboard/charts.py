from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.config import CHART_COLORS, THEME


def _base_layout(
    fig: go.Figure,
    title: str,
    y_title: str,
    x_title: str = "",
    compact_legend: bool = False,
) -> go.Figure:
    legend_y = 1.0 if compact_legend else -0.2
    legend_x = 1.02 if compact_legend else 0
    legend_xanchor = "left" if compact_legend else "left"
    legend_orientation = "v" if compact_legend else "h"
    legend_font_size = 9 if compact_legend else 11
    itemwidth = 72 if compact_legend else 110
    margin_right = 170 if compact_legend else 10
    margin_bottom = 48 if compact_legend else 86
    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", y=0.98, yanchor="top"),
        xaxis_title=x_title,
        yaxis_title=y_title,
        paper_bgcolor=THEME["surface"],
        plot_bgcolor=THEME["surface"],
        hovermode="x unified",
        margin=dict(l=10, r=margin_right, t=26, b=margin_bottom),
        font=dict(family="Segoe UI, sans-serif", color=THEME["ink"]),
        legend=dict(
            orientation=legend_orientation,
            yanchor="top",
            y=legend_y,
            xanchor=legend_xanchor,
            x=legend_x,
            title="",
            font=dict(size=legend_font_size),
            itemwidth=itemwidth,
            tracegroupgap=4,
            bgcolor="rgba(255,255,255,0.82)" if compact_legend else "rgba(255,255,255,0)",
            bordercolor="rgba(16, 33, 61, 0.08)",
            borderwidth=1 if compact_legend else 0,
        ),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, tickformat="%b/%y")
    fig.update_yaxes(gridcolor=THEME["grid"], zeroline=False)
    return fig


def line_chart(
    df: pd.DataFrame,
    value_col: str,
    color_col: str,
    title: str,
    y_title: str,
    value_prefix: str = "",
    value_suffix: str = "",
    value_format: str = ",.0f",
    dash_col: str | None = None,
    dash_map: dict[str, str] | None = None,
    compact_legend: bool = False,
) -> go.Figure:
    line_kwargs = {}
    if dash_col:
        line_kwargs["line_dash"] = dash_col
    if dash_map:
        line_kwargs["line_dash_map"] = dash_map

    fig = px.line(
        df,
        x="date",
        y=value_col,
        color=color_col,
        color_discrete_sequence=CHART_COLORS,
        line_shape="spline",
        **line_kwargs,
    )
    fig.update_traces(
        line=dict(width=3),
        mode="lines",
        hovertemplate=(
            "%{x|%b/%Y}<br>%{fullData.name}: "
            + value_prefix
            + "%{y:"
            + value_format
            + "}"
            + value_suffix
            + "<extra></extra>"
        ),
    )
    return _base_layout(fig, title=title, y_title=y_title, compact_legend=compact_legend)


def comparison_chart(
    df: pd.DataFrame,
    title: str,
    y_title: str = "Base 100",
    compact_legend: bool = False,
) -> go.Figure:
    fig = px.line(
        df,
        x="date",
        y="rebased_value",
        color="series_name",
        color_discrete_sequence=CHART_COLORS,
        line_shape="spline",
    )
    fig.update_traces(
        line=dict(width=3),
        mode="lines",
        hovertemplate="%{x|%b/%Y}<br>%{fullData.name}: %{y:,.1f}<extra></extra>",
    )
    return _base_layout(fig, title=title, y_title=y_title, compact_legend=compact_legend)


def neighborhood_chart(
    prices_df: pd.DataFrame,
    value_col: str,
    ipca_df: pd.DataFrame,
    title: str,
    y_title: str,
    compact_legend: bool = False,
) -> go.Figure:
    fig = go.Figure()

    for index, label in enumerate(prices_df["label"].dropna().unique()):
        subset = prices_df[prices_df["label"] == label]
        fig.add_trace(
            go.Scatter(
                x=subset["date"],
                y=subset[value_col],
                mode="lines",
                name=label,
                line=dict(color=CHART_COLORS[index % len(CHART_COLORS)], width=3),
                hovertemplate="%{x|%b/%Y}<br>%{fullData.name}: %{y:,.1f}<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=ipca_df["date"],
            y=ipca_df[value_col],
            mode="lines",
            name="IPCA",
            line=dict(color=THEME["accent"], width=2, dash="dash"),
            hovertemplate="%{x|%b/%Y}<br>IPCA: %{y:,.1f}<extra></extra>",
        )
    )

    return _base_layout(fig, title=title, y_title=y_title, compact_legend=compact_legend)
