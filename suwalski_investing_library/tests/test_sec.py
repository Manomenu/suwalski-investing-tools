"""XBRL parsing: alias drift and restatements, without touching the network."""

import pytest
from suwalski_investing_library.marketdata.sec import history_from_facts


def _fact(tag: str, year: int, value: float, *, filed: str = "2026-01-01", form: str = "10-K") -> dict:
    return {tag: {"units": {"USD": [{"start": f"{year - 1}-01-01", "end": f"{year}-01-01", "val": value, "form": form, "filed": filed}]}}}


def _ifrs(*entries: dict) -> dict:
    """Same shape, but under the IFRS taxonomy an ADR files 20-F with."""
    return {"facts": {"ifrs-full": _facts(*entries)["facts"]["us-gaap"]}}


def _facts(*entries: dict) -> dict:
    merged: dict = {}
    for entry in entries:
        for tag, payload in entry.items():
            merged.setdefault(tag, {"units": {"USD": []}})["units"]["USD"].extend(payload["units"]["USD"])
    return {"facts": {"us-gaap": merged}}


def _company(years: range, revenue_tag: str = "Revenues") -> dict:
    entries = []
    for year in years:
        entries.append(_fact(revenue_tag, year, 100.0 * year))
        entries.append(_fact("NetCashProvidedByUsedInOperatingActivities", year, 30.0 * year))
        entries.append(_fact("PaymentsToAcquirePropertyPlantAndEquipment", year, -10.0 * year))
    return _facts(*entries)


def test_free_cash_flow_is_operating_less_capex():
    history = history_from_facts(_company(range(2020, 2023)))

    assert history[-1].fcf == pytest.approx(30.0 * 2022 - 10.0 * 2022)
    assert history[-1].fcf_margin == pytest.approx((30.0 - 10.0) / 100.0)


def test_growth_compares_consecutive_reported_years():
    history = history_from_facts(_company(range(2020, 2023)))

    assert history[0].revenue_growth is None
    assert history[1].revenue_growth == pytest.approx(2021 / 2020 - 1)


def test_only_the_requested_number_of_years_comes_back():
    assert len(history_from_facts(_company(range(2010, 2027)), years=10)) == 10


def test_an_earlier_alias_keeps_a_year_a_later_alias_also_reports():
    facts = _facts(
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", 2025, 500.0),
        _fact("Revenues", 2025, 999.0),  # legacy tag, same year
        _fact("NetCashProvidedByUsedInOperatingActivities", 2025, 100.0),
        _fact("PaymentsToAcquirePropertyPlantAndEquipment", 2025, -20.0),
    )

    assert history_from_facts(facts)[0].revenue == pytest.approx(500.0)


def test_a_restated_year_takes_the_more_recently_filed_figure():
    facts = _facts(
        _fact("Revenues", 2025, 400.0, filed="2025-03-01"),
        _fact("Revenues", 2025, 420.0, filed="2026-03-01"),
        _fact("NetCashProvidedByUsedInOperatingActivities", 2025, 100.0),
        _fact("PaymentsToAcquirePropertyPlantAndEquipment", 2025, -20.0),
    )

    assert history_from_facts(facts)[0].revenue == pytest.approx(420.0)


def test_quarterly_and_non_annual_filings_are_ignored():
    facts = _facts(
        _fact("Revenues", 2025, 400.0, form="10-Q"),
        _fact("NetCashProvidedByUsedInOperatingActivities", 2025, 100.0),
        _fact("PaymentsToAcquirePropertyPlantAndEquipment", 2025, -20.0),
    )

    assert history_from_facts(facts) == []


def test_a_document_without_revenue_yields_no_history():
    assert history_from_facts({"facts": {"us-gaap": {}}}) == []


def test_the_alias_with_the_widest_coverage_supplies_the_series():
    # GRAB in the wild: one year tagged RevenueFromContractsWithCustomers at 0.05B, while
    # Revenue carries the real 1.43B for that same year plus three more years.
    facts = _ifrs(
        _fact("RevenueFromContractsWithCustomers", 2022, 0.05e9),
        *[_fact("Revenue", year, value) for year, value in ((2022, 1.43e9), (2023, 2.36e9), (2024, 2.80e9))],
        *[_fact("CashFlowsFromUsedInOperatingActivities", year, 0.1e9) for year in (2022, 2023, 2024)],
        *[_fact("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", year, -0.05e9) for year in (2022, 2023, 2024)],
    )

    history = history_from_facts(facts)

    assert [point.revenue for point in history] == pytest.approx([1.43e9, 2.36e9, 2.80e9])


def test_a_narrower_alias_still_fills_years_the_widest_one_is_missing():
    facts = _facts(
        *[_fact("Revenues", year, 100.0 * year) for year in (2023, 2024, 2025)],
        _fact("SalesRevenueNet", 2022, 100.0 * 2022),  # older tag, only year the other lacks
        *[_fact("NetCashProvidedByUsedInOperatingActivities", year, 30.0 * year) for year in range(2022, 2026)],
        *[_fact("PaymentsToAcquirePropertyPlantAndEquipment", year, -10.0 * year) for year in range(2022, 2026)],
    )

    assert [point.year for point in history_from_facts(facts)] == [2022, 2023, 2024, 2025]


def test_an_ifrs_filer_reads_the_same_as_a_us_gaap_one():
    entries = []
    for year in (2023, 2024, 2025):
        entries.append(_fact("Revenue", year, 100.0 * year))
        entries.append(_fact("CashFlowsFromUsedInOperatingActivities", year, 30.0 * year))
        entries.append(_fact("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", year, -10.0 * year))

    history = history_from_facts(_ifrs(*entries))

    assert [point.year for point in history] == [2023, 2024, 2025]
    assert history[-1].fcf_margin == pytest.approx(0.2)


def test_a_filer_reporting_in_euro_is_read_not_skipped():
    # ASML files in EUR; reading only the USD bucket returns nothing for it.
    facts = _facts(*[_fact("Revenues", year, 100.0 * year) for year in (2024, 2025)])
    for tag, value in (("NetCashProvidedByUsedInOperatingActivities", 30.0), ("PaymentsToAcquirePropertyPlantAndEquipment", -10.0)):
        for year in (2024, 2025):
            facts["facts"]["us-gaap"].setdefault(tag, {"units": {}})["units"].setdefault("EUR", []).append(
                {"start": f"{year - 1}-01-01", "end": f"{year}-01-01", "val": value * year, "form": "20-F", "filed": "2026-01-01"}
            )
    for tag in ("Revenues",):
        facts["facts"]["us-gaap"][tag]["units"]["EUR"] = facts["facts"]["us-gaap"][tag]["units"].pop("USD")

    history = history_from_facts(facts)

    assert [point.year for point in history] == [2024, 2025]


def test_cik_overrides_cover_adrs_sec_has_no_ticker_for(monkeypatch):
    from suwalski_investing_library.marketdata.sec import _cik_for

    monkeypatch.setenv("SEC_CIK_OVERRIDES", "SE:1703399, GRAB:1855612")

    assert _cik_for("se", cache_dir=None, ttl_seconds=0) == "0001703399"
    assert _cik_for("GRAB", cache_dir=None, ttl_seconds=0) == "0001855612"
