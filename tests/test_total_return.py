"""Unit tests for the Imóvel + Aluguel total-return series calculations.

Tests cover:
  1. Cumulative income-return (cumprod) calculation.
  2. Real-return deflation formula  ( nominal / (ipca[t] / ipca[t0]) ).
  3. Forward-fill behaviour when rental_yield has null values.

These tests are standalone and do NOT import Streamlit or data-loading
functions, so they run fast without any Excel files or network access.
"""

from __future__ import annotations

import pandas as pd
import pytest


# ── Helper functions mirroring the in-app logic ───────────────────────────────

def _build_income_return(yield_series: pd.Series) -> pd.Series:
    """Cumulative income return from a monthly yield fraction series.

    - Forward-fills null values from the last known yield.
    - Falls back to 0.0 if the first values are null (no prior data).
    - Returns a cumulative product starting from (1 + yield_month_0).
    """
    filled = yield_series.ffill().fillna(0.0)
    return (1 + filled).cumprod()


def _deflate_by_ipca(nominal: pd.Series, ipca: pd.Series) -> pd.Series:
    """Convert a nominal index series to real terms.

    real[t] = nominal[t] / (ipca[t] / ipca[t0])

    Both series must share the same index / alignment.
    """
    ipca_base = ipca.iloc[0]
    if ipca_base == 0 or pd.isna(ipca_base):
        return nominal.copy()
    ipca_factor = ipca / ipca_base
    return nominal / ipca_factor


def _imovel_aluguel_nominal(
    price: pd.Series,
    yield_monthly: pd.Series,
) -> pd.Series:
    """Combined nominal total-return index (Base 100 at t0).

    Mirrors the formula described in the spec:
        price_return[t]  = price[t] / price[t0]
        income_return[t] = cumprod(1 + yield[t])   (yield already monthly)
        total[t]         = 100 × price_return[t] × income_return[t]

    Note: `yield_monthly` is the MONTHLY yield fraction (e.g. 0.005 = 0.5 % /
    month ≈ 6 % / year) — NOT the annualised figure.  No ÷12 is applied here
    because the raw column `rental_yield` in this codebase already stores the
    monthly value.
    """
    p0 = price.iloc[0]
    if p0 == 0 or pd.isna(p0):
        return pd.Series([100.0] * len(price), index=price.index)
    price_return = price / p0
    income_return = _build_income_return(yield_monthly)
    return 100.0 * price_return * income_return


# ── Tests: cumulative income return ──────────────────────────────────────────

class TestIncomeReturn:
    def test_constant_yield_compounds_correctly(self) -> None:
        """Constant monthly yield must compound to (1+y)^n."""
        y = 0.005  # 0.5 % / month
        yields = pd.Series([y, y, y])
        result = _build_income_return(yields)
        expected = pd.Series([(1 + y) ** n for n in range(1, 4)])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False)

    def test_zero_yield_stays_at_one(self) -> None:
        """Zero yield every month → income_return == 1 throughout."""
        yields = pd.Series([0.0, 0.0, 0.0])
        result = _build_income_return(yields)
        assert (result == 1.0).all(), f"Expected all 1.0, got {result.tolist()}"

    def test_varying_yields_accumulate_correctly(self) -> None:
        """Different yields each month compound in sequence."""
        yields = pd.Series([0.004, 0.006, 0.005])
        result = _build_income_return(yields)
        expected = pd.Series([
            1.004,
            1.004 * 1.006,
            1.004 * 1.006 * 1.005,
        ])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_ffill_single_null_in_middle(self) -> None:
        """A null in the middle is filled from the preceding value."""
        yields = pd.Series([0.004, None, 0.006])
        result = _build_income_return(yields)
        # month 1: 0.004, month 2: ffill → 0.004, month 3: 0.006
        expected = pd.Series([1.004, 1.004 * 1.004, 1.004 * 1.004 * 1.006])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_ffill_trailing_nulls(self) -> None:
        """Trailing nulls use the last known non-null yield."""
        yields = pd.Series([0.003, None, None])
        result = _build_income_return(yields)
        # all three months use 0.003
        expected = pd.Series([1.003, 1.003 ** 2, 1.003 ** 3])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_all_null_yields_defaults_to_one(self) -> None:
        """When every value is null, income_return is 1 (no rental income)."""
        yields = pd.Series([None, None, None], dtype=float)
        result = _build_income_return(yields)
        assert (result == 1.0).all(), f"Expected all 1.0, got {result.tolist()}"

    def test_partial_null_ffill_complex(self) -> None:
        """Forward-fill propagates correctly across a mixed sequence."""
        yields = pd.Series([0.003, None, 0.006, None, None])
        result = _build_income_return(yields)
        # effective yields: [0.003, 0.003, 0.006, 0.006, 0.006]
        effective = [0.003, 0.003, 0.006, 0.006, 0.006]
        expected = pd.Series(effective).add(1).cumprod()
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected.reset_index(drop=True), atol=1e-10)


# ── Tests: IPCA deflation ─────────────────────────────────────────────────────

class TestIpcaDeflation:
    def test_rising_ipca_reduces_real_value(self) -> None:
        """Higher IPCA at later dates should lower the real series."""
        nominal = pd.Series([100.0, 105.0, 110.0])
        ipca = pd.Series([100.0, 102.0, 105.0])
        real = _deflate_by_ipca(nominal, ipca)
        expected = pd.Series([100.0, 105.0 / 1.02, 110.0 / 1.05])
        pd.testing.assert_series_equal(real.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_constant_ipca_real_equals_nominal(self) -> None:
        """Flat IPCA (no inflation) → real series equals nominal."""
        nominal = pd.Series([100.0, 110.0, 120.0])
        ipca = pd.Series([100.0, 100.0, 100.0])
        real = _deflate_by_ipca(nominal, ipca)
        pd.testing.assert_series_equal(real.reset_index(drop=True), nominal.reset_index(drop=True), check_names=False)

    def test_first_value_is_always_100(self) -> None:
        """At t0 the deflated value equals the nominal value (ipca ratio = 1)."""
        nominal = pd.Series([250.0, 260.0, 270.0])
        ipca = pd.Series([110.0, 112.0, 115.0])
        real = _deflate_by_ipca(nominal, ipca)
        assert real.iloc[0] == pytest.approx(250.0)

    def test_deflation_formula_symmetry(self) -> None:
        """If nominal grows exactly at IPCA rate, real stays flat."""
        # nominal doubles over 2 periods, IPCA also doubles → real constant
        nominal = pd.Series([100.0, 150.0, 200.0])
        ipca = pd.Series([100.0, 150.0, 200.0])
        real = _deflate_by_ipca(nominal, ipca)
        expected = pd.Series([100.0, 100.0, 100.0])
        pd.testing.assert_series_equal(real.reset_index(drop=True), expected, check_names=False, atol=1e-10)


# ── Tests: combined nominal total-return index ────────────────────────────────

class TestImovelAluguelNominal:
    def test_no_price_change_no_yield_returns_100(self) -> None:
        """Flat price and zero yield → index stays at 100."""
        price = pd.Series([1000.0, 1000.0, 1000.0])
        yields = pd.Series([0.0, 0.0, 0.0])
        result = _imovel_aluguel_nominal(price, yields)
        expected = pd.Series([100.0, 100.0, 100.0])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_starts_at_100_times_first_income(self) -> None:
        """First value is 100 × (1 + first_month_yield): income compounds immediately.

        price_return[0] = price[0]/price[0] = 1.0
        income_return[0] = (1 + yield[0])^1
        → result[0] = 100 × 1.0 × (1 + yield[0])
        The app rebases this to Base 100 via rebase_by_group, so the on-screen
        chart always starts at 100.  The raw index reflects the first period return.
        """
        y0 = 0.004
        price = pd.Series([5000.0, 5100.0, 5200.0])
        yields = pd.Series([y0, y0, y0])
        result = _imovel_aluguel_nominal(price, yields)
        assert result.iloc[0] == pytest.approx(100.0 * (1 + y0))

    def test_price_only_gain_no_yield(self) -> None:
        """With zero yield, index tracks price return × 100."""
        price = pd.Series([1000.0, 1100.0, 1210.0])  # +10% each month
        yields = pd.Series([0.0, 0.0, 0.0])
        result = _imovel_aluguel_nominal(price, yields)
        expected = pd.Series([100.0, 110.0, 121.0])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)

    def test_combined_exceeds_price_only(self) -> None:
        """With positive yield, combined index always ≥ price-only index."""
        price = pd.Series([1000.0, 1050.0, 1100.0])
        yields = pd.Series([0.005, 0.005, 0.005])
        combined = _imovel_aluguel_nominal(price, yields)
        price_only = 100.0 * price / price.iloc[0]
        assert (combined.values >= price_only.values - 1e-9).all()

    def test_yield_null_ffill_in_combined(self) -> None:
        """Null yield months in combined return are forward-filled gracefully."""
        price = pd.Series([1000.0, 1000.0, 1000.0])
        yields = pd.Series([0.005, None, None])
        result = _imovel_aluguel_nominal(price, yields)
        # income_return with ffill: all 3 months use 0.005
        expected = pd.Series([
            100.0 * 1.005,
            100.0 * 1.005 ** 2,
            100.0 * 1.005 ** 3,
        ])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False, atol=1e-10)
