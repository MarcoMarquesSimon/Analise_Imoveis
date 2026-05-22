from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "dados"
CACHE_DIR = PROJECT_ROOT / ".cache"

FIPEZAP_SERIES_FILE = DATA_DIR / "fipezap-serieshistoricas.xlsx"
FIPEZAP_NEIGHBORHOODS_FILE = DATA_DIR / "fipezap_por_estado.xlsx"
IGMI_FILE = DATA_DIR / "igmi-r-serie-historica-fevereiro2026.xlsx"

SGS_CODES = {
    "IPCA": 433,
    "IVG-R": 21340,
    "MVG-R": 25419,
    "CDI": 4390,
}

EXCLUDED_FIPEZAP_SHEETS = {"Resumo", "Aux", "Índice FipeZAP"}

FIPEZAP_SEGMENTS = {
    "residential": {
        "label": "Residencial",
        "sheet_label": "Imóveis residenciais",
        "refs": {
            "date": "B",
            "sale_index": "C",
            "sale_var_12m": "M",
            "sale_price_m2": "R",
            "rent_index": "W",
            "rent_price_m2": "AL",
            "rental_yield": "AQ",
        },
    },
    "commercial": {
        "label": "Comercial",
        "sheet_label": "Imóveis comerciais",
        "refs": {
            "date": "B",
            "sale_index": "AV",
            "sale_var_12m": "AX",
            "sale_price_m2": "AY",
            "rent_index": "AZ",
            "rent_price_m2": "BC",
            "rental_yield": "BD",
        },
    },
}

CITY_NAME_MAP = {
    "sao paulo": "São Paulo",
    "rio de janeiro": "Rio de Janeiro",
    "goiania": "Goiânia",
    "brasilia": "Brasília",
    "florianopolis": "Florianópolis",
    "vitoria": "Vitória",
    "sao jose": "São José",
    "sao luis": "São Luís",
    "joao pessoa": "João Pessoa",
    "belem": "Belém",
    "curitiba": "Curitiba",
    "fortaleza": "Fortaleza",
    "salvador": "Salvador",
    "recife": "Recife",
    "porto alegre": "Porto Alegre",
    "belo horizonte": "Belo Horizonte",
}

THEME = {
    "navy": "#163A63",
    "navy_soft": "#285989",
    "ink": "#10213D",
    "muted": "#66758A",
    "paper": "#F6F8FB",
    "surface": "#FFFFFF",
    "surface_alt": "#EAF0F7",
    "accent": "#C4963B",
    "grid": "#D8E1EE",
    "success": "#0D7A5F",
}

# ── Chart colour palette ────────────────────────────────────────────────────
# Slots are ordered to match how series_labels first appear in the unified
# chart (alphabetical rebase_key sort → Aluguel, Imóvel+Aluguel, Venda,
# then overflow for additional cities):
#   slot 0 → Aluguel family          (vivid orange)
#   slot 1 → Imóvel + Aluguel family (rich teal)
#   slot 2 → Venda family            (strong blue)
#   slots 3-7 → overflow for multi-city or additional families
CHART_COLORS: list[str] = [
    "#EA580C",  # vivid orange  — Aluguel
    "#0D9488",  # rich teal     — Imóvel + Aluguel
    "#2563EB",  # strong blue   — Venda
    "#6366F1",  # indigo        — 4th series/city overflow
    "#0891B2",  # cyan          — 5th
    "#65A30D",  # lime green    — 6th
    "#BE185D",  # magenta-pink  — 7th
    "#64748B",  # slate         — 8th
]

# Global benchmark series are pinned to fixed colours so they are always
# the same regardless of how many cities are selected (overrides the sequence).
SERIES_FIXED_COLORS: dict[str, str] = {
    "CDI": "#7C3AED",   # distinct violet-purple
    "IPCA": "#DC2626",  # warm red
}

# Lighter counterparts for real (IPCA-deflated, dashed) series lines.
# Each nominal base colour maps to its real variant (≈60% lightness).
# Applied per-trace after figure creation so the dash style reinforces
# the nominal vs real hierarchy.
REAL_COLOR_MAP: dict[str, str] = {
    "#EA580C": "#FCA86A",  # Aluguel real       — light orange
    "#0D9488": "#5EEAD4",  # Imóvel+Aluguel real — light teal
    "#2563EB": "#93C5FD",  # Venda real          — light blue
    "#6366F1": "#A5B4FC",  # indigo real
    "#0891B2": "#67E8F9",  # cyan real
    "#65A30D": "#A3E635",  # lime real
    "#BE185D": "#F9A8D4",  # pink real
    "#64748B": "#CBD5E1",  # slate real
}
