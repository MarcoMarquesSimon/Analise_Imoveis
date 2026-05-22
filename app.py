from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import line_chart, neighborhood_chart
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


# ── Return cards ──────────────────────────────────────────────────────────────

_RETURN_CARDS_CSS = """
<style>
.ret-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin:.4rem 0 .85rem}
@media(max-width:640px){.ret-grid{grid-template-columns:1fr}}
.rc{background:#fff;border-left:3px solid #163A63;border-radius:6px;padding:.55rem .75rem}
.rc.pos{border-left-color:#0D7A5F}
.rc.neg{border-left-color:#A55D3A}
.rc.neut{border-left-color:#285989}
.rc-header{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;
           min-height:1.6rem}
.rc-title{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:#66758A;
          font-weight:700;line-height:1.2;align-self:center}
.rc-value{font-size:1.2rem;font-weight:900;color:#10213D;line-height:1;flex-shrink:0;
          white-space:nowrap}
.rc.pos .rc-value{color:#0D7A5F}
.rc.neg .rc-value{color:#A55D3A}
.rc.neut .rc-value{color:#285989}
.rc-sub{font-size:.66rem;color:#66758A;margin-top:.18rem;line-height:1.35}
.rc-ann{font-size:.64rem;color:#8A97A8;margin-top:.1rem}
.rc-badge-win{display:inline-block;padding:.12rem .45rem;border-radius:999px;font-size:.66rem;
              font-weight:700;margin-top:.28rem;background:rgba(13,122,95,.12);color:#0D7A5F;
              box-shadow:0 0 8px rgba(13,122,95,.28)}
.rc-badge-lose{display:inline-block;padding:.12rem .45rem;border-radius:999px;font-size:.66rem;
               font-weight:700;margin-top:.28rem;background:rgba(180,30,30,.1);color:#B41E1E;
               animation:rc-pulse 1.6s ease-in-out infinite}
@keyframes rc-pulse{0%,100%{opacity:1}50%{opacity:.5}}
.rc-bar-wrap{margin-top:.4rem}
.rc-bar-row{display:flex;align-items:center;gap:.35rem;margin-bottom:.16rem;
            font-size:.63rem;color:#66758A}
.rc-bar-lbl{width:2.8rem;text-align:right;white-space:nowrap}
.rc-bar-bg{flex:1;background:#EAF0F7;border-radius:4px;height:5px;overflow:hidden}
.rc-bar-fill{height:100%;border-radius:4px}
</style>
"""


def _rc_n_months(start, end) -> int:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    return max(int((e.year - s.year) * 12 + (e.month - s.month)), 1)


def _rc_annualize(total_pct: float, n_months: int) -> float:
    return ((1 + total_pct / 100) ** (12 / max(n_months, 1)) - 1) * 100


def _rc_total_return(df: pd.DataFrame, price_col: str) -> float | None:
    if df.empty or price_col not in df.columns:
        return None
    results = []
    groups = df.groupby("city") if "city" in df.columns else [(None, df)]
    for _, sub in groups:
        vals = sub.sort_values("date")[price_col].dropna()
        if len(vals) < 2:
            continue
        first = vals.iloc[0]
        if first == 0 or pd.isna(first):
            continue
        results.append((vals.iloc[-1] / first - 1) * 100)
    return sum(results) / len(results) if results else None


def _rc_ipca_return(ipca_reference: pd.DataFrame, date_range: tuple) -> float | None:
    filt = filter_period(ipca_reference, *date_range)
    if filt.empty or "ipca_index" not in filt.columns:
        return None
    valid = filt["ipca_index"].dropna()
    if len(valid) < 2 or valid.iloc[0] == 0:
        return None
    return (valid.iloc[-1] / valid.iloc[0] - 1) * 100


def _rc_fmt(v: float) -> str:
    return f"{v:+,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _rc_na(title: str) -> str:
    return (
        '<div class="rc neut">'
        f'<div class="rc-header">'
        f'<span class="rc-title">{title}</span>'
        '<span class="rc-value" style="font-size:.82rem;color:#66758A;font-weight:600">'
        "Dados insuficientes</span></div></div>"
    )


def render_return_cards(
    filtered: pd.DataFrame,
    market: dict,
    date_range: tuple,
    ipca_reference: pd.DataFrame,
    rental_income_pct: float | None = None,
) -> None:
    st.markdown(_RETURN_CARDS_CSS, unsafe_allow_html=True)

    n_months = _rc_n_months(date_range[0], date_range[1])
    nom_total = _rc_total_return(filtered, market["price_col"])
    real_total = (
        _rc_total_return(filtered, market["real_col"])
        if market.get("supports_real") and market.get("real_col") in filtered.columns
        else None
    )
    ipca_total = _rc_ipca_return(ipca_reference, date_range)

    # When the real price column is unavailable (e.g. yield mode), derive real return
    # directly from the formula: ((1 + nominal) / (1 + inflation)) − 1
    if real_total is None and nom_total is not None and ipca_total is not None:
        real_total = ((1 + nom_total / 100) / (1 + ipca_total / 100) - 1) * 100

    # Card 1 — Retorno Nominal
    if nom_total is not None:
        nom_ann = _rc_annualize(nom_total, n_months)
        cls = "pos" if nom_total >= 0 else "neg"
        _income_line = ""
        if rental_income_pct is not None:
            _income_line = (
                f'<div class="rc-ann">do qual {_rc_fmt(rental_income_pct)} pp de renda de aluguel</div>'
            )
        c1 = (
            f'<div class="rc {cls}">'
            '<div class="rc-header">'
            '<span class="rc-title">Retorno Nominal</span>'
            f'<span class="rc-value">{_rc_fmt(nom_total)}</span>'
            "</div>"
            f'<div class="rc-sub">{n_months} meses</div>'
            f'<div class="rc-ann">{_rc_fmt(nom_ann)} a.a.</div>'
            f'{_income_line}'
            "</div>"
        )
    else:
        c1 = _rc_na("Retorno Nominal")

    # Card 2 — Retorno Real (ajustado pelo IPCA)
    if real_total is not None:
        real_ann = _rc_annualize(real_total, n_months)
        cls = "pos" if real_total >= 0 else "neg"
        if ipca_total is not None:
            ipca_str = "0%" if ipca_total == 0 else _rc_fmt(ipca_total)
            ipca_line = f"Infla&ccedil;&atilde;o no per&iacute;odo: {ipca_str}"
        else:
            ipca_line = "IPCA: 0%"
        c2 = (
            f'<div class="rc {cls}">'
            '<div class="rc-header">'
            '<span class="rc-title">Retorno Real (ajustado pelo IPCA)</span>'
            f'<span class="rc-value">{_rc_fmt(real_total)}</span>'
            "</div>"
            f'<div class="rc-sub">{ipca_line}</div>'
            f'<div class="rc-ann">{_rc_fmt(real_ann)} a.a. real</div>'
            "</div>"
        )
    else:
        c2 = _rc_na("Retorno Real (ajustado pelo IPCA)")

    # Card 3 — Ganho Real vs Inflação
    if nom_total is not None and ipca_total is not None:
        spread = nom_total - ipca_total
        cls3 = "pos" if spread > 0 else "neg"
        if spread > 0:
            badge = '<div class="rc-badge-win">&#10022; Bateu a infla&ccedil;&atilde;o</div>'
        else:
            badge = '<div class="rc-badge-lose">&#10008; Perdeu para a infla&ccedil;&atilde;o</div>'
        max_abs = max(abs(nom_total), abs(ipca_total), 0.1)
        asset_w = int(min(abs(nom_total) / max_abs * 100, 100))
        ipca_w = int(min(abs(ipca_total) / max_abs * 100, 100))
        asset_color = "#0D7A5F" if nom_total >= ipca_total else "#A55D3A"
        bar = (
            '<div class="rc-bar-wrap">'
            '<div class="rc-bar-row">'
            '<span class="rc-bar-lbl">Im&oacute;vel</span>'
            f'<div class="rc-bar-bg"><div class="rc-bar-fill" style="width:{asset_w}%;background:{asset_color}"></div></div>'
            f'<span>{_rc_fmt(nom_total)}</span></div>'
            '<div class="rc-bar-row">'
            '<span class="rc-bar-lbl">IPCA</span>'
            f'<div class="rc-bar-bg"><div class="rc-bar-fill" style="width:{ipca_w}%;background:#163A63"></div></div>'
            f'<span>{_rc_fmt(ipca_total)}</span></div>'
            "</div>"
        )
        c3 = (
            f'<div class="rc {cls3}">'
            '<div class="rc-header">'
            '<span class="rc-title">Ganho Real vs Infla&ccedil;&atilde;o</span>'
            f'<span class="rc-value">{_rc_fmt(spread)} p.p.</span>'
            "</div>"
            f"{badge}"
            f"{bar}"
            "</div>"
        )
    else:
        c3 = _rc_na("Ganho Real vs Inflação")

    st.markdown(f'<div class="ret-grid">{c1}{c2}{c3}</div>', unsafe_allow_html=True)


def get_market_config(asset_class: str, market_type: str, rent_view: str = "Imóvel + Aluguel") -> dict:
    if asset_class == "commercial":
        names = {
            "sale_composite": "FipeZap Comercial Venda Composto",
            "rent_composite": "FipeZap Comercial Aluguel Composto",
            "received_composite": "Aluguel Comercial Recebido Composto",
            "yield_composite": "Imóvel — Yield de Aluguel Comercial Composto",
            "sale_title": "Preço do m² de venda comercial por cidade",
            "received_title": "Imóvel + Aluguel — Recebimento comercial por cidade",
            "yield_title": "Imóvel — Yield de aluguel comercial por cidade",
        }
    else:
        names = {
            "sale_composite": "FipeZap Venda Composto",
            "rent_composite": "FipeZap Aluguel Composto",
            "received_composite": "Aluguel Recebido Composto",
            "yield_composite": "Imóvel — Yield de Aluguel Composto",
            "sale_title": "Preço do m² de venda por cidade",
            "received_title": "Imóvel + Aluguel — Recebimento por cidade",
            "yield_title": "Imóvel — Yield de aluguel por cidade",
        }

    if market_type == "Aluguel":
        if rent_view == "Imóvel":
            return {
                "label": "imóvel",
                "price_col": "rental_yield",
                "real_col": "rental_yield",
                "secondary_series": [names["yield_composite"], names["rent_composite"], "IPCA", "CDI", "CDI Real"],
                "composite_series": names["yield_composite"],
                "value_prefix": "",
                "value_suffix": "%",
                "value_format": ",.2f",
                "multiplier": 100.0,
                "y_title": "Imóvel — Yield (%)",
                "supports_real": False,
                "chart_heading": names["yield_title"],
            }
        return {
            "label": "imóvel + aluguel",
            "price_col": "aluguel_m2",
            "real_col": "aluguel_m2_real",
            "secondary_series": [names["received_composite"], names["rent_composite"], "IPCA", "CDI", "CDI Real"],
            "composite_series": names["received_composite"],
            "value_prefix": "R$ ",
            "value_suffix": "/m²",
            "value_format": ",.2f",
            "multiplier": 1.0,
            "supports_real": True,
            "y_title": "Imóvel + Aluguel (R$/m²)",
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

    # ── Filters: Cidades · Período · Escala ───────────────────────────────────
    filter_col1, filter_col2, filter_col3 = st.columns([1.45, 1.0, 0.85])
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
        render_filter_heading("Escala")
        chart_mode = st.radio(
            "Escala",
            ["Base 100", "Valor"],
            horizontal=True,
            key=f"{key_prefix}_mode",
            label_visibility="collapsed",
        )

    if len(date_range) != 2 or not selected_cities:
        st.info("Escolha uma ou mais cidades para começar a análise.")
        return

    # ── Series selector panel ──────────────────────────────────────────────────
    # 8 series: 4 per-city price series + 2 total-return series + 2 global benchmarks.
    # CDI and IPCA only render in Base 100 mode (no R$/m² denomination).
    # Imóvel + Aluguel: cumulative total return (capital gain + rental income),
    # uses indice_total_return_window scaled to R$/m² in Valor mode.
    _ALL_SERIES = [
        "Venda — Nominal",
        "Venda — Real",
        "Imóvel + Aluguel — Nominal",
        "Imóvel + Aluguel — Real",
        "Aluguel — Nominal",
        "Aluguel — Real",
        "CDI",
        "IPCA",
    ]
    _DEFAULT_SERIES = ["Venda — Nominal", "Imóvel + Aluguel — Nominal", "IPCA"]

    sel_key = f"{key_prefix}_series_sel"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = _DEFAULT_SERIES[:]

    _shd_col, _sall_col, _sclr_col = st.columns([2.8, 0.7, 0.5])
    with _shd_col:
        render_filter_heading("Séries")
    with _sall_col:
        if st.button("Selecionar tudo", key=f"{key_prefix}_series_all"):
            st.session_state[sel_key] = _ALL_SERIES[:]
    with _sclr_col:
        if st.button("Limpar", key=f"{key_prefix}_series_clr"):
            st.session_state[sel_key] = []

    selected_series = st.multiselect(
        "Séries",
        options=_ALL_SERIES,
        key=sel_key,
        label_visibility="collapsed",
    )

    if not selected_series:
        st.info("Selecione ao menos uma série para exibir.")
        return

    # ── Load and prepare data ──────────────────────────────────────────────────
    ipca_reference = get_ipca_reference()
    city_series = ensure_total_return_columns(ensure_rent_gain_columns(get_city_series(asset_class)))
    city_series = ensure_real_series(city_series, "sale_price_m2", "sale_price_m2_real", ipca_reference)
    city_series = ensure_real_series(city_series, "rent_price_m2", "rent_price_m2_real", ipca_reference)
    filtered = filter_period(city_series[city_series["city"].isin(selected_cities)], *date_range)
    filtered = filtered.sort_values(["city", "date"])
    filtered = add_window_total_return_indices(filtered, group_col="city")

    # ── Build plot frames ──────────────────────────────────────────────────────
    # color_col = "{city} — Venda" / "{city} — Imóvel + Aluguel" / "{city} — Aluguel"
    #   → same hue for nominal/real pair of each city+family
    # dash_col  = "Nominal" (solid) or "Real" (dashed)
    # rebase_key = unique per (city, family, dash) for independent Base-100 rebasing

    _PRICE_MAP: dict[str, tuple[str, str, str]] = {
        "Venda — Nominal":   ("sale_price_m2",     "Venda",   "Nominal"),
        "Venda — Real":      ("sale_price_m2_real", "Venda",   "Real"),
        "Aluguel — Nominal": ("rent_price_m2",      "Aluguel", "Nominal"),
        "Aluguel — Real":    ("rent_price_m2_real", "Aluguel", "Real"),
    }

    plot_frames: list[pd.DataFrame] = []

    for label in selected_series:
        if label not in _PRICE_MAP:
            continue
        col, family, dash = _PRICE_MAP[label]
        if col not in filtered.columns:
            continue
        df_s = filtered[["date", "city", col]].copy().dropna(subset=[col])
        df_s["plot_value"] = df_s[col]
        df_s["series_label"] = df_s["city"] + " — " + family
        df_s["dash_type"] = dash
        df_s["rebase_key"] = df_s["city"] + " — " + family + " — " + dash
        plot_frames.append(df_s[["date", "series_label", "dash_type", "rebase_key", "plot_value"]])

    # ── Imóvel + Aluguel: cumulative total return (capital gain + rental income) ──
    # Source: indice_total_return_window / indice_total_return_real_window
    #   (pre-computed by add_window_total_return_indices from retorno_total_pct,
    #    which compounds capital return + monthly rental_yield at each month).
    # Valor mode: scaled to R$/m² starting at the same initial sale price as Venda.
    # Base 100 mode: rebase_by_group normalises each series independently to 100.
    # Edge case: missing rental_yield is zero-filled (conservative, no error thrown).
    _ia_nom_sel = "Imóvel + Aluguel — Nominal" in selected_series
    _ia_real_sel = "Imóvel + Aluguel — Real" in selected_series

    if _ia_nom_sel or _ia_real_sel:
        _tr_cols = ["date", "city", "sale_price_m2", "sale_price_m2_real",
                    "indice_total_return_window", "indice_total_return_real_window"]
        _tr = filtered[[c for c in _tr_cols if c in filtered.columns]].copy()
        _tr = _tr.sort_values(["city", "date"])
        _tr["_init_nom_idx"] = _tr.groupby("city")["indice_total_return_window"].transform("first")
        _tr["_init_real_idx"] = _tr.groupby("city")["indice_total_return_real_window"].transform("first")
        _tr["_init_px_nom"] = _tr.groupby("city")["sale_price_m2"].transform("first")
        _tr["_init_px_real"] = _tr.groupby("city")["sale_price_m2_real"].transform("first")

        if _ia_nom_sel:
            tr_nom = _tr.copy()
            tr_nom["plot_value"] = (
                tr_nom["indice_total_return_window"]
                / tr_nom["_init_nom_idx"].replace(0, 1.0)
                * tr_nom["_init_px_nom"]
            )
            tr_nom["series_label"] = tr_nom["city"] + " — Imóvel + Aluguel"
            tr_nom["dash_type"] = "Nominal"
            tr_nom["rebase_key"] = tr_nom["city"] + " — Imóvel + Aluguel — Nominal"
            plot_frames.append(tr_nom[["date", "series_label", "dash_type", "rebase_key", "plot_value"]])

        if _ia_real_sel:
            tr_real = _tr.copy()
            tr_real["plot_value"] = (
                tr_real["indice_total_return_real_window"]
                / tr_real["_init_real_idx"].replace(0, 1.0)
                * tr_real["_init_px_real"]
            )
            tr_real["series_label"] = tr_real["city"] + " — Imóvel + Aluguel"
            tr_real["dash_type"] = "Real"
            tr_real["rebase_key"] = tr_real["city"] + " — Imóvel + Aluguel — Real"
            plot_frames.append(tr_real[["date", "series_label", "dash_type", "rebase_key", "plot_value"]])

        # Footnote for cities with no rental_yield data in the selected window
        _cities_no_yield = [
            city
            for city, sub in filtered.groupby("city")
            if "rental_yield" not in sub.columns or sub["rental_yield"].isna().all()
        ]
        if _cities_no_yield:
            st.caption(
                "¹ Yield de aluguel indisponível para o período em: "
                + ", ".join(_cities_no_yield)
                + ". Imóvel + Aluguel reflete apenas valorização do imóvel."
            )

    # Global benchmarks — only meaningful in Base 100 (no R$/m² unit)
    _global_in_valor = [s for s in ["CDI", "IPCA"] if s in selected_series and chart_mode == "Valor"]
    if _global_in_valor:
        st.caption(
            "ℹ️ "
            + " e ".join(_global_in_valor)
            + " não são exibidos no modo Valor (sem unidade R$/m²). "
            "Mude para Base 100 para incluí-los."
        )

    if chart_mode == "Base 100":
        if "CDI" in selected_series:
            cdi_ref = get_cdi_reference()
            cdi_win = filter_period(cdi_ref, *date_range)
            if not cdi_win.empty and "cdi_index" in cdi_win.columns:
                cdi_df = cdi_win[["date", "cdi_index"]].copy()
                cdi_df["plot_value"] = cdi_df["cdi_index"]
                cdi_df["series_label"] = "CDI"
                cdi_df["dash_type"] = "Nominal"
                cdi_df["rebase_key"] = "CDI"
                plot_frames.append(cdi_df[["date", "series_label", "dash_type", "rebase_key", "plot_value"]])

        if "IPCA" in selected_series:
            ipca_win = filter_period(ipca_reference, *date_range)
            if not ipca_win.empty and "ipca_index" in ipca_win.columns:
                ipca_df = ipca_win[["date", "ipca_index"]].copy()
                ipca_df["plot_value"] = ipca_df["ipca_index"]
                ipca_df["series_label"] = "IPCA"
                ipca_df["dash_type"] = "Nominal"
                ipca_df["rebase_key"] = "IPCA"
                plot_frames.append(ipca_df[["date", "series_label", "dash_type", "rebase_key", "plot_value"]])

    if not plot_frames:
        st.info("Nenhuma série disponível para as cidades e período selecionados.")
        return

    plot_df = pd.concat(plot_frames, ignore_index=True).sort_values(["rebase_key", "date"])

    if chart_mode == "Base 100":
        plot_df = rebase_by_group(
            plot_df, group_col="rebase_key", value_col="plot_value", new_col="plot_value"
        )
        y_title = "Base 100"
        val_prefix, val_suffix, val_format = "", "", ",.1f"
    else:
        y_title = "R$/m²"
        val_prefix, val_suffix, val_format = "R$ ", "/m²", ",.0f"

    # ── KPI Return cards ───────────────────────────────────────────────────────
    # When "Imóvel + Aluguel — Nominal" is selected, the Retorno Nominal KPI
    # reflects the total return (capital + income). A secondary line shows
    # how many pp came from rental income vs pure capital appreciation.
    _tr_nom_kpi = "Imóvel + Aluguel — Nominal" in selected_series
    _tr_real_kpi = "Imóvel + Aluguel — Real" in selected_series

    if _tr_nom_kpi:
        _kpi_market = {
            "price_col": "indice_total_return_window",
            "real_col": "indice_total_return_real_window",
            "supports_real": _tr_real_kpi,
            "multiplier": 1.0,
        }
        # Rental income contribution ≈ total_return − capital_only (pp, approximate)
        _tot_ret = _rc_total_return(filtered, "indice_total_return_window")
        _cap_ret = _rc_total_return(filtered, "sale_price_m2")
        _rental_income_pct = (
            _tot_ret - _cap_ret
            if _tot_ret is not None and _cap_ret is not None
            else None
        )
    else:
        _kpi_market = {
            "price_col": "sale_price_m2",
            "real_col": "sale_price_m2_real",
            "supports_real": True,
            "multiplier": 1.0,
        }
        _rental_income_pct = None

    render_return_cards(filtered, _kpi_market, date_range, ipca_reference, rental_income_pct=_rental_income_pct)

    # ── Unified chart ──────────────────────────────────────────────────────────
    n_unique_labels = plot_df["series_label"].nunique()
    render_chart_heading("Evolução das séries selecionadas")
    st.plotly_chart(
        line_chart(
            plot_df,
            value_col="plot_value",
            color_col="series_label",
            title="",
            y_title=y_title,
            value_prefix=val_prefix,
            value_suffix=val_suffix,
            value_format=val_format,
            dash_col="dash_type",
            dash_map={"Nominal": "solid", "Real": "dash"},
            compact_legend=n_unique_labels > 8,
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
        tab_panorama, tab_neighborhood, tab_data = st.tabs(["Panorama", "m² por Bairro", "Dados"])
        with tab_panorama:
            render_panorama(asset_class)
        with tab_neighborhood:
            render_neighborhoods()
        with tab_data:
            render_data_tab(asset_class)
    else:
        tab_panorama, tab_data = st.tabs(["Panorama", "Dados"])
        with tab_panorama:
            render_panorama(asset_class)
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
