from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import comparison_chart, line_chart, neighborhood_chart
from dashboard.data import (
    add_total_return_columns,
    compute_growth,
    filter_period,
    build_comparison_series,
    load_city_metadata,
    load_city_series_with_real_values,
    load_igmi_series,
    load_ipca_reference,
    load_macro_series,
    load_neighborhood_metadata,
    load_neighborhood_series_with_real_values,
    make_download_excel,
    rebase_by_group,
)
from dashboard.ui import (
    render_chart_heading,
    inject_theme,
    render_control_label,
    render_page_footnote,
    render_hero,
    render_metric_card,
)


st.set_page_config(
    page_title="Mercado Residencial",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_theme()


@st.cache_data(show_spinner=False, persist="disk")
def get_city_series() -> pd.DataFrame:
    return load_city_series_with_real_values()


@st.cache_data(show_spinner=False, persist="disk")
def get_city_metadata() -> dict:
    return load_city_metadata()


@st.cache_data(show_spinner=False, persist="disk")
def get_ipca_reference() -> pd.DataFrame:
    return load_ipca_reference()


@st.cache_data(show_spinner=False, persist="disk")
def get_comparison_series() -> pd.DataFrame:
    return build_comparison_series()


@st.cache_data(show_spinner=False, persist="disk")
def get_neighborhood_series() -> pd.DataFrame:
    return load_neighborhood_series_with_real_values()


@st.cache_data(show_spinner=False, persist="disk")
def get_neighborhood_metadata() -> dict:
    return load_neighborhood_metadata()


@st.cache_data(show_spinner=False, persist="disk")
def get_dataset_preview(dataset_name: str) -> pd.DataFrame:
    if dataset_name == "FipeZap cidades":
        return get_city_series()[
            [
                "date",
                "city",
                "sale_index",
                "sale_price_m2",
                "sale_price_m2_real",
                "aluguel_m2",
                "ganho_capital_m2",
                "retorno_total_m2",
                "retorno_total_pct",
                "indice_total_return",
                "rent_gain_nominal",
                "rent_gain_real",
                "sale_var_12m",
                "rental_yield",
            ]
        ].copy()
    if dataset_name == "Bairros":
        return get_neighborhood_series()[
            ["date", "state", "city", "neighborhood", "price_m2", "price_m2_real", "var_12m"]
        ].copy()
    if dataset_name == "IGMI-R":
        return load_igmi_series()[["date", "city", "value", "series_name"]].copy()
    if dataset_name == "Macro índices":
        return load_macro_series()[["date", "indicator", "value", "source"]].copy()
    if dataset_name == "Comparativo":
        return get_comparison_series()[["date", "series_name", "value"]].copy()
    return pd.DataFrame()


def format_currency(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def prepare_period_defaults(df: pd.DataFrame, years_back: int = 8) -> tuple[pd.Timestamp, pd.Timestamp]:
    max_date = df["date"].max()
    min_date = max(df["date"].min(), max_date - pd.DateOffset(years=years_back))
    return min_date.to_pydatetime().date(), max_date.to_pydatetime().date()


def render_filter_heading(label: str) -> None:
    render_control_label(label)


def plotly_config() -> dict:
    return {
        "displayModeBar": False,
        "displaylogo": False,
        "responsive": True,
    }


def ensure_real_series(
    df: pd.DataFrame,
    nominal_col: str,
    real_col: str,
    ipca_reference: pd.DataFrame,
) -> pd.DataFrame:
    if real_col in df.columns:
        return df

    fixed = df.copy()
    deflator_col = None

    if "deflator_to_latest" in fixed.columns:
        deflator_col = "deflator_to_latest"
    else:
        ipca_cols = [column for column in ["date", "deflator_to_latest", "ipca_index"] if column in ipca_reference.columns]
        fixed = fixed.merge(ipca_reference[ipca_cols], on="date", how="left")

        if "deflator_to_latest" in fixed.columns:
            deflator_col = "deflator_to_latest"
        elif "deflator_to_latest_y" in fixed.columns:
            deflator_col = "deflator_to_latest_y"
        elif "deflator_to_latest_x" in fixed.columns:
            deflator_col = "deflator_to_latest_x"
        elif "ipca_index" in fixed.columns:
            latest_ipca = fixed["ipca_index"].dropna().iloc[-1] if fixed["ipca_index"].notna().any() else 100.0
            fixed["deflator_to_latest_calc"] = latest_ipca / fixed["ipca_index"]
            deflator_col = "deflator_to_latest_calc"

    if deflator_col is None:
        fixed[real_col] = fixed[nominal_col]
        return fixed

    fixed[deflator_col] = fixed[deflator_col].ffill().bfill().fillna(1.0)
    fixed[real_col] = fixed[nominal_col] * fixed[deflator_col]
    return fixed.drop(
        columns=[
            "deflator_to_latest",
            "deflator_to_latest_x",
            "deflator_to_latest_y",
            "deflator_to_latest_calc",
            "ipca_index",
        ],
        errors="ignore",
    )


def ensure_rent_gain_columns(df: pd.DataFrame) -> pd.DataFrame:
    fixed = df.copy()
    if "rent_gain_nominal" not in fixed.columns:
        fixed["rent_gain_nominal"] = fixed["rental_yield"] * fixed["sale_price_m2"]
    if "rent_gain_real" not in fixed.columns:
        if "sale_price_m2_real" in fixed.columns:
            fixed["rent_gain_real"] = fixed["rental_yield"] * fixed["sale_price_m2_real"]
        else:
            fixed["rent_gain_real"] = fixed["rent_gain_nominal"]
    return fixed


def ensure_total_return_columns(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = {
        "aluguel_m2",
        "ganho_capital_m2",
        "retorno_total_m2",
        "retorno_total_pct",
        "indice_total_return",
        "retorno_total_m2_real",
        "retorno_total_pct_real",
        "indice_total_return_real",
    }
    if required_columns.issubset(df.columns):
        return df
    return add_total_return_columns(df)


def add_window_total_return_indices(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    windowed = df.sort_values([group_col, "date"]).copy()
    windowed["indice_total_return_window"] = windowed.groupby(group_col)["retorno_total_pct"].transform(
        lambda s: (1 + s.fillna(0.0)).cumprod()
    )
    windowed["indice_total_return_real_window"] = windowed.groupby(group_col)["retorno_total_pct_real"].transform(
        lambda s: (1 + s.fillna(0.0)).cumprod()
    )
    return windowed


def compute_level_change(df: pd.DataFrame, group_col: str, value_col: str, multiplier: float = 1.0) -> pd.DataFrame:
    ordered = df.sort_values(["date"])
    summary = (
        ordered.groupby(group_col)
        .agg(
            first_value=(value_col, "first"),
            last_value=(value_col, "last"),
            last_date=("date", "last"),
        )
        .reset_index()
    )
    summary["change_value"] = (summary["last_value"] - summary["first_value"]) * multiplier
    summary["last_value_scaled"] = summary["last_value"] * multiplier
    return summary.sort_values("last_value_scaled", ascending=False)


def get_market_config(market_type: str, rent_view: str = "Recebimento") -> dict:
    if market_type == "Aluguel":
        if rent_view == "Yield":
            return {
                "label": "yield de aluguel",
                "price_col": "rental_yield",
                "real_col": "rental_yield",
                "index_col": "rental_yield",
                "composite_series": "Yield de Aluguel Composto",
                "secondary_series": ["Yield de Aluguel Composto", "FipeZap Aluguel Composto", "IPCA"],
                "value_prefix": "",
                "value_suffix": "%",
                "value_format": ",.2f",
                "multiplier": 100.0,
                "y_title": "Yield de aluguel (%)",
                "supports_real": False,
            }
        return {
            "label": "recebimento de aluguel",
            "price_col": "aluguel_m2",
            "real_col": "aluguel_m2_real",
            "index_col": "aluguel_m2",
            "real_index_col": "aluguel_m2_real",
            "composite_series": "Aluguel Recebido Composto",
            "secondary_series": ["Aluguel Recebido Composto", "FipeZap Aluguel Composto", "IPCA"],
            "value_prefix": "R$ ",
            "value_suffix": "/m²",
            "value_format": ",.2f",
            "multiplier": 1.0,
            "supports_real": True,
            "y_title": "Recebimento mensal por aluguel (R$/m²)",
        }
    return {
        "label": "venda",
        "price_col": "sale_price_m2",
        "real_col": "sale_price_m2_real",
        "index_col": "sale_index",
        "real_index_col": "sale_price_m2_real",
        "composite_series": "FipeZap Venda Composto",
        "secondary_series": ["FipeZap Venda Composto", "IVG-R", "IGMI-R Brasil", "MVG-R", "IPCA"],
        "value_prefix": "R$ ",
        "value_suffix": "/m²",
        "value_format": ",.0f",
        "multiplier": 1.0,
        "supports_real": True,
        "y_title": "R$/m² de venda",
    }


def build_ipca_window(ipca_reference: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    ipca_filtered = filter_period(ipca_reference, start_date, end_date).copy()
    if ipca_filtered.empty:
        return ipca_filtered.assign(ipca_window_base_100=pd.Series(dtype="float64"))
    base = ipca_filtered["ipca_index"].iloc[0]
    ipca_filtered["ipca_window_base_100"] = (ipca_filtered["ipca_index"] / base) * 100
    return ipca_filtered


def format_preview_df(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(display_df["date"], errors="coerce").dt.strftime("%m/%Y")

    currency_cols = {
        "sale_price_m2",
        "sale_price_m2_real",
        "aluguel_m2",
        "ganho_capital_m2",
        "retorno_total_m2",
        "retorno_total_m2_real",
        "rent_gain_nominal",
        "rent_gain_real",
        "price_m2",
        "price_m2_real",
    }
    pct_cols = {"sale_var_12m", "var_12m", "rental_yield", "retorno_total_pct", "retorno_total_pct_real"}

    for column in display_df.columns:
        if column in currency_cols:
            display_df[column] = display_df[column].map(format_currency)
        elif column in pct_cols:
            if column == "rental_yield":
                display_df[column] = display_df[column].map(lambda x: format_pct(x * 100) if pd.notna(x) else "-")
            else:
                display_df[column] = display_df[column].map(format_pct)
        elif pd.api.types.is_float_dtype(df[column]):
            display_df[column] = display_df[column].round(2)

    return display_df


def render_growth_kpis(
    growth: pd.DataFrame,
    entity_col: str,
    period_label: str,
    positive_label: str,
) -> None:
    top_entity = growth.iloc[0]
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        render_metric_card(
            "Variação nominal média",
            format_pct(growth["nominal_growth_pct"].mean()),
            period_label,
        )
    with metric_col2:
        render_metric_card(
            "Variação real média",
            format_pct(growth["real_growth_pct"].mean()),
            positive_label,
        )
    with metric_col3:
        render_metric_card(
            "Maior alta real",
            format_pct(top_entity["real_growth_pct"]),
            top_entity[entity_col],
        )


def render_panorama() -> None:
    metadata = get_city_metadata()
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.45, 1.0, 0.85, 0.85])
    all_cities = metadata["cities"]
    start_default = max(metadata["min_date"], metadata["max_date"] - pd.DateOffset(years=8)).date()
    end_default = metadata["max_date"].date()

    with filter_col1:
        render_filter_heading("Cidades")
        selected_cities = st.multiselect(
            "Cidades",
            options=all_cities,
            default=[],
            label_visibility="collapsed",
            placeholder="Escolha uma ou mais cidades",
        )
    with filter_col2:
        render_filter_heading("Período")
        date_range = st.date_input(
            "Período",
            value=(start_default, end_default),
            min_value=metadata["min_date"].date(),
            max_value=metadata["max_date"].date(),
            label_visibility="collapsed",
        )
    with filter_col3:
        render_filter_heading("Mercado")
        market_type = st.radio(
            "Mercado",
            ["Venda", "Aluguel"],
            horizontal=True,
            label_visibility="collapsed",
        )
    with filter_col4:
        render_filter_heading("Escala")
        chart_mode = st.radio(
            "Escala",
            ["Valor", "Base 100"],
            horizontal=True,
            label_visibility="collapsed",
        )

    if len(date_range) != 2 or not selected_cities:
        st.info("Escolha uma ou mais cidades para começar a análise.")
        return

    rent_view = "Recebimento"
    if market_type == "Aluguel":
        metric_col, _ = st.columns([1.15, 2.85])
        with metric_col:
            render_filter_heading("Métrica")
            rent_view = st.radio(
                "Métrica de aluguel",
                ["Yield", "Recebimento"],
                horizontal=True,
                key="panorama_rent_view",
                label_visibility="collapsed",
            )

    market = get_market_config(market_type, rent_view=rent_view)
    ipca_reference = get_ipca_reference()
    city_series = ensure_total_return_columns(ensure_rent_gain_columns(get_city_series()))
    city_series = ensure_real_series(
        city_series,
        nominal_col=market["price_col"],
        real_col=market["real_col"],
        ipca_reference=ipca_reference,
    )
    filtered = filter_period(city_series[city_series["city"].isin(selected_cities)], *date_range)
    filtered = filtered.sort_values(["city", "date"])
    filtered = add_window_total_return_indices(filtered, group_col="city")
    if market_type == "Aluguel":
        filtered = filtered[filtered["rental_yield"].notna()].copy()
        available_cities = sorted(filtered["city"].dropna().unique().tolist())
        missing_cities = [city for city in selected_cities if city not in available_cities]
        if filtered.empty:
            st.warning("As cidades selecionadas não possuem série de rentabilidade do aluguel disponível nesse período.")
            return
        if missing_cities:
            st.caption("Sem rentabilidade do aluguel para: " + ", ".join(missing_cities))

    series_visibility = ["Nominal"]
    if market["supports_real"]:
        line_selector_col, _ = st.columns([1.15, 2.85])
        with line_selector_col:
            render_filter_heading("Linhas")
            series_visibility = st.multiselect(
                "Linhas",
                options=["Nominal", "Real"],
                default=["Nominal", "Real"],
                key=f"panorama_series_visibility_{market_type}_{rent_view}",
                label_visibility="collapsed",
            )
        if not series_visibility:
            st.info("Selecione ao menos uma linha para exibir.")
            return

    plot_frames = []
    if market["supports_real"]:
        growth_nominal_col = market["price_col"]
        growth_real_col = market["real_col"]

        growth = compute_growth(
            filtered,
            group_col="city",
            nominal_col=growth_nominal_col,
            real_col=growth_real_col,
        )
        if "Nominal" in series_visibility:
            nominal_source = market["price_col"]
            nominal_df = filtered[["date", "city", nominal_source]].copy()
            nominal_df["plot_value"] = nominal_df[nominal_source] * market["multiplier"]
            nominal_df["line_kind"] = "Nominal"
            nominal_df["series_key"] = nominal_df["city"] + "_nominal"
            plot_frames.append(nominal_df[["date", "city", "line_kind", "series_key", "plot_value"]])
        if "Real" in series_visibility:
            real_source = market["real_col"]
            real_df = filtered[["date", "city", real_source]].copy()
            real_df["plot_value"] = real_df[real_source] * market["multiplier"]
            real_df["line_kind"] = "Real"
            real_df["series_key"] = real_df["city"] + "_real"
            plot_frames.append(real_df[["date", "city", "line_kind", "series_key", "plot_value"]])
    else:
        growth = compute_growth(
            filtered,
            group_col="city",
            nominal_col=market["price_col"],
            real_col=market["real_col"],
        )
        yield_df = filtered[["date", "city", market["price_col"]]].copy()
        yield_df["plot_value"] = yield_df[market["price_col"]] * market["multiplier"]
        yield_df["line_kind"] = "Yield"
        yield_df["series_key"] = yield_df["city"] + "_yield"
        plot_frames.append(yield_df[["date", "city", "line_kind", "series_key", "plot_value"]])

    plot_df = pd.concat(plot_frames, ignore_index=True).sort_values(["city", "line_kind", "date"])
    if chart_mode == "Base 100":
        plot_df = rebase_by_group(plot_df, group_col="series_key", value_col="plot_value", new_col="plot_value")
        y_title = "Base 100"
    else:
        y_title = market["y_title"]

    render_growth_kpis(
        growth,
        entity_col="city",
        period_label="Período selecionado",
        positive_label=f"{(growth['real_growth_pct'] > 0).sum()} cidades com alta real",
    )
    chart_heading = (
        "Recebimento de aluguel por cidade"
        if market_type == "Aluguel" and rent_view != "Yield"
        else "Yield de aluguel por cidade"
        if market_type == "Aluguel"
        else "Preço do m² de venda por cidade"
    )
    render_chart_heading(chart_heading)
    st.plotly_chart(
        line_chart(
            plot_df,
            value_col="plot_value",
            color_col="city",
            title="",
            y_title=y_title,
            value_prefix=market["value_prefix"] if y_title != "Base 100" else "",
            value_suffix=market["value_suffix"] if y_title != "Base 100" else "",
            value_format=market["value_format"] if y_title != "Base 100" else ",.1f",
            dash_col="line_kind" if market["supports_real"] else None,
            dash_map={"Nominal": "solid", "Real": "dash"} if market["supports_real"] else None,
            compact_legend=len(selected_cities) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )


def render_comparisons() -> None:
    metadata = get_city_metadata()
    all_cities = metadata["cities"]
    start_default = max(metadata["min_date"], metadata["max_date"] - pd.DateOffset(years=8)).date()
    end_default = metadata["max_date"].date()

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.35, 1.0, 0.85, 0.9])
    with filter_col1:
        render_filter_heading("Cidades")
        selected_cities = st.multiselect(
            "Cidades para comparar",
            options=all_cities,
            default=[],
            key="compare_cities",
            label_visibility="collapsed",
            placeholder="Escolha as cidades",
        )
    with filter_col2:
        render_filter_heading("Período")
        date_range = st.date_input(
            "Período",
            value=(start_default, end_default),
            min_value=metadata["min_date"].date(),
            max_value=metadata["max_date"].date(),
            key="compare_range",
            label_visibility="collapsed",
        )
    with filter_col3:
        render_filter_heading("Mercado")
        market_type = st.radio(
            "Mercado",
            ["Venda", "Aluguel"],
            horizontal=True,
            key="compare_market",
            label_visibility="collapsed",
        )
    with filter_col4:
        render_filter_heading("Escala")
        chart_mode = st.radio(
            "Escala",
            ["Valor", "Base 100"],
            horizontal=True,
            key="compare_mode",
            label_visibility="collapsed",
        )

    select_all_cities = st.checkbox("Selecionar todas as cidades", key="compare_all_cities")
    if select_all_cities:
        selected_cities = all_cities

    if len(date_range) != 2 or not selected_cities:
        st.info("Escolha as cidades que deseja comparar.")
        return

    rent_view = "Recebimento"
    if market_type == "Aluguel":
        metric_col, _ = st.columns([1.15, 2.85])
        with metric_col:
            render_filter_heading("Métrica")
            rent_view = st.radio(
                "Métrica de aluguel na comparação",
                ["Yield", "Recebimento"],
                horizontal=True,
                key="compare_rent_view",
                label_visibility="collapsed",
            )

    market = get_market_config(market_type, rent_view=rent_view)
    city_series = ensure_total_return_columns(ensure_rent_gain_columns(get_city_series()))
    comparison_series = get_comparison_series()
    main_df = filter_period(city_series[city_series["city"].isin(selected_cities)], *date_range)
    main_df = main_df.sort_values(["city", "date"])
    main_df = add_window_total_return_indices(main_df, group_col="city")
    if market_type == "Aluguel":
        main_df = main_df[main_df["rental_yield"].notna()].copy()
        available_cities = sorted(main_df["city"].dropna().unique().tolist())
        missing_cities = [city for city in selected_cities if city not in available_cities]
        if main_df.empty:
            st.warning("As cidades selecionadas não possuem série de rentabilidade do aluguel disponível nesse período.")
            return
        if missing_cities:
            st.caption("Sem rentabilidade do aluguel para: " + ", ".join(missing_cities))

    metric_source = main_df.copy()
    main_value_col = market["price_col"]

    if chart_mode == "Base 100":
        main_df = rebase_by_group(main_df, group_col="city", value_col=main_value_col, new_col="plot_value")
        y_title = "Base 100"
        value_format = ",.1f"
        value_prefix = ""
        value_suffix = ""
    else:
        main_df["plot_value"] = main_df[main_value_col] * market["multiplier"]
        y_title = market["y_title"]
        value_format = market["value_format"]
        value_prefix = market["value_prefix"]
        value_suffix = market["value_suffix"]

    growth = compute_growth(
        metric_source,
        group_col="city",
        nominal_col=market["price_col"],
        real_col=market["real_col"],
    )
    render_growth_kpis(
        growth,
        entity_col="city",
        period_label="Período selecionado",
        positive_label=f"{(growth['real_growth_pct'] > 0).sum()} cidades com alta real",
    )

    heading = (
        "Recebimento de aluguel por cidade"
        if market_type == "Aluguel" and rent_view != "Yield"
        else "Yield de aluguel por cidade"
        if market_type == "Aluguel"
        else "Preço do m² de venda por cidade"
    )
    render_chart_heading(heading)
    st.plotly_chart(
        line_chart(
            main_df,
            value_col="plot_value",
            color_col="city",
            title="",
            y_title=y_title,
            value_prefix=value_prefix,
            value_format=value_format,
            value_suffix=value_suffix,
            compact_legend=len(selected_cities) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )

    available_series = [
        series for series in market["secondary_series"] if series in comparison_series["series_name"].unique()
    ]
    if market_type == "Aluguel":
        default_series = [series for series in available_series if series != "IPCA"]
    else:
        default_series = [
            series
            for series in [market["composite_series"], "IVG-R", "IGMI-R Brasil", "MVG-R"]
            if series in available_series
        ]
    render_filter_heading("Séries")
    selected_series = st.multiselect(
        "Séries secundárias",
        options=available_series,
        default=default_series,
        key="secondary_series",
        label_visibility="collapsed",
    )

    secondary_df = filter_period(
        comparison_series[comparison_series["series_name"].isin(sorted(set(selected_series + ["IPCA"])))],
        *date_range,
    )
    secondary_df = secondary_df.sort_values(["series_name", "date"])
    secondary_df = rebase_by_group(secondary_df, group_col="series_name", value_col="value", new_col="rebased_value")

    render_chart_heading("Índices selecionados vs IPCA")
    st.plotly_chart(
        comparison_chart(
            secondary_df,
            title="",
            y_title="Base 100 no início da janela",
            compact_legend=len(selected_series) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )

def render_neighborhoods() -> None:
    metadata = get_neighborhood_metadata()
    all_cities = metadata["cities"]
    start_default = max(
        metadata["min_date"],
        metadata["max_date"] - pd.DateOffset(years=6),
    ).to_pydatetime().date()
    end_default = metadata["max_date"].to_pydatetime().date()

    filter_col1, filter_col2 = st.columns([1.45, 1.05])
    with filter_col1:
        render_filter_heading("Cidades")
        selected_cities = st.multiselect(
            "Cidades",
            options=all_cities,
            default=[],
            key="neighborhood_cities",
            label_visibility="collapsed",
            placeholder="Escolha as cidades",
        )
    with filter_col2:
        render_filter_heading("Período")
        date_range = st.date_input(
            "Período",
            value=(start_default, end_default),
            min_value=metadata["min_date"].date(),
            max_value=metadata["max_date"].date(),
            key="neighborhood_range",
            label_visibility="collapsed",
        )

    if len(date_range) != 2 or not selected_cities:
        st.info("Escolha primeiro as cidades para liberar os bairros.")
        return

    neighborhood_series = get_neighborhood_series()
    ipca_reference = get_ipca_reference()
    city_filtered = neighborhood_series[neighborhood_series["city"].isin(selected_cities)].copy()
    city_filtered = filter_period(city_filtered, *date_range)
    labels = sorted(city_filtered["label"].dropna().unique().tolist())
    latest_snapshot = city_filtered.sort_values("date").groupby("label").tail(1).sort_values("price_m2", ascending=False)

    render_filter_heading("Bairros")
    selected_labels = st.multiselect(
        "Bairros",
        options=labels,
        default=[],
        key="neighborhood_labels",
        label_visibility="collapsed",
        placeholder="Escolha os bairros",
    )
    select_all_bairros = st.checkbox("Selecionar todos os bairros", key="all_neighborhoods")
    if select_all_bairros:
        selected_labels = labels

    if not selected_labels:
        st.info("Escolha os bairros que deseja comparar.")
        return

    filtered = city_filtered[city_filtered["label"].isin(selected_labels)].sort_values(["label", "date"])
    growth = compute_growth(filtered, group_col="label", nominal_col="price_m2", real_col="price_m2_real")
    ipca_filtered = build_ipca_window(ipca_reference, *date_range)
    nominal_base_df = rebase_by_group(filtered, group_col="label", value_col="price_m2", new_col="plot_value")
    real_base_df = rebase_by_group(filtered, group_col="label", value_col="price_m2_real", new_col="plot_value")
    ipca_plot = ipca_filtered.copy()
    ipca_plot["label"] = "IPCA"
    ipca_plot["plot_value"] = ipca_plot["ipca_window_base_100"]
    chart_variant = st.radio(
        "Série do gráfico",
        ["Nominal", "Real"],
        horizontal=True,
        key="neighborhood_chart_variant",
    )
    selected_snapshot = latest_snapshot[latest_snapshot["label"].isin(selected_labels)]
    summary_table = (
        selected_snapshot[["label", "price_m2", "price_m2_real"]]
        .merge(growth[["label", "real_growth_pct"]], on="label", how="left")
        .rename(
            columns={
                "label": "Bairro",
                "price_m2": "Último nominal",
                "price_m2_real": "Último real",
                "real_growth_pct": "Alta real",
            }
        )
        .sort_values("Último nominal", ascending=False)
    )
    summary_table["Último nominal"] = summary_table["Último nominal"].map(format_currency)
    summary_table["Último real"] = summary_table["Último real"].map(format_currency)
    summary_table["Alta real"] = summary_table["Alta real"].map(format_pct)

    render_growth_kpis(
        growth,
        entity_col="label",
        period_label="Período selecionado",
        positive_label=f"{(growth['real_growth_pct'] > 0).sum()} bairros com alta real",
    )

    active_df = nominal_base_df if chart_variant == "Nominal" else real_base_df
    render_chart_heading(f"Preço {chart_variant.lower()} do m² por bairro")
    st.plotly_chart(
        neighborhood_chart(
            active_df,
            value_col="plot_value",
            ipca_df=ipca_plot,
            title="",
            y_title="Base 100",
            compact_legend=len(selected_labels) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )

    render_chart_heading("Tabela comparativa")
    st.dataframe(summary_table, use_container_width=True, hide_index=True)

def render_data_tab() -> None:
    dataset_names = ["Bairros", "IGMI-R", "Macro índices", "Comparativo"]
    render_filter_heading("Base")
    dataset_name = st.selectbox(
        "Dataset",
        options=dataset_names,
        index=None,
        placeholder="Escolha uma base",
        label_visibility="collapsed",
    )

    if dataset_name is None:
        st.info("Escolha uma base para visualizar os dados.")
        return

    preview_df = get_dataset_preview(dataset_name)
    display_df = format_preview_df(preview_df.head(250))

    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        render_metric_card("Linhas", f"{len(preview_df):,}".replace(",", "."), dataset_name)
    with info_col2:
        render_metric_card("Colunas", str(preview_df.shape[1]), "Prévia carregada")
    with info_col3:
        min_date = preview_df["date"].min() if "date" in preview_df.columns else None
        max_date = preview_df["date"].max() if "date" in preview_df.columns else None
        period_text = f"{min_date:%m/%Y} a {max_date:%m/%Y}" if min_date is not None and pd.notna(min_date) else "Sem data"
        render_metric_card("Cobertura", period_text, "Faixa observada")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv_bytes = preview_df.to_csv(index=False).encode("utf-8-sig")
    xlsx_bytes = make_download_excel(preview_df)
    download_col1, download_col2 = st.columns(2)
    with download_col1:
        st.download_button(
            "Baixar CSV",
            data=csv_bytes,
            file_name=f"{dataset_name.lower().replace(' ', '_')}.csv",
            mime="text/csv",
        )
    with download_col2:
        st.download_button(
            "Baixar Excel",
            data=xlsx_bytes,
            file_name=f"{dataset_name.lower().replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_page_footer(city_metadata: dict) -> None:
    latest_base = city_metadata["max_date"].strftime("%m/%Y")
    footnote = (
        f"Fontes: FipeZap, ABECIP e Banco Central. "
        f"Valores reais ajustados pelo IPCA; linhas tracejadas indicam série real. "
        f"Última base FipeZap: {latest_base}."
    )
    render_page_footnote(footnote)


def main() -> None:
    render_hero()
    with st.spinner("Carregando estrutura do dashboard..."):
        metadata = get_city_metadata()

    if not metadata["cities"]:
        st.error("Não foi possível carregar as séries principais do dashboard.")
        return

    tab_panorama, tab_compare, tab_neighborhood, tab_data = st.tabs(
        ["Panorama", "Comparações", "m² por Bairro", "Dados"]
    )

    with tab_panorama:
        render_panorama()

    with tab_compare:
        render_comparisons()

    with tab_neighborhood:
        render_neighborhoods()

    with tab_data:
        render_data_tab()

    render_page_footer(metadata)


main()
