from __future__ import annotations

import streamlit as st

from dashboard.config import THEME


def inject_theme() -> None:
    st.markdown(
        f"""
        <style>
            :root {{
                --navy: {THEME["navy"]};
                --navy-soft: {THEME["navy_soft"]};
                --ink: {THEME["ink"]};
                --muted: {THEME["muted"]};
                --paper: {THEME["paper"]};
                --surface: {THEME["surface"]};
                --surface-alt: {THEME["surface_alt"]};
                --accent: {THEME["accent"]};
                --grid: {THEME["grid"]};
                --success: {THEME["success"]};
            }}

            .stApp {{
                background:
                    radial-gradient(circle at top left, rgba(22, 58, 99, 0.08), transparent 30%),
                    linear-gradient(180deg, #f8fbff 0%, var(--paper) 100%);
                color: var(--ink);
                font-family: "Segoe UI", sans-serif;
            }}

            .block-container {{
                padding-top: 2.6rem;
                padding-bottom: 1.5rem;
                max-width: 1360px;
            }}

            h1, h2, h3, h4, h5, h6, p, div, span, label {{
                font-family: "Segoe UI", sans-serif !important;
            }}

            [data-baseweb="tab-list"] {{
                gap: 0.5rem;
                padding: 0.25rem;
                background: rgba(255,255,255,0.85);
                border: 1px solid rgba(16, 33, 61, 0.08);
                border-radius: 999px;
                margin-bottom: 0.35rem;
            }}

            [data-baseweb="tab"] {{
                height: 42px;
                padding: 0 1.15rem;
                border-radius: 999px;
                color: var(--muted);
            }}

            [data-baseweb="tab-panel"] {{
                padding-top: 0.15rem;
            }}

            [aria-selected="true"] {{
                background: var(--navy) !important;
                color: white !important;
            }}

            .panel-card {{
                background: rgba(255,255,255,0.92);
                border: 1px solid rgba(16, 33, 61, 0.08);
                border-radius: 22px;
                padding: 1rem 1.1rem;
                box-shadow: 0 18px 50px rgba(16, 33, 61, 0.05);
            }}

            .hero {{
                padding: 1.7rem 1.2rem 1.05rem 1.2rem;
                border-radius: 22px;
                background:
                    linear-gradient(135deg, rgba(22, 58, 99, 0.98), rgba(40, 89, 137, 0.96)),
                    var(--navy);
                color: white;
                margin-bottom: 0.85rem;
                box-shadow: 0 22px 50px rgba(22, 58, 99, 0.14);
                overflow: visible;
            }}

            .hero h1 {{
                font-size: 1.5rem;
                font-weight: 800;
                margin: 0;
                letter-spacing: -0.02em;
                line-height: 1.2;
                padding-bottom: 0.08rem;
            }}

            .hero p {{
                margin: 0.3rem 0 0 0;
                color: rgba(255,255,255,0.82);
                max-width: 48ch;
                font-size: 0.95rem;
            }}

            .section-label {{
                font-size: 0.78rem;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: rgba(255,255,255,0.68);
                margin-bottom: 0.5rem;
                font-weight: 700;
                line-height: 1.4;
                padding-top: 0.18rem;
                display: block;
            }}

            .metric-card {{
                background: linear-gradient(180deg, rgba(255,255,255,1), rgba(240, 245, 252, 0.95));
                border: 1px solid rgba(16, 33, 61, 0.08);
                border-radius: 20px;
                padding: 0.95rem 1rem;
                margin-bottom: 0.7rem;
                box-shadow: 0 16px 38px rgba(16, 33, 61, 0.05);
            }}

            .metric-label {{
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--muted);
                font-weight: 700;
                margin-bottom: 0.35rem;
            }}

            .metric-value {{
                font-size: 1.55rem;
                color: var(--ink);
                font-weight: 800;
                line-height: 1.1;
            }}

            .metric-meta {{
                margin-top: 0.35rem;
                font-size: 0.92rem;
                color: var(--muted);
            }}

            .stDateInput, .stMultiSelect, .stSelectbox, .stRadio {{
                background: rgba(255,255,255,0.82);
                border-radius: 16px;
            }}

            .stMultiSelect [data-baseweb="tag"] {{
                background: var(--navy) !important;
                border-radius: 10px !important;
                border: 1px solid rgba(255,255,255,0.12) !important;
            }}

            .stMultiSelect [data-baseweb="tag"] span,
            .stMultiSelect [data-baseweb="tag"] svg {{
                color: white !important;
                fill: white !important;
            }}

            .stDateInput [data-baseweb="input"] > div,
            .stMultiSelect [data-baseweb="select"] > div,
            .stSelectbox [data-baseweb="select"] > div {{
                background: var(--navy-soft) !important;
                border: 1px solid rgba(255,255,255,0.1) !important;
                color: white !important;
                border-radius: 14px !important;
            }}

            .stDateInput input,
            .stMultiSelect input,
            .stSelectbox input,
            .stSelectbox div,
            .stDateInput div {{
                color: white !important;
            }}

            .stMultiSelect input::placeholder,
            .stSelectbox input::placeholder,
            .stDateInput input::placeholder {{
                color: rgba(255,255,255,0.92) !important;
                -webkit-text-fill-color: rgba(255,255,255,0.92) !important;
                opacity: 1 !important;
            }}

            .stMultiSelect [data-baseweb="select"] span,
            .stSelectbox [data-baseweb="select"] span {{
                color: white !important;
            }}

            .stMultiSelect [data-baseweb="select"] > div > div,
            .stSelectbox [data-baseweb="select"] > div > div {{
                color: white !important;
                -webkit-text-fill-color: white !important;
            }}

            .stMultiSelect [data-baseweb="select"] [id*="placeholder"],
            .stSelectbox [data-baseweb="select"] [id*="placeholder"] {{
                color: rgba(255,255,255,0.96) !important;
                -webkit-text-fill-color: rgba(255,255,255,0.96) !important;
                opacity: 1 !important;
            }}

            .stDateInput svg,
            .stMultiSelect svg,
            .stSelectbox svg {{
                fill: white !important;
                color: white !important;
            }}

            .stRadio label,
            .stRadio div[role="radiogroup"] {{
                color: var(--ink) !important;
            }}

            .stRadio input[type="radio"] {{
                accent-color: var(--navy);
            }}

            .stRadio div[role="radiogroup"] > label {{
                background: rgba(22, 58, 99, 0.08);
                padding: 0.45rem 0.75rem;
                border-radius: 999px;
                border: 1px solid rgba(22, 58, 99, 0.08);
            }}

            .control-label {{
                text-align: center;
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: var(--muted);
                margin: 0.1rem 0 0.45rem 0;
            }}

            .page-footnote {{
                margin-top: 0.9rem;
                padding-top: 0.45rem;
                color: var(--muted);
                font-size: 0.8rem;
                text-align: center;
            }}

            .chart-heading {{
                margin: 0.1rem 0 0.55rem 0.1rem;
                color: var(--ink);
                font-size: 1rem;
                font-weight: 700;
            }}

            .stDownloadButton button, .stButton button {{
                border-radius: 999px;
                border: 1px solid rgba(22, 58, 99, 0.15);
                color: var(--navy);
                background: white;
            }}

            [data-testid="stAlert"] {{
                background: var(--navy-soft);
                color: white;
                border: 1px solid rgba(255,255,255,0.12);
            }}

            [data-testid="stAlert"] * {{
                color: white !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <div class="section-label">Imóveis Brasil</div>
            <h1>Mercado Residencial</h1>
            <p>Preço nominal, preço real e comparação entre cidades e bairros.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, meta: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_control_label(label: str) -> None:
    st.markdown(f'<div class="control-label">{label}</div>', unsafe_allow_html=True)


def render_page_footnote(text: str) -> None:
    st.markdown(f'<div class="page-footnote">{text}</div>', unsafe_allow_html=True)


def render_chart_heading(title: str) -> None:
    st.markdown(f'<div class="chart-heading">{title}</div>', unsafe_allow_html=True)
