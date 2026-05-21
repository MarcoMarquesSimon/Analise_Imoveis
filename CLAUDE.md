# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

## Architecture

This is a single-page Streamlit dashboard for Brazilian real-estate market analysis. The entry point is `app.py`; everything else lives under `dashboard/`.

| Module | Role |
|---|---|
| `app.py` | All Streamlit UI logic — filters, tabs, chart rendering, KPI cards |
| `dashboard/config.py` | Paths, theme palette, `SGS_CODES`, `FIPEZAP_SEGMENTS` column-letter maps |
| `dashboard/data.py` | Data loading, IPCA deflation, transformations, disk cache |
| `dashboard/charts.py` | Stateless Plotly figure factories (`line_chart`, `comparison_chart`, `neighborhood_chart`) |
| `dashboard/ui.py` | CSS injection (`inject_theme`) and HTML component helpers |
| `dados/` | Source Excel files (FipeZap series, FipeZap bairros, IGMI-R) |
| `.cache/` | Auto-managed pickle cache — delete to force a full reload |

## Data flow

1. **Excel parsing** — FipeZap workbooks are parsed with a custom low-level XML reader (`_parse_fipezap_sheet` in `data.py`) that reads directly from the `.xlsx` ZIP. Column letters per metric are hardcoded in `FIPEZAP_SEGMENTS` inside `config.py`; updating to a new workbook layout means updating those letter refs.

2. **BCB API** — IPCA (433), IVG-R (21340) and MVG-R (25419) are fetched from the Banco Central SGS API via `fetch_sgs_series`. Results are cached for 12 h; stale data is served on network failure.

3. **Real-value deflation** — `merge_with_ipca` joins price series to the IPCA reference table and multiplies by `deflator_to_latest` (ratio of latest IPCA index to each row's index). The IPCA reference is built once in `load_ipca_reference`.

4. **Total return** — `add_total_return_columns` computes `aluguel_m2 + ganho_capital_m2` for nominal and real variants, then compounds them into `indice_total_return` and `indice_total_return_real`.

## Caching strategy

There are two cache layers:
- **`lru_cache`** — in-process, cleared on restart.
- **Disk pickle cache** (`.cache/*.pkl`) — keyed by source file `mtime` + size; rebuilt automatically when source files change. Macro/API data is keyed by age (`max_age_seconds=43200`).

Streamlit's `@st.cache_data(persist="disk")` is used in `app.py` on top of the `dashboard/data.py` functions as a third layer; this is the cache that `st.cache_data.clear()` would affect.

## Asset classes

The dashboard supports two segments — `"residential"` and `"commercial"` — selected via a top-level radio button in `app.py`. The segment string is threaded through `load_fipezap_city_series`, `get_city_series`, etc. The commercial tab omits the neighborhood analysis (controlled by `ASSET_CONFIG["commercial"]["show_neighborhoods"] = False`).

## Adding or updating data sources

- **New FipeZap workbook**: replace `dados/fipezap-serieshistoricas.xlsx`. If column layout changed, update `FIPEZAP_SEGMENTS` in `config.py`.
- **New neighborhood file**: replace `dados/fipezap_por_estado.xlsx` (sheet must be named `base_longa` with columns `data`, `estado`, `cidade`, `bairro`, `preco_m2`, `variacao_12m`).
- **New IGMI-R file**: replace `dados/igmi-r-serie-historica-fevereiro2026.xlsx`; update `IGMI_FILE` in `config.py` if the filename changes.
- After replacing any Excel file, delete `.cache/` to force a rebuild.
