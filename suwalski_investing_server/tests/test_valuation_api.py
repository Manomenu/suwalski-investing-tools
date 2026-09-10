import pytest
from fastapi.testclient import TestClient
from suwalski_investing_server.app import app

client = TestClient(app)

BASE = {
    "revenue": 100.0,
    "optimized_fcf_margin": 0.10,
    "shares_outstanding": 1.0,
    "discount_rate": 0.10,
    "terminal_growth": 0.02,
    "projection_years": 10,
    "growth_segments": [{"start_year": 1, "end_year": 3, "growth": 0.40}],
}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_reverse_dcf_solves_the_open_years():
    response = client.post("/valuation/reverse-dcf", json={**BASE, "current_price": 400.0})

    assert response.status_code == 200
    body = response.json()
    assert body["solved_years"] == [4, 5, 6, 7, 8, 9, 10]
    assert len(body["projection"]["years"]) == 10
    assert body["projection"]["intrinsic_value_per_share"] == pytest.approx(400.0, abs=1e-6)
    assert body["projection"]["years"][0]["growth"] == pytest.approx(0.40)
    assert body["projection"]["years"][3]["growth"] == pytest.approx(body["implied_growth"])


def test_bad_inputs_come_back_as_422():
    response = client.post("/valuation/reverse-dcf", json={**BASE, "current_price": 400.0, "terminal_growth": 0.20})

    assert response.status_code == 422
    assert "terminal_growth" in response.text


def test_unsolvable_price_comes_back_as_422_with_the_reason():
    response = client.post("/valuation/reverse-dcf", json={**BASE, "current_price": 1.0})

    assert response.status_code == 422
    assert "above the" in response.json()["detail"]
