from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
import pickle
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
import requests

from dashboard.config import (
    CACHE_DIR,
    CITY_NAME_MAP,
    EXCLUDED_FIPEZAP_SHEETS,
    FIPEZAP_NEIGHBORHOODS_FILE,
    FIPEZAP_SEGMENTS,
    FIPEZAP_SERIES_FILE,
    IGMI_FILE,
    SGS_CODES,
)


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
XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


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
    ascii_name = unicodedata.normalize("NFKD", clean).encode("ascii", "ignore").decode("utf-8").lower()
    return CITY_NAME_MAP.get(ascii_name, clean)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({".": None, "": None}), errors="coerce")


def _read_shared_strings(workbook_zip: zipfile.ZipFile) -> list[str]:
    shared_strings = []
    if "xl/sharedStrings.xml" not in workbook_zip.namelist():
        return shared_strings

    root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
    for item in root.findall("main:si", XML_NS):
        text = "".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        shared_strings.append(text)
    return shared_strings


def _read_sheet_targets(workbook_zip: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    rel_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root}

    targets = {}
    for sheet in workbook_root.findall("main:sheets/main:sheet", XML_NS):
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_map[rel_id]
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        targets[sheet.attrib["name"]] = target
    return targets


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find("main:is", XML_NS)
        if inline is None:
            return None
        return "".join(node.text or "" for node in inline.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))

    value_node = cell.find("main:v", XML_NS)
    if value_node is None or value_node.text is None:
        return None

    if cell_type == "s":
        return shared_strings[int(value_node.text)]
    return value_node.text


def _excel_serial_to_datetime(value) -> pd.Timestamp:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(numeric):
        return pd.Timestamp("1899-12-30") + pd.to_timedelta(float(numeric), unit="D")
    return pd.to_datetime(value, errors="coerce")


def _parse_fipezap_sheet(
    workbook_zip: zipfile.ZipFile,
    sheet_target: str,
    label: str,
    segment: str,
    shared_strings: list[str],
) -> pd.DataFrame:
    refs = FIPEZAP_SEGMENTS[segment]["refs"]
    required_letters = set(refs.values())
    root = ET.fromstring(workbook_zip.read(sheet_target))
    records = []

    for row in root.findall(".//main:sheetData/main:row", XML_NS):
        row_number = int(row.attrib.get("r", "0"))
        if row_number < 5:
            continue

        letter_map = {}
        for cell in row.findall("main:c", XML_NS):
            ref = cell.attrib.get("r", "")
            letter = "".join(character for character in ref if character.isalpha())
            if letter in required_letters:
                letter_map[letter] = _cell_text(cell, shared_strings)

        if refs["date"] not in letter_map:
            continue

        record = {}
        for field, letter in refs.items():
            record[field] = letter_map.get(letter)
        records.append(record)

    if not records:
        return pd.DataFrame(columns=FIPEZAP_COLUMNS + ["city", "source", "segment"])

    df = pd.DataFrame(records)
    df["date"] = df["date"].map(_excel_serial_to_datetime)
    for column in FIPEZAP_COLUMNS[1:]:
        df[column] = _coerce_numeric(df[column])

    numeric_columns = FIPEZAP_COLUMNS[1:]
    df = df[df["date"].notna()].copy()
    df = df[df[numeric_columns].notna().any(axis=1)].copy()
    df["city"] = standardize_city_name(label)
    df["source"] = "FipeZap"
    df["segment"] = segment
    return df.sort_values("date").reset_index(drop=True)


def _load_fipezap_workbook_segment(segment: str, composite_only: bool = False) -> pd.DataFrame:
    with zipfile.ZipFile(FIPEZAP_SERIES_FILE) as workbook_zip:
        shared_strings = _read_shared_strings(workbook_zip)
        sheet_targets = _read_sheet_targets(workbook_zip)

        if composite_only:
            selected_sheets = ["Índice FipeZAP"]
        else:
            selected_sheets = [name for name in sheet_targets if name not in EXCLUDED_FIPEZAP_SHEETS]

        frames = []
        for sheet_name in selected_sheets:
            frames.append(
                _parse_fipezap_sheet(
                    workbook_zip=workbook_zip,
                    sheet_target=sheet_targets[sheet_name],
                    label=sheet_name,
                    segment=segment,
                    shared_strings=shared_strings,
                )
            )

    if not frames:
        return pd.DataFrame(columns=FIPEZAP_COLUMNS + ["city", "source", "segment"])
    return pd.concat(frames, ignore_index=True)


@lru_cache(maxsize=4)
def load_fipezap_city_series(segment: str = "residential") -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        return _load_fipezap_workbook_segment(segment=segment, composite_only=False)

    return _load_disk_cache(
        f"fipezap_city_series_{segment}",
        builder=builder,
        source_paths=[FIPEZAP_SERIES_FILE],
    )


@lru_cache(maxsize=4)
def load_city_metadata(segment: str = "residential") -> dict:
    def builder() -> dict:
        df = load_fipezap_city_series(segment)
        if df.empty:
            return {"cities": [], "min_date": pd.NaT, "max_date": pd.NaT}
        return {
            "cities": sorted(df["city"].dropna().unique().tolist()),
            "min_date": df["date"].min(),
            "max_date": df["date"].max(),
        }

    return _load_disk_cache(
        f"city_metadata_{segment}",
        builder=builder,
        source_paths=[FIPEZAP_SERIES_FILE],
    )


@lru_cache(maxsize=4)
def load_fipezap_composite_series(segment: str = "residential") -> pd.DataFrame:
    def builder() -> pd.DataFrame:
        return _load_fipezap_workbook_segment(segment=segment, composite_only=True)

    return _load_disk_cache(
        f"fipezap_composite_series_{segment}",
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

        value_columns = [column for column in df.columns if column not in {"raw_month", "date", "var% 12 meses"}]
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
        melted["series_name"] = melted["city"].apply(lambda city: "IGMI-R Brasil" if city == "Brasil" else f"IGMI-R {city}")
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
        return pd.DataFrame(columns=["date", "ipca_monthly_pct", "ipca_index", "deflator_to_latest", "ipca_cumulative_pct"])

    ipca = ipca.sort_values("date").reset_index(drop=True)
    ipca["ipca_monthly_pct"] = ipca["value"]
    ipca["ipca_index"] = (1 + ipca["ipca_monthly_pct"] / 100).cumprod() * 100
    latest_index = ipca["ipca_index"].iloc[-1]
    ipca["deflator_to_latest"] = latest_index / ipca["ipca_index"]
    ipca["ipca_cumulative_pct"] = (ipca["ipca_index"] / ipca["ipca_index"].iloc[0] - 1) * 100
    return ipca[["date", "ipca_monthly_pct", "ipca_index", "deflator_to_latest", "ipca_cumulative_pct"]]


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
    sort_columns = ["city", "date"] if "city" in df.columns else ["date"]
    enriched = df.sort_values(sort_columns).copy()
    group_key = "city" if "city" in enriched.columns else None
    group = enriched.groupby(group_key, group_keys=False) if group_key else None

    prev_sale = group["sale_price_m2"].shift(1) if group is not None else enriched["sale_price_m2"].shift(1)
    enriched["aluguel_m2"] = enriched["sale_price_m2"] * enriched["rental_yield"]
    enriched["ganho_capital_m2"] = (enriched["sale_price_m2"] - prev_sale).fillna(0.0)
    capital_return_pct = ((enriched["sale_price_m2"] / prev_sale) - 1).replace([pd.NA, pd.NaT], 0.0).fillna(0.0)
    enriched["retorno_total_m2"] = enriched["ganho_capital_m2"] + enriched["aluguel_m2"]
    enriched["retorno_total_pct"] = capital_return_pct + enriched["rental_yield"].fillna(0.0)

    prev_sale_real = None
    if "sale_price_m2_real" in enriched.columns:
        prev_sale_real = group["sale_price_m2_real"].shift(1) if group is not None else enriched["sale_price_m2_real"].shift(1)

    if prev_sale_real is not None:
        enriched["aluguel_m2_real"] = enriched["sale_price_m2_real"] * enriched["rental_yield"]
        enriched["ganho_capital_m2_real"] = (enriched["sale_price_m2_real"] - prev_sale_real).fillna(0.0)
        capital_return_pct_real = ((enriched["sale_price_m2_real"] / prev_sale_real) - 1).replace([pd.NA, pd.NaT], 0.0).fillna(0.0)
        enriched["retorno_total_m2_real"] = enriched["ganho_capital_m2_real"] + enriched["aluguel_m2_real"]
        enriched["retorno_total_pct_real"] = capital_return_pct_real + enriched["rental_yield"].fillna(0.0)
    else:
        enriched["aluguel_m2_real"] = enriched["aluguel_m2"]
        enriched["ganho_capital_m2_real"] = enriched["ganho_capital_m2"]
        enriched["retorno_total_m2_real"] = enriched["retorno_total_m2"]
        enriched["retorno_total_pct_real"] = enriched["retorno_total_pct"]

    enriched["retorno_total_pct"] = enriched["retorno_total_pct"].fillna(0.0)
    enriched["retorno_total_pct_real"] = enriched["retorno_total_pct_real"].fillna(0.0)

    if group is not None:
        enriched["indice_total_return"] = group["retorno_total_pct"].transform(lambda s: (1 + s.fillna(0.0)).cumprod())
        enriched["indice_total_return_real"] = group["retorno_total_pct_real"].transform(lambda s: (1 + s.fillna(0.0)).cumprod())
    else:
        enriched["indice_total_return"] = (1 + enriched["retorno_total_pct"].fillna(0.0)).cumprod()
        enriched["indice_total_return_real"] = (1 + enriched["retorno_total_pct_real"].fillna(0.0)).cumprod()

    enriched["rent_gain_nominal"] = enriched["aluguel_m2"]
    enriched["rent_gain_real"] = enriched["aluguel_m2_real"]
    return enriched.sort_values(sort_columns).reset_index(drop=True)


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
    summary["nominal_growth_pct"] = ((summary["last_nominal"] / summary["first_nominal"]) - 1) * 100
    summary["real_growth_pct"] = ((summary["last_real"] / summary["first_real"]) - 1) * 100
    return summary.sort_values("real_growth_pct", ascending=False)


def _comparison_series_names(segment: str) -> dict[str, str]:
    if segment == "commercial":
        return {
            "sale": "FipeZap Comercial Venda Composto",
            "rent": "FipeZap Comercial Aluguel Composto",
            "received": "Aluguel Comercial Recebido Composto",
            "total_return": "Retorno Total Comercial Composto",
            "yield": "Yield de Aluguel Comercial Composto",
        }
    return {
        "sale": "FipeZap Venda Composto",
        "rent": "FipeZap Aluguel Composto",
        "received": "Aluguel Recebido Composto",
        "total_return": "Retorno Total Composto",
        "yield": "Yield de Aluguel Composto",
    }


def build_comparison_series(segment: str = "residential") -> pd.DataFrame:
    names = _comparison_series_names(segment)
    composite_source = load_fipezap_composite_series(segment)

    sale_composite = composite_source[["date", "sale_index"]].rename(columns={"sale_index": "value"})
    sale_composite["series_name"] = names["sale"]

    rent_composite = composite_source[["date", "rent_index"]].rename(columns={"rent_index": "value"})
    rent_composite["series_name"] = names["rent"]

    composite_source = add_total_return_columns(composite_source)
    rent_gain_composite = composite_source[["date", "aluguel_m2"]].rename(columns={"aluguel_m2": "value"})
    rent_gain_composite["series_name"] = names["received"]

    total_return_composite = composite_source[["date", "indice_total_return"]].copy()
    total_return_composite["value"] = total_return_composite["indice_total_return"]
    total_return_composite["series_name"] = names["total_return"]

    yield_composite = composite_source[["date", "rental_yield"]].copy()
    yield_composite["value"] = yield_composite["rental_yield"] * 100
    yield_composite["series_name"] = names["yield"]

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


def load_city_series_with_real_values(segment: str = "residential") -> pd.DataFrame:
    return add_total_return_columns(
        add_rent_gain_columns(
            merge_with_ipca(load_fipezap_city_series(segment), value_columns=["sale_price_m2", "rent_price_m2"])
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


@lru_cache(maxsize=4)
def load_dashboard_data(segment: str = "residential") -> dict[str, pd.DataFrame]:
    city_series = load_city_series_with_real_values(segment)
    composite_series = load_fipezap_composite_series(segment)
    igmi_series = load_igmi_series()
    macro_series = load_macro_series()
    ipca_reference = load_ipca_reference()
    comparison_series = build_comparison_series(segment)

    payload = {
        "city_series": city_series,
        "composite_series": composite_series,
        "igmi_series": igmi_series,
        "macro_series": macro_series,
        "ipca_reference": ipca_reference,
        "comparison_series": comparison_series,
    }

    if segment == "residential":
        payload["neighborhood_series"] = load_neighborhood_series_with_real_values()
    return payload
