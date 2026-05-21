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

CHART_COLORS = [
    "#163A63",
    "#285989",
    "#3B74A8",
    "#C4963B",
    "#0D7A5F",
    "#A55D3A",
    "#5D4D8C",
    "#7286A0",
]
