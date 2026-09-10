"""`rdcf` — run the reverse DCF straight from a terminal, no server needed.

    rdcf --ticker NVDA --optimized-margin 35% --growth 1-3:55%
    rdcf --price 224.03 --shares 24.40 --fcf 127.01 --fcf-margin 42% \
        --optimized-margin 35% --growth 1-3:55% --discount 10% --terminal 3%

Exit codes: 1 the price cannot be solved, 2 bad inputs, 3 the market data lookup failed.
"""

import argparse
import json
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.contracts.valuation import ReverseDcfRequest
from suwalski_investing_library.marketdata.errors import MarketDataError
from suwalski_investing_library.marketdata.provider import DEFAULT_TTL_SECONDS, get_snapshot
from suwalski_investing_library.valuation.errors import ValuationError
from suwalski_investing_library.valuation.reverse import solve_implied_growth

from suwalski_investing_cli.parsing import parse_rate, parse_segment
from suwalski_investing_cli.render import render_projection, render_reverse, render_snapshot, render_summary

_DESCRIPTION = """Reverse DCF with split growth.

A normal DCF asks "what is it worth?" and needs you to guess every year of growth. This
asks the opposite: at today's price, what growth is the market already paying for? You pin
the years you have a view on, and the tool solves the rest. The output is one number to
argue with — "years 4-10 must compound at 4.4%" — instead of a valuation you tuned until
you liked it."""

_EPILOG = """what the assumptions actually mean

  --discount is your hurdle rate. If you pay the intrinsic value this model prints and the
  cash flows land as projected, you earn roughly that rate a year. 10% is a common stand-in
  for long-run equity returns; use more for a business you consider risky or when you have
  better places for the money. Raising it lowers the value of every future dollar, so the
  same price starts implying more growth.

  --terminal is the assumption you should touch least. Everything after the last projected
  year is one perpetuity, and small changes there swing the value hard. Keep it at or below
  long-run inflation-plus-real-GDP (~3%); it must stay under --discount or the arithmetic
  diverges.

  --optimized-margin is where most of the disagreement lives. It says what the business
  looks like once it is done growing into itself. Today's margin (--fcf-margin, or whatever
  the ticker reports) is a fact; this one is a bet.

  --growth is the part you are supposed to be opinionated about, and only for the years you
  genuinely have a view on. Leave the rest to the solver — that is the whole point.

examples

  rdcf --ticker NVDA --optimized-margin 35% --growth 1-3:55%
      price, shares, revenue, FCF and net debt come from Yahoo Finance; you supply the view

  rdcf --ticker MSFT --optimized-margin 30% --growth 1-5:12% --discount 12% --years 15
      a stricter hurdle over a longer horizon

  rdcf --price 224.03 --shares 24.40 --fcf 127.01 --fcf-margin 42% \\
       --optimized-margin 35% --growth 1-3:55% --discount 10% --terminal 3%
      no network at all — every number typed in by hand

exit codes
  0 solved   1 no growth in range justifies the price   2 bad inputs   3 market data lookup failed
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rdcf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_DESCRIPTION,
        epilog=_EPILOG,
    )

    market = parser.add_argument_group("what the market says (a --ticker fills all four in)")
    market.add_argument("--ticker", default=None, help="read the four values below off Yahoo Finance; explicit flags still win")
    market.add_argument("--price", type=float, default=None, help="what one share costs today — the number the solver has to justify")
    market.add_argument(
        "--shares",
        type=float,
        default=None,
        help="shares outstanding. Dilution and buybacks are not modelled, so use the count you expect to live with",
    )
    market.add_argument(
        "--net-debt",
        type=float,
        default=None,
        help="debt minus cash. Subtracted from the business value; negative (net cash) adds to it",
    )

    business = parser.add_argument_group("the business today")
    business.add_argument("--revenue", type=float, default=None, help="TTM revenue — the base every growth rate compounds from")
    business.add_argument("--fcf", type=float, default=None, help="TTM free cash flow; with --fcf-margin it stands in for --revenue")
    business.add_argument(
        "--fcf-margin",
        type=parse_rate,
        default=None,
        help="what share of revenue turned into free cash flow over the last year — a fact, not a forecast",
    )

    assumptions = parser.add_argument_group("your assumptions (nothing here can be fetched — see the notes below)")
    assumptions.add_argument(
        "--optimized-margin",
        type=parse_rate,
        required=True,
        help=(
            "the FCF margin you believe the business settles at. Revenue times this margin is the cash being discounted, "
            "so it is the single biggest lever here. Above today's margin means you expect operating leverage; below it "
            "means you read today's margin as a peak"
        ),
    )
    assumptions.add_argument(
        "--ramp-years",
        type=int,
        default=0,
        metavar="N",
        help="if that margin is not reached immediately, walk to it linearly over N years starting from --fcf-margin (default: from year 1)",
    )
    assumptions.add_argument(
        "--growth",
        type=parse_segment,
        action="append",
        default=[],
        metavar="YEARS:RATE",
        help=(
            "revenue growth you actually have a view on, per year range: 1-3:55%% or 5:10%% (repeatable). "
            "Every year you leave uncovered is what the tool solves for — that solved rate is the answer you came for"
        ),
    )
    assumptions.add_argument(
        "--discount",
        type=parse_rate,
        default=0.10,
        help=(
            "the annual return you demand from this position (default 10%%). It is your yardstick, not a market fact: "
            "at 10%% a dollar the company earns in ten years is worth 39 cents to you now. Demand more and the same price "
            "implies more growth"
        ),
    )
    assumptions.add_argument(
        "--terminal",
        type=parse_rate,
        default=0.025,
        help=(
            "how fast cash grows forever after the last projected year (default 2.5%%). Long-run nominal GDP, roughly 3%%, "
            "is the honest ceiling — above it the company eventually outgrows the economy. Must stay below --discount"
        ),
    )
    assumptions.add_argument(
        "--years",
        type=int,
        default=10,
        help="how far out you are willing to forecast before the terminal value takes over (default 10)",
    )

    solver = parser.add_argument_group("solver and output")
    solver.add_argument(
        "--min-growth",
        type=parse_rate,
        default=-0.9,
        help="floor of the search range (default -90%%). A price needing less than this is reported, not clamped",
    )
    solver.add_argument(
        "--max-growth",
        type=parse_rate,
        default=3.0,
        help="ceiling of the search range (default 300%%). A price needing more than this is reported, not clamped",
    )
    solver.add_argument("--refresh", action="store_true", help="ignore the cached snapshot for --ticker and refetch")
    solver.add_argument(
        "--cache-ttl",
        type=int,
        default=DEFAULT_TTL_SECONDS,
        metavar="SECONDS",
        help=f"how long a fetched snapshot is reused (default {DEFAULT_TTL_SECONDS})",
    )
    solver.add_argument("--json", action="store_true", help="print the raw result as JSON instead of the tables")
    return parser


def _request(args: argparse.Namespace) -> tuple[ReverseDcfRequest, TickerSnapshot | None]:
    """Explicit flags always win; --ticker fills in whatever is left."""
    snapshot = get_snapshot(args.ticker, ttl_seconds=args.cache_ttl, refresh=args.refresh) if args.ticker else None

    price = _pick(args.price, snapshot and snapshot.price)
    shares = _pick(args.shares, snapshot and snapshot.shares_outstanding)
    if price is None or shares is None:
        raise ValueError("give --price and --shares, or --ticker to read them off Yahoo Finance")

    # A negative TTM margin is a fact, not a usable input — the model needs a positive one,
    # and only when a ramp is requested, so drop it rather than fail on it.
    fcf_margin = _pick(args.fcf_margin, snapshot and snapshot.fcf_margin)
    if fcf_margin is not None and fcf_margin <= 0:
        fcf_margin = None

    revenue = args.revenue
    if revenue is None:
        if args.fcf is not None and fcf_margin is not None:
            revenue = args.fcf / fcf_margin
        elif snapshot is not None:
            revenue = snapshot.revenue_ttm
        else:
            raise ValueError("give --revenue, --fcf together with --fcf-margin, or --ticker")

    request = ReverseDcfRequest(
        revenue=revenue,
        optimized_fcf_margin=args.optimized_margin,
        current_fcf_margin=fcf_margin,
        margin_ramp_years=args.ramp_years,
        shares_outstanding=shares,
        net_debt=_pick(args.net_debt, snapshot and snapshot.net_debt) or 0.0,
        discount_rate=args.discount,
        terminal_growth=args.terminal,
        projection_years=args.years,
        growth_segments=args.growth,
        current_price=price,
        growth_lower_bound=args.min_growth,
        growth_upper_bound=args.max_growth,
    )
    return request, snapshot


def _pick(explicit: float | None, fetched: float | None) -> float | None:
    return explicit if explicit is not None else fetched


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        request, snapshot = _request(args)
        result = solve_implied_growth(request)
    except MarketDataError as exc:
        print(f"market data: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:  # ValidationError is a ValueError; both mean "bad inputs"
        for line in _input_error_lines(exc):
            print(line, file=sys.stderr)
        return 2
    except ValuationError as exc:
        print(f"cannot solve: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return 0

    if snapshot is not None:
        print(render_snapshot(snapshot))
        print()
    print(render_projection(result.projection))
    print()
    print(render_summary(result.projection))
    print()
    print(render_reverse(result))
    return 0


def _input_error_lines(exc: ValueError) -> list[str]:
    if not isinstance(exc, ValidationError):
        return [f"invalid inputs: {exc}"]
    return ["invalid inputs:"] + [f"  {'.'.join(str(part) for part in error['loc']) or 'model'}: {error['msg']}" for error in exc.errors()]


if __name__ == "__main__":
    raise SystemExit(main())
