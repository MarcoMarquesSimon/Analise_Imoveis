from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
import pickle
import time
import unicodedata

import pandas as pd
import requests

from dashboard.config import (
    CACHE_DIR,
    CITY_NAME_MAP,
    EXCLUDED_FIPEZAP_SHEETS,
    FIPEZAP_NEIGHBORHOODS_FILE,
    FIPEZAP_SERIES_FILE,
    IGMI_FILE,
    SGS_CODES,
)


FIPEZAP_USECOLS = [1, 2, 12, 17, 22, 37, 42]
FIPEZAP_COLUMNS = [
    "date",
    "sale_index",
    "sale_var_12m",
    "sale_price_m2",
    "rent_index",
    "rent_price_m2",
    "rental_yield",
]
MACRO_CACHE_MAX_AGE_SECONDS = 60 * 60 * 12


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_file(cache_name: str):
    _ensure_cache_dir()
    return CACHE_DIR / f"{cache_name}.pkl"


def _source_signature(paths: list) -> tuple:
    signature = []
    for path in paths:
        stat = path.stat()
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _load_disk_cache(
    cache_name: str,
    builder,
    source_paths: list | None = None,
    max_age_seconds: int | None = None,
    allow_stale_on_error: bool = False,
):
    cache_path = _cache_file(cache_name)
    cached_payload = None
    if cache_path.exists():
        try:
            with cache_path.open("rb") as file:
                cached_payload = pickle.load(file)
        except Exception:
            cached_payload = None

    expected_signature = _source_signature(source_paths) if source_paths else None
    if cached_payload is not None:
        signature_ok = expected_signature is None or cached_payload.get("signature") == expected_signature
        age_ok = max_age_seconds is None or (time.time() - cached_payload.get("created_at", 0) <= max_age_seconds)
        if signature_ok and age_ok:
            return cached_payload["data"]

    try:
        data = builder()
    except Exception:
        if allow_stale_on_error and cached_payload is not None:
            return cached_payload["data"]
        raise

    payload = {
        "created_at": time.time(),
        "signature": expected_signature,
        "data": data,
    }
    with cache_path.open("wb") as file:
        pickle.dump(payload, file, protocol=pickle.HIGHEST_PROTOCOL)
    return data


def standardize_city_name(name: str) -> str:
    if pd.isna(name):
        return name
    clean = " ".join(str(name).strip().split())
    ascii_name = (
        unicodedata.normalize("NFKD", clean)
        .encode("ascii", "ignore")
        .decode("utf-8")
        .lower()
    )
    return CITY_NAME_MAP.get(ascii_name, clean)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({".": None, "": None}), errors="coerce")


def _prepare_fipezap_frame(raw_df: pd.DataFrame, label: str) -> pd.DataFrame:
    df = raw_df.copy()
    df.columns = FIPEZAP_COLUMNS
    df = df[df["date"].notna() & (df["date"] != "Data")].copy()
    df["date"] = pd.to_datetime(
        df["date"].astype(str),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )
    df = df[df["date"].notna()].copy()

    for column in FIPEZAP_COLUMNS[1:]:
        df[column] = _coerce_numeric(df[column])

    df["city"] = standardize_city_name(label)
    df["source"] = "FipeZap"
    return df.sort_values("date").reset_index(drop=True)


@lru_cache(maxsize=1)
def load_fipezap_city_series() -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        workbook = pd.ExcelFile(FIPEZAP_SERIES_FILE)
        frames = []

        for sheet in workbook.sheet_names:
            if sheet in EXCLUDED_FIPEZAP_SHEETS:
                continue
            raw_df = workbook.parse(
                sheet_name=sheet,
                header=None,
                skiprows=3,
                usecols=FIPEZAP_USECOLS,
            )
            frames.append(_prepare_fipezap_frame(raw_df, label=sheet))

        return pd.concat(frames, ignore_index=True)

    return _load_disk_cache(
        "fipezap_city_series",
        builder=builder,
        source_paths=[FIPEZAP_SERIES_FILE],
    )


@lru_cache(maxsize=1)
def load_city_metadata() -> dict:
    def builder() -> dict:
        workbook = pd.ExcelFile(FIPEZAP_SERIES_FILE)
        cities = sorted([sheet for sheet in workbook.sheet_names if sheet not in EXCLUDED_FIPEZAP_SHEETS])
        sample_sheet = "Índice FipeZAP" if "Índice FipeZAP" in workbook.sheet_names else cities[0]
        raw_df = workbook.parse(
            sheet_name=sample_sheet,
            header=None,
            skiprows=3,
            usecols=[1],
        )
        raw_df.columns = ["date"]
        raw_df = raw_df[raw_df["date"].notna() & (raw_df["date"] != "Data")].copy()
        raw_df["date"] = pd.to_datetime(
            raw_df["date"].astype(str),
            format="%Y-%m-%d %H:%M:%S",
            errors="coerce",
        )
        raw_df = raw_df[raw_df["date"].notna()].copy()
        return {
            "cities": [standardize_city_name(city) for city in cities],
            "min_date": raw_df["date"].min(),
            "max_date": raw_df["date"].max(),
        }

    return _load_disk_cache(
        "city_metadata",
        builder=builder,
        source_paths=[FIPEZAP_SERIES_FILE],
    )


@lru_cache(maxsize=1)
def load_fipezap_composite_series() -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        workbook = pd.ExcelFile(FIPEZAP_SERIES_FILE)
        raw_df = workbook.parse(
            sheet_name="Índice FipeZAP",
            header=None,
            skiprows=3,
            usecols=FIPEZAP_USECOLS,
        )
        return _prepare_fipezap_frame(raw_df, label="FipeZap Composto")

    return _load_disk_cache(
        "fipezap_composite_series",
        builder=builder,
        source_paths=[FIPEZAP_SERIES_FILE],
    )


@lru_cache(maxsize=1)
def load_neighborhood_series() -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        df = pd.read_excel(FIPEZAP_NEIGHBORHOODS_FILE, sheet_name="base_longa")
        df = df.rename(
            columns={
                "data": "date",
                "estado": "state",
                "cidade": "city",
                "bairro": "neighborhood",
                "preco_m2": "price_m2",
                "variacao_12m": "var_12m",
            }
        )
        df["date"] = pd.to_datetime(df["date"].astype(str) + "-01", errors="coerce")
        df["city"] = df["city"].map(standardize_city_name)
        df["price_m2"] = _coerce_numeric(df["price_m2"])
        df["var_12m"] = _coerce_numeric(df["var_12m"])
        df["label"] = df["neighborhood"] + " • " + df["city"]
        df["source"] = "FipeZap bairros"
        return df.sort_values(["city", "neighborhood", "date"]).reset_index(drop=True)

    return _load_disk_cache(
        "neighborhood_series",
        builder=builder,
        source_paths=[FIPEZAP_NEIGHBORHOODS_FILE],
    )


@lru_cache(maxsize=1)
def load_neighborhood_city_options() -> list[str]:
    def builder() -> list[str]:
        df = pd.read_excel(FIPEZAP_NEIGHBORHOODS_FILE, sheet_name="base_longa", usecols=["cidade"])
        cities = df["cidade"].dropna().map(standardize_city_name).drop_duplicates().sort_values().tolist()
        return cities

    return _load_disk_cache(
        "neighborhood_city_options",
        builder=builder,
        source_paths=[FIPEZAP_NEIGHBORHOODS_FILE],
    )


@lru_cache(maxsize=1)
def load_neighborhood_metadata() -> dict:
    def builder() -> dict:
        df = pd.read_excel(FIPEZAP_NEIGHBORHOODS_FILE, sheet_name="base_longa", usecols=["data", "cidade"])
        dates = pd.to_datetime(df["data"].astype(str) + "-01", errors="coerce").dropna()
        cities = df["cidade"].dropna().map(standardize_city_name).drop_duplicates().sort_values().tolist()
        return {
            "cities": cities,
            "min_date": dates.min(),
            "max_date": dates.max(),
        }

    return _load_disk_cache(
        "neighborhood_metadata",
        builder=builder,
        source_paths=[FIPEZAP_NEIGHBORHOODS_FILE],
    )


@lru_cache(maxsize=1)
def load_igmi_series() -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        raw_df = pd.read_excel(IGMI_FILE, sheet_name=0, header=None)
        headers = raw_df.iloc[4].tolist()
        df = raw_df.iloc[5:].copy()
        df.columns = headers
        df = df.rename(columns={"Mês": "raw_month", "BRASIL": "Brasil"})
        df["date"] = pd.to_datetime(df["raw_month"], format="%Y %m", errors="coerce")
        df = df[df["date"].notna()].copy()

        value_columns = [
            column
            for column in df.columns
            if column not in {"raw_month", "date", "var% 12 meses"}
        ]

        melted = df.melt(
            id_vars=["date"],
            value_vars=value_columns,
            var_name="city",
            value_name="value",
        )
        melted["value"] = _coerce_numeric(melted["value"])
        melted = melted[melted["value"].notna()].copy()
        melted["city"] = melted["city"].map(standardize_city_name)
        melted["indicator"] = "IGMI-R"
        melted["series_name"] = melted["city"].apply(
            lambda city: "IGMI-R Brasil" if city == "Brasil" else f"IGMI-R {city}"
        )
        melted["source"] = "ABECIP"
        return melted.sort_values(["city", "date"]).reset_index(drop=True)

    return _load_disk_cache(
        "igmi_series",
        builder=builder,
        source_paths=[IGMI_FILE],
    )


def fetch_sgs_series(series_name: str) -> pd.DataFrame:
    code = SGS_CODES[series_name]
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    df["date"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
    df["value"] = _coerce_numeric(df["valor"])
    df = df[df["date"].notna()].copy()
    df["indicator"] = series_name
    df["source"] = "Banco Central do Brasil"
    return df[["date", "indicator", "value", "source"]].sort_values("date")


@lru_cache(maxsize=1)
def load_macro_series() -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        frames = []
        with ThreadPoolExecutor(max_workers=len(SGS_CODES)) as executor:
            futures = [executor.submit(fetch_sgs_series, series_name) for series_name in SGS_CODES]
            for future in futures:
                try:
                    frames.append(future.result())
                except requests.RequestException:
                    continue

        if not frames:
            return pd.DataFrame(columns=["date", "indicator", "value", "source"])

        return pd.concat(frames, ignore_index=True)

    return _load_disk_cache(
        "macro_series",
        builder=builder,
        max_age_seconds=MACRO_CACHE_MAX_AGE_SECONDS,
        allow_stale_on_error=True,
    )


@lru_cache(maxsize=1)
def load_ipca_reference() -> pd.DataFrame:
    macro = load_macro_series()
    ipca = macro[macro["indicator"] == "IPCA"].copy()
    if ipca.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "ipca_monthly_pct",
                "ipca_index",
                "deflator_to_latest",
                "ipca_cumulative_pct",
            ]
        )

    ipca = ipca.sort_values("date").reset_index(drop=True)
    ipca["ipca_monthly_pct"] = ipca["value"]
    ipca["ipca_index"] = (1 + ipca["ipca_monthly_pct"] / 100).cumprod() * 100
    latest_index = ipca["ipca_index"].iloc[-1]
    ipca["deflator_to_latest"] = latest_index / ipca["ipca_index"]
    ipca["ipca_cumulative_pct"] = (ipca["ipca_index"] / ipca["ipca_index"].iloc[0] - 1) * 100
    return ipca[
        [
            "date",
            "ipca_monthly_pct",
            "ipca_index",
            "deflator_to_latest",
            "ipca_cumulative_pct",
        ]
    ]


def merge_with_ipca(df: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    ipca = load_ipca_reference()
    if ipca.empty:
        merged = df.copy()
        for column in value_columns:
            merged[f"{column}_real"] = merged[column]
        return merged

    merged = df.merge(ipca[["date", "ipca_index", "deflator_to_latest"]], on="date", how="left")
    merged["deflator_to_latest"] = merged["deflator_to_latest"].ffill().bfill().fillna(1.0)

    for column in value_columns:
        merged[f"{column}_real"] = merged[column] * merged["deflator_to_latest"]

    return merged


def add_rent_gain_columns(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.copy()
    enriched["rent_gain_nominal"] = enriched["rental_yield"] * enriched["sale_price_m2"]
    if "sale_price_m2_real" in enriched.columns:
        enriched["rent_gain_real"] = enriched["rental_yield"] * enriched["sale_price_m2_real"]
    else:
        enriched["rent_gain_real"] = enriched["rent_gain_nominal"]
    return enriched


def add_total_return_columns(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.sort_values(["city", "date"]).copy()
    group = enriched.groupby("city", group_keys=False)

    prev_sale = group["sale_price_m2"].shift(1)
    enriched["aluguel_m2"] = enriched["sale_price_m2"] * enriched["rental_yield"]
    enriched["ganho_capital_m2"] = (enriched["sale_price_m2"] - prev_sale).fillna(0.0)
    capital_return_pct = ((enriched["sale_price_m2"] / prev_sale) - 1).replace([pd.NA, pd.NaT], 0.0)
    capital_return_pct = capital_return_pct.fillna(0.0)
    enriched["retorno_total_m2"] = enriched["ganho_capital_m2"] + enriched["aluguel_m2"]
    enriched["retorno_total_pct"] = capital_return_pct + enriched["rental_yield"].fillna(0.0)

    prev_sale_real = group["sale_price_m2_real"].shift(1) if "sale_price_m2_real" in enriched.columns else None
    if prev_sale_real is not None:
        enriched["aluguel_m2_real"] = enriched["sale_price_m2_real"] * enriched["rental_yield"]
        enriched["ganho_capital_m2_real"] = (enriched["sale_price_m2_real"] - prev_sale_real).fillna(0.0)
        capital_return_pct_real = ((enriched["sale_price_m2_real"] / prev_sale_real) - 1).replace([pd.NA, pd.NaT], 0.0)
        capital_return_pct_real = capital_return_pct_real.fillna(0.0)
        enriched["retorno_total_m2_real"] = enriched["ganho_capital_m2_real"] + enriched["aluguel_m2_real"]
        enriched["retorno_total_pct_real"] = capital_return_pct_real + enriched["rental_yield"].fillna(0.0)
    else:
        enriched["aluguel_m2_real"] = enriched["aluguel_m2"]
        enriched["ganho_capital_m2_real"] = enriched["ganho_capital_m2"]
        enriched["retorno_total_m2_real"] = enriched["retorno_total_m2"]
        enriched["retorno_total_pct_real"] = enriched["retorno_total_pct"]

    enriched["retorno_total_pct"] = enriched["retorno_total_pct"].fillna(0.0)
    enriched["retorno_total_pct_real"] = enriched["retorno_total_pct_real"].fillna(0.0)
    enriched["indice_total_return"] = group["retorno_total_pct"].transform(lambda s: (1 + s.fillna(0.0)).cumprod())
    enriched["indice_total_return_real"] = group["retorno_total_pct_real"].transform(lambda s: (1 + s.fillna(0.0)).cumprod())

    # Backward compatibility for existing screens.
    enriched["rent_gain_nominal"] = enriched["aluguel_m2"]
    enriched["rent_gain_real"] = enriched["aluguel_m2_real"]
    return enriched.sort_values(["city", "date"]).reset_index(drop=True)


def filter_period(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    return df[(df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))].copy()


def rebase_by_group(df: pd.DataFrame, group_col: str, value_col: str, new_col: str = "base_100") -> pd.DataFrame:
    rebased = df.copy()
    first_values = rebased.groupby(group_col)[value_col].transform("first")
    rebased[new_col] = (rebased[value_col] / first_values) * 100
    return rebased


def compute_growth(df: pd.DataFrame, group_col: str, nominal_col: str, real_col: str) -> pd.DataFrame:
    ordered = df.sort_values(["date"])
    summary = (
        ordered.groupby(group_col)
        .agg(
            first_nominal=(nominal_col, "first"),
            last_nominal=(nominal_col, "last"),
            first_real=(real_col, "first"),
            last_real=(real_col, "last"),
            last_date=("date", "last"),
        )
        .reset_index()
    )
    summary["nominal_growth_pct"] = (
        (summary["last_nominal"] / summary["first_nominal"]) - 1
    ) * 100
    summary["real_growth_pct"] = ((summary["last_real"] / summary["first_real"]) - 1) * 100
    return summary.sort_values("real_growth_pct", ascending=False)


def build_comparison_series() -> pd.DataFrame:
    composite_source = load_fipezap_composite_series()
    sale_composite = composite_source[["date", "sale_index"]].rename(columns={"sale_index": "value"})
    sale_composite["series_name"] = "FipeZap Venda Composto"
    rent_composite = composite_source[["date", "rent_index"]].rename(columns={"rent_index": "value"})
    rent_composite["series_name"] = "FipeZap Aluguel Composto"
    composite_source = add_total_return_columns(composite_source)
    rent_gain_composite = composite_source[["date", "aluguel_m2"]].rename(columns={"aluguel_m2": "value"})
    rent_gain_composite["series_name"] = "Aluguel Recebido Composto"
    total_return_composite = composite_source[["date", "indice_total_return"]].copy()
    total_return_composite["value"] = total_return_composite["indice_total_return"]
    total_return_composite["series_name"] = "Retorno Total Composto"
    yield_composite = composite_source[["date", "rental_yield"]].copy()
    yield_composite["value"] = yield_composite["rental_yield"] * 100
    yield_composite["series_name"] = "Yield de Aluguel Composto"

    igmi = load_igmi_series()
    igmi_brasil = igmi[igmi["city"] == "Brasil"][["date", "value"]].copy()
    igmi_brasil["series_name"] = "IGMI-R Brasil"

    macro = load_macro_series()
    selected_macro = macro[macro["indicator"].isin(["IVG-R", "MVG-R"])][["date", "indicator", "value"]].copy()
    selected_macro["series_name"] = selected_macro["indicator"]

    ipca = load_ipca_reference()[["date", "ipca_index"]].rename(columns={"ipca_index": "value"})
    ipca["series_name"] = "IPCA"

    frames = [
        sale_composite[["date", "series_name", "value"]],
        rent_composite[["date", "series_name", "value"]],
        rent_gain_composite[["date", "series_name", "value"]],
        total_return_composite[["date", "series_name", "value"]],
        yield_composite[["date", "series_name", "value"]],
        igmi_brasil[["date", "series_name", "value"]],
        selected_macro[["date", "series_name", "value"]],
        ipca[["date", "series_name", "value"]],
    ]
    return pd.concat(frames, ignore_index=True).sort_values(["series_name", "date"])


def load_city_series_with_real_values() -> pd.DataFrame:
    return add_total_return_columns(
        add_rent_gain_columns(
            merge_with_ipca(load_fipezap_city_series(), value_columns=["sale_price_m2", "rent_price_m2"])
        )
    )


def load_neighborhood_series_with_real_values() -> pd.DataFrame:
    return merge_with_ipca(load_neighborhood_series(), value_columns=["price_m2"])


def make_download_excel(df: pd.DataFrame, sheet_name: str = "dados") -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    return buffer.read()


@lru_cache(maxsize=1)
def load_dashboard_data() -> dict[str, pd.DataFrame]:
    city_series = load_city_series_with_real_values()
    neighborhood_series = load_neighborhood_series_with_real_values()
    composite_series = load_fipezap_composite_series()
    igmi_series = load_igmi_series()
    macro_series = load_macro_series()
    ipca_reference = load_ipca_reference()
    comparison_series = build_comparison_series()

    return {
        "city_series": city_series,
        "neighborhood_series": neighborhood_series,
        "composite_series": composite_series,
        "igmi_series": igmi_series,
        "macro_series": macro_series,
        "ipca_reference": ipca_reference,
        "comparison_series": comparison_series,
    }
