"""The valuation engine must stay installable and importable without the `tickers` extra.

`marketdata/` lives in this package for convenience, but nothing in `valuation/` or
`contracts/` may reach for it — otherwise every consumer of the engine inherits pandas,
numpy and an unofficial Yahoo scraper it never asked for.
"""

import subprocess
import sys
import textwrap


def test_importing_the_engine_pulls_in_none_of_the_ticker_dependencies() -> None:
    probe = textwrap.dedent(
        """
        import sys

        import suwinvtools_library.valuation.reverse  # noqa: F401
        from suwinvtools_library.contracts import market, valuation  # noqa: F401

        print(",".join(sorted(name for name in ("pandas", "numpy", "yfinance") if name in sys.modules)))
        """
    )

    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)  # noqa: S603 — our own interpreter, our own probe

    assert result.stdout.strip() == "", f"the engine imported {result.stdout.strip()}"
