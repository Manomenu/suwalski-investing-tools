import json

from suwalski_investing_cli.main import main

# The reference reverse-DCF screen for NVDA, as typed into the CLI. Flag/value pairs are
# kept on one line each, the way you would type them at a prompt.
# fmt: off
REFERENCE = [
    "--price", "224.03",
    "--shares", "24.40",
    "--fcf", "127.01",
    "--fcf-margin", "42%",
    "--optimized-margin", "35%",
    "--growth", "1-3:55%",
    "--discount", "10%",
    "--terminal", "3%",
]
# fmt: on


def test_prints_the_projection_and_the_solved_growth(capsys):
    assert main(REFERENCE) == 0

    output = capsys.readouterr().out
    assert "Intrinsic value / share" in output
    assert "GROWTH THE PRICE REQUIRES" in output
    assert "years 4-10    4.76%   <- solved" in output


def test_json_carries_the_full_result(capsys):
    assert main([*REFERENCE, "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["solved_years"] == [4, 5, 6, 7, 8, 9, 10]
    assert len(payload["projection"]["years"]) == 10


def test_missing_revenue_inputs_exit_2(capsys):
    code = main(["--price", "10", "--shares", "10", "--optimized-margin", "35%"])

    assert code == 2
    assert "--fcf together with --fcf-margin" in capsys.readouterr().err


def test_unsolvable_price_exits_1(capsys):
    code = main([*REFERENCE[2:], "--price", "1"])

    assert code == 1
    assert "cannot solve" in capsys.readouterr().err


def test_invalid_model_inputs_exit_2_with_field_detail(capsys):
    code = main([*REFERENCE, "--terminal", "20%"])

    assert code == 2
    assert "terminal_growth" in capsys.readouterr().err
