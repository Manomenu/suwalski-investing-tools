import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from suwinvtools_server.signals import store
from suwinvtools_server.signals.checks import ALL_CHECKS
from suwinvtools_server.signals.model import Evidence, Outcome, Reading, Verdict


@pytest.fixture
def seeded(client: TestClient, pool: ConnectionPool) -> TestClient:
    with pool.connection() as conn:
        conn.execute("TRUNCATE signal_readings, signal_outcomes, signal_runs")
        for period, value in (("2026Q1", 30.0), ("2026Q2", 25.0)):
            store.save_reading(conn, Reading(check_id="A1", subject="AWS", period=period, value=value))
        store.save_outcome(conn, Outcome("A1", "AWS", "2026Q2", Verdict.NEUTRAL, "AWS: 25% r/r"))
        evidence = (Evidence(url="https://sec.gov/x", title="10-Q", quote="AWS segment sales increased 25%"),)
        store.save_outcome(conn, Outcome("A1", "3 chmury", "2026Q2", Verdict.RED, "Hamują AWS, Azure.", evidence))
        store.save_outcome(conn, Outcome("A2", "OpenAI", "2026Q2", Verdict.GREEN, "OpenAI +20% kw/kw."))
    return client


def test_the_board_lists_every_check_with_its_headline(seeded: TestClient) -> None:
    body = seeded.get("/signals").json()

    assert [item["check"]["id"] for item in body["items"]] == [check.meta.id for check in ALL_CHECKS]
    a1 = body["items"][0]
    assert a1["headline"]["verdict"] == "red"
    assert a1["headline"]["evidence"][0]["quote"] == "AWS segment sales increased 25%"


def test_the_feed_has_red_and_green_newest_first(seeded: TestClient) -> None:
    feed = seeded.get("/signals/feed").json()

    assert {item["verdict"] for item in feed} == {"red", "green"}


def test_a_check_page_has_readings_and_outcomes(seeded: TestClient) -> None:
    body = seeded.get("/signals/a1").json()

    assert body["check"]["id"] == "A1"
    assert [reading["value"] for reading in body["readings"]] == [30.0, 25.0]
    assert len(body["outcomes"]) == 2


def test_an_unknown_check_is_404(seeded: TestClient) -> None:
    assert seeded.get("/signals/Z9").status_code == 404
