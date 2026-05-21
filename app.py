from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import comparison_chart, line_chart, neighborhood_chart
from dashboard.data import (
    add_total_return_columns,
    build_comparison_series,
    compute_growth,
    filter_period,
    load_cdi_reference,
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
    inject_theme,
    render_chart_heading,
    render_control_label,
    render_hero,
    render_metric_card,
    render_page_footnote,
)


ASSET_CONFIG = {
    "residential": {
        "label": "Residenciais",
        "hero_title": "Mercado Residencial",
        "hero_description": "Preço nominal, preço real e comparação entre cidades e bairros.",
        "show_neighborhoods": True,
    },
    "commercial": {
        "label": "Comerciais",
        "hero_title": "Mercado Comercial",
        "hero_description": "Preço nominal, preço real e comparação entre cidades, com venda, locação e rentabilidade.",
        "show_neighborhoods": False,
    },
}


st.set_page_config(
    page_title="Mercado Imobiliário Brasil",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_theme()


@st.cache_data(show_spinner=False, persist="disk")
def get_city_series(asset_class: str) -> pd.DataFrame:
    return load_city_series_with_real_values(asset_class)


@st.cache_data(show_spinner=False, persist="disk")
def get_city_metadata(asset_class: str) -> dict:
    return load_city_metadata(asset_class)


@st.cache_data(show_spinner=False, persist="disk")
def get_ipca_reference() -> pd.DataFrame:
    return load_ipca_reference()


@st.cache_data(show_spinner=False, persist="disk")
def get_comparison_series(asset_class: str) -> pd.DataFrame:
    return build_comparison_series(asset_class)


@st.cache_data(show_spinner=False, persist="disk")
def get_neighborhood_series() -> pd.DataFrame:
    return load_neighborhood_series_with_real_values()


@st.cache_data(show_spinner=False, persist="disk")
def get_neighborhood_metadata() -> dict:
    return load_neighborhood_metadata()


@st.cache_data(show_spinner=False, persist="disk")
def get_cdi_reference() -> pd.DataFrame:
    return load_cdi_reference()


@st.cache_data(show_spinner=False, persist="disk")
def get_dataset_preview(dataset_name: str, asset_class: str) -> pd.DataFrame:
    if dataset_name == "FipeZap cidades":
        return get_city_series(asset_class)[
            [
                "date",
                "city",
                "sale_index",
                "sale_price_m2",
                "sale_price_m2_real",
                "rent_index",
                "rent_price_m2",
                "rent_price_m2_real",
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
        return get_neighborhood_series()[["date", "state", "city", "neighborhood", "price_m2", "price_m2_real", "var_12m"]].copy()
    if dataset_name == "IGMI-R":
        return load_igmi_series()[["date", "city", "value", "series_name"]].copy()
    if dataset_name == "Macro índices":
        return load_macro_series()[["date", "indicator", "value", "source"]].copy()
    if dataset_name == "Comparativo":
        return get_comparison_series(asset_class)[["date", "series_name", "value"]].copy()
    return pd.DataFrame()


def format_currency(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


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


def build_ipca_window(ipca_reference: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    ipca_filtered = filter_period(ipca_reference, start_date, end_date).copy()
    if ipca_filtered.empty:
        return ipca_filtered.assign(ipca_window_base_100=pd.Series(dtype="float64"))
    base = ipca_filtered["ipca_index"].iloc[0]
    ipca_filtered["ipca_window_base_100"] = (ipca_filtered["ipca_index"] / base) * 100
    return ipca_filtered


def build_cdi_window(cdi_reference: pd.DataFrame, start_date, end_date, series: str = "cdi_index") -> pd.DataFrame:
    cdi_filtered = filter_period(cdi_reference, start_date, end_date).copy()
    if cdi_filtered.empty or series not in cdi_filtered.columns:
        return pd.DataFrame(columns=["date", "plot_value"])
    base = cdi_filtered[series].iloc[0]
    cdi_filtered["plot_value"] = (cdi_filtered[series] / base) * 100
    return cdi_filtered[["date", "plot_value"]]


def format_preview_df(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(display_df["date"], errors="coerce").dt.strftime("%m/%Y")

    currency_cols = {
        "sale_price_m2",
        "sale_price_m2_real",
        "rent_price_m2",
        "rent_price_m2_real",
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
    if growth.empty:
        st.info("Sem dados suficientes para calcular as KPIs neste recorte.")
        return

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


def get_market_config(asset_class: str, market_type: str, rent_view: str = "Recebimento") -> dict:
    if asset_class == "commercial":
        names = {
            "sale_composite": "FipeZap Comercial Venda Composto",
            "rent_composite": "FipeZap Comercial Aluguel Composto",
            "received_composite": "Aluguel Comercial Recebido Composto",
            "yield_composite": "Yield de Aluguel Comercial Composto",
            "sale_title": "Preço do m² de venda comercial por cidade",
            "received_title": "Recebimento de aluguel comercial por cidade",
            "yield_title": "Yield de aluguel comercial por cidade",
        }
    else:
        names = {
            "sale_composite": "FipeZap Venda Composto",
            "rent_composite": "FipeZap Aluguel Composto",
            "received_composite": "Aluguel Recebido Composto",
            "yield_composite": "Yield de Aluguel Composto",
            "sale_title": "Preço do m² de venda por cidade",
            "received_title": "Recebimento de aluguel por cidade",
            "yield_title": "Yield de aluguel por cidade",
        }

    if market_type == "Aluguel":
        if rent_view == "Yield":
            return {
                "label": "yield de aluguel",
                "price_col": "rental_yield",
                "real_col": "rental_yield",
                "secondary_series": [names["yield_composite"], names["rent_composite"], "IPCA", "CDI", "CDI Real"],
                "composite_series": names["yield_composite"],
                "value_prefix": "",
                "value_suffix": "%",
                "value_format": ",.2f",
                "multiplier": 100.0,
                "y_title": "Yield de aluguel (%)",
                "supports_real": False,
                "chart_heading": names["yield_title"],
            }
        return {
            "label": "recebimento de aluguel",
            "price_col": "aluguel_m2",
            "real_col": "aluguel_m2_real",
            "secondary_series": [names["received_composite"], names["rent_composite"], "IPCA", "CDI", "CDI Real"],
            "composite_series": names["received_composite"],
            "value_prefix": "R$ ",
            "value_suffix": "/m²",
            "value_format": ",.2f",
            "multiplier": 1.0,
            "supports_real": True,
            "y_title": "Recebimento mensal por aluguel (R$/m²)",
            "chart_heading": names["received_title"],
        }
    return {
        "label": "venda",
        "price_col": "sale_price_m2",
        "real_col": "sale_price_m2_real",
        "secondary_series": [names["sale_composite"], "IVG-R", "IGMI-R Brasil", "MVG-R", "IPCA", "CDI", "CDI Real"],
        "composite_series": names["sale_composite"],
        "value_prefix": "R$ ",
        "value_suffix": "/m²",
        "value_format": ",.0f",
        "multiplier": 1.0,
        "supports_real": True,
        "y_title": "R$/m² de venda",
        "chart_heading": names["sale_title"],
    }


def render_panorama(asset_class: str) -> None:
    metadata = get_city_metadata(asset_class)
    key_prefix = f"{asset_class}_panorama"
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
            key=f"{key_prefix}_cities",
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
            key=f"{key_prefix}_range",
            label_visibility="collapsed",
        )
    with filter_col3:
        render_filter_heading("Mercado")
        market_type = st.radio(
            "Mercado",
            ["Venda", "Aluguel"],
            horizontal=True,
            key=f"{key_prefix}_market",
            label_visibility="collapsed",
        )
    with filter_col4:
        render_filter_heading("Escala")
        chart_mode = st.radio(
            "Escala",
            ["Valor", "Base 100"],
            horizontal=True,
            key=f"{key_prefix}_mode",
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
                key=f"{key_prefix}_rent_view",
                label_visibility="collapsed",
            )

    market = get_market_config(asset_class, market_type, rent_view=rent_view)
    ipca_reference = get_ipca_reference()
    city_series = ensure_total_return_columns(ensure_rent_gain_columns(get_city_series(asset_class)))
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
                key=f"{key_prefix}_line_visibility",
                label_visibility="collapsed",
            )
        if not series_visibility:
            st.info("Selecione ao menos uma linha para exibir.")
            return

    growth = compute_growth(filtered, group_col="city", nominal_col=market["price_col"], real_col=market["real_col"])
    plot_frames = []

    if market["supports_real"]:
        if "Nominal" in series_visibility:
            nominal_df = filtered[["date", "city", market["price_col"]]].copy()
            nominal_df["plot_value"] = nominal_df[market["price_col"]] * market["multiplier"]
            nominal_df["line_kind"] = "Nominal"
            nominal_df["series_key"] = nominal_df["city"] + "_nominal"
            plot_frames.append(nominal_df[["date", "city", "line_kind", "series_key", "plot_value"]])
        if "Real" in series_visibility:
            real_df = filtered[["date", "city", market["real_col"]]].copy()
            real_df["plot_value"] = real_df[market["real_col"]] * market["multiplier"]
            real_df["line_kind"] = "Real"
            real_df["series_key"] = real_df["city"] + "_real"
            plot_frames.append(real_df[["date", "city", "line_kind", "series_key", "plot_value"]])

        if chart_mode == "Base 100" and market_type == "Venda":
            cdi_ref = get_cdi_reference()
            cdi_win = filter_period(cdi_ref, *date_range)
            if not cdi_win.empty:
                if "Nominal" in series_visibility:
                    tr_nom = filtered[["date", "city", "indice_total_return_window"]].copy()
                    tr_nom["plot_value"] = tr_nom["indice_total_return_window"] * 100
                    tr_nom["city"] = tr_nom["city"] + " + Aluguel"
                    tr_nom["line_kind"] = "Nominal"
                    tr_nom["series_key"] = tr_nom["city"] + "_nominal"
                    plot_frames.append(tr_nom[["date", "city", "line_kind", "series_key", "plot_value"]])

                    cdi_n = cdi_win[["date", "cdi_index"]].copy()
                    cdi_n["plot_value"] = cdi_n["cdi_index"]
                    cdi_n["city"] = "CDI"
                    cdi_n["line_kind"] = "Nominal"
                    cdi_n["series_key"] = "CDI_nominal"
                    plot_frames.append(cdi_n[["date", "city", "line_kind", "series_key", "plot_value"]])

                if "Real" in series_visibility:
                    tr_real = filtered[["date", "city", "indice_total_return_real_window"]].copy()
                    tr_real["plot_value"] = tr_real["indice_total_return_real_window"] * 100
                    tr_real["city"] = tr_real["city"] + " + Aluguel"
                    tr_real["line_kind"] = "Real"
                    tr_real["series_key"] = tr_real["city"] + "_real"
                    plot_frames.append(tr_real[["date", "city", "line_kind", "series_key", "plot_value"]])

                    cdi_r = cdi_win[["date", "cdi_real_index"]].copy()
                    cdi_r["plot_value"] = cdi_r["cdi_real_index"]
                    cdi_r["city"] = "CDI"
                    cdi_r["line_kind"] = "Real"
                    cdi_r["series_key"] = "CDI_real"
                    plot_frames.append(cdi_r[["date", "city", "line_kind", "series_key", "plot_value"]])
    else:
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

    real_positive_label = f"{(growth['real_growth_pct'] > 0).sum()} cidades com alta real"
    if market_type == "Aluguel" and rent_view == "Yield":
        real_positive_label = "Yield sem deflator dedicado"

    render_growth_kpis(
        growth,
        entity_col="city",
        period_label="Período selecionado",
        positive_label=real_positive_label,
    )
    render_chart_heading(market["chart_heading"])
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


def render_comparisons(asset_class: str) -> None:
    metadata = get_city_metadata(asset_class)
    key_prefix = f"{asset_class}_compare"
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
            key=f"{key_prefix}_cities",
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
            key=f"{key_prefix}_range",
            label_visibility="collapsed",
        )
    with filter_col3:
        render_filter_heading("Mercado")
        market_type = st.radio(
            "Mercado",
            ["Venda", "Aluguel"],
            horizontal=True,
            key=f"{key_prefix}_market",
            label_visibility="collapsed",
        )
    with filter_col4:
        render_filter_heading("Escala")
        chart_mode = st.radio(
            "Escala",
            ["Valor", "Base 100"],
            horizontal=True,
            key=f"{key_prefix}_mode",
            label_visibility="collapsed",
        )

    select_all_cities = st.checkbox("Selecionar todas as cidades", key=f"{key_prefix}_all_cities")
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
                key=f"{key_prefix}_rent_view",
                label_visibility="collapsed",
            )

    market = get_market_config(asset_class, market_type, rent_view=rent_view)
    city_series = ensure_total_return_columns(ensure_rent_gain_columns(get_city_series(asset_class)))
    comparison_series = get_comparison_series(asset_class)
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
    if chart_mode == "Base 100":
        main_df = rebase_by_group(main_df, group_col="city", value_col=market["price_col"], new_col="plot_value")
        y_title = "Base 100"
        value_prefix = ""
        value_suffix = ""
        value_format = ",.1f"
    else:
        main_df["plot_value"] = main_df[market["price_col"]] * market["multiplier"]
        y_title = market["y_title"]
        value_prefix = market["value_prefix"]
        value_suffix = market["value_suffix"]
        value_format = market["value_format"]

    growth = compute_growth(metric_source, group_col="city", nominal_col=market["price_col"], real_col=market["real_col"])
    real_positive_label = f"{(growth['real_growth_pct'] > 0).sum()} cidades com alta real"
    if market_type == "Aluguel" and rent_view == "Yield":
        real_positive_label = "Yield sem deflator dedicado"

    render_growth_kpis(
        growth,
        entity_col="city",
        period_label="Período selecionado",
        positive_label=real_positive_label,
    )

    render_chart_heading(market["chart_heading"])
    st.plotly_chart(
        line_chart(
            main_df,
            value_col="plot_value",
            color_col="city",
            title="",
            y_title=y_title,
            value_prefix=value_prefix,
            value_suffix=value_suffix,
            value_format=value_format,
            compact_legend=len(selected_cities) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )

    available_series = [series for series in market["secondary_series"] if series in comparison_series["series_name"].unique()]
    if market_type == "Aluguel":
        default_series = [series for series in available_series if series != "IPCA"]
    else:
        default_series = [series for series in [market["composite_series"], "IVG-R", "IGMI-R Brasil", "MVG-R"] if series in available_series]

    render_filter_heading("Séries")
    selected_series = st.multiselect(
        "Séries secundárias",
        options=available_series,
        default=default_series,
        key=f"{key_prefix}_secondary_series",
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
    start_default = max(metadata["min_date"], metadata["max_date"] - pd.DateOffset(years=6)).date()
    end_default = metadata["max_date"].date()

    filter_col1, filter_col2 = st.columns([1.45, 1.05])
    with filter_col1:
        render_filter_heading("Cidades")
        selected_cities = st.multiselect(
            "Cidades",
            options=metadata["cities"],
            default=[],
            key="residential_neighborhood_cities",
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
            key="residential_neighborhood_range",
            label_visibility="collapsed",
        )

    if len(date_range) != 2 or not selected_cities:
        st.info("Escolha primeiro as cidades para liberar os bairros.")
        return

    city_filtered = get_neighborhood_series()
    city_filtered = city_filtered[city_filtered["city"].isin(selected_cities)].copy()
    city_filtered = filter_period(city_filtered, *date_range)
    labels = sorted(city_filtered["label"].dropna().unique().tolist())
    latest_snapshot = city_filtered.sort_values("date").groupby("label").tail(1).sort_values("price_m2", ascending=False)

    render_filter_heading("Bairros")
    selected_labels = st.multiselect(
        "Bairros",
        options=labels,
        default=[],
        key="residential_neighborhood_labels",
        label_visibility="collapsed",
        placeholder="Escolha os bairros",
    )
    if st.checkbox("Selecionar todos os bairros", key="residential_neighborhood_all"):
        selected_labels = labels

    if not selected_labels:
        st.info("Escolha os bairros que deseja comparar.")
        return

    filtered = city_filtered[city_filtered["label"].isin(selected_labels)].sort_values(["label", "date"])
    growth = compute_growth(filtered, group_col="label", nominal_col="price_m2", real_col="price_m2_real")
    nominal_base_df = rebase_by_group(filtered, group_col="label", value_col="price_m2", new_col="plot_value")
    real_base_df = rebase_by_group(filtered, group_col="label", value_col="price_m2_real", new_col="plot_value")
    chart_variant = st.radio(
        "Série do gráfico",
        ["Nominal", "Real"],
        horizontal=True,
        key="residential_neighborhood_variant",
    )

    cdi_series_col = "cdi_index" if chart_variant == "Nominal" else "cdi_real_index"
    cdi_label = "CDI" if chart_variant == "Nominal" else "CDI Real"
    cdi_plot = build_cdi_window(get_cdi_reference(), *date_range, series=cdi_series_col)
    cdi_plot = cdi_plot if not cdi_plot.empty else None

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
            reference_df=cdi_plot,
            reference_label=cdi_label,
            title="",
            y_title="Base 100",
            compact_legend=len(selected_labels) > 8,
        ),
        use_container_width=True,
        config=plotly_config(),
    )

    render_chart_heading("Tabela comparativa")
    st.dataframe(summary_table, use_container_width=True, hide_index=True)


def render_data_tab(asset_class: str) -> None:
    dataset_names = ["FipeZap cidades", "IGMI-R", "Macro índices", "Comparativo"]
    if asset_class == "residential":
        dataset_names.insert(1, "Bairros")

    render_filter_heading("Base")
    dataset_name = st.selectbox(
        "Dataset",
        options=dataset_names,
        index=None,
        key=f"{asset_class}_data_dataset",
        placeholder="Escolha uma base",
        label_visibility="collapsed",
    )

    if dataset_name is None:
        st.info("Escolha uma base para visualizar os dados.")
        return

    preview_df = get_dataset_preview(dataset_name, asset_class)
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
            file_name=f"{asset_class}_{dataset_name.lower().replace(' ', '_')}.csv",
            mime="text/csv",
        )
    with download_col2:
        st.download_button(
            "Baixar Excel",
            data=xlsx_bytes,
            file_name=f"{asset_class}_{dataset_name.lower().replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_page_footer(city_metadata: dict, asset_class: str) -> None:
    latest_base = city_metadata["max_date"].strftime("%m/%Y")
    segment_label = "residencial" if asset_class == "residential" else "comercial"
    footnote = (
        f"Fontes: FipeZap, ABECIP e Banco Central. "
        f"Valores reais ajustados pelo IPCA; linhas tracejadas indicam série real. "
        f"Segmento {segment_label}; última base FipeZap: {latest_base}."
    )
    render_page_footnote(footnote)


def render_asset_dashboard(asset_class: str) -> None:
    asset = ASSET_CONFIG[asset_class]
    render_hero(
        title=asset["hero_title"],
        description=asset["hero_description"],
    )

    with st.spinner("Carregando estrutura do dashboard..."):
        metadata = get_city_metadata(asset_class)

    if not metadata["cities"]:
        st.error("Não foi possível carregar as séries principais do dashboard.")
        return

    if asset["show_neighborhoods"]:
        tab_panorama, tab_compare, tab_neighborhood, tab_data = st.tabs(["Panorama", "Comparações", "m² por Bairro", "Dados"])
        with tab_panorama:
            render_panorama(asset_class)
        with tab_compare:
            render_comparisons(asset_class)
        with tab_neighborhood:
            render_neighborhoods()
        with tab_data:
            render_data_tab(asset_class)
    else:
        tab_panorama, tab_compare, tab_data = st.tabs(["Panorama", "Comparações", "Dados"])
        with tab_panorama:
            render_panorama(asset_class)
        with tab_compare:
            render_comparisons(asset_class)
        with tab_data:
            render_data_tab(asset_class)

    render_page_footer(metadata, asset_class)


def main() -> None:
    render_filter_heading("Página")
    page_label = st.radio(
        "Página",
        options=[ASSET_CONFIG["residential"]["label"], ASSET_CONFIG["commercial"]["label"]],
        horizontal=True,
        key="asset_page_selector",
        label_visibility="collapsed",
    )
    asset_class = "commercial" if page_label == ASSET_CONFIG["commercial"]["label"] else "residential"
    render_asset_dashboard(asset_class)


main()
