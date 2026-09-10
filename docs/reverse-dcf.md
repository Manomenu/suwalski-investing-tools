# The reverse DCF model

## Forward direction

The projection is revenue-driven. For each year `t` in `1..N`:

```
revenue_t = revenue_0 * PROD(1 + g_i)   for i in 1..t
fcf_t     = revenue_t * margin_t
PV        = SUM fcf_t / (1+r)^t  +  TV / (1+r)^N
TV        = fcf_N * (1 + g_term) / (r - g_term)          [Gordon growth]
equity    = PV - net_debt
per share = equity / shares_outstanding
```

`margin_t` is the optimized FCF margin for every year by default. That is what an
"optimized free cash flow" input means on a reverse-DCF screen: the base case is the
business running at the margin you believe it settles at, not at today's margin. Set
`margin_ramp_years = N` (with `current_fcf_margin`) to walk there linearly instead; the
terminal value always rests on the optimized margin either way.

`r` must exceed `g_term`, otherwise the Gordon terminal value diverges — the contracts
reject that combination rather than returning a nonsense number.

## Reverse direction

Growth for years covered by a `growth_segment` is fixed. Every other year gets one shared
rate `g*`, and the solver looks for the `g*` where

```
f(g*) = value_per_share(g*) - current_price = 0
```

`f` is monotone in `g*` (more growth can only add value), so a bisection over the requested
bracket (default `-90%` to `+300%`) converges to machine precision in a few dozen
iterations. No numeric dependencies, and the result is deterministic — the same inputs
always produce the same number, which is what makes the regression test below meaningful.

If the price sits outside the bracket's value range, the solver refuses instead of
clamping: a price below the value at `-90%` growth (or above the value at `+300%`) means
the price is not explained by growth at all, but by the margin, the discount rate or the
terminal assumption. Saying so is more useful than returning the nearest bound.

## Worked example

The regression test in `suwalski_investing_library/tests/test_reverse.py` reproduces a
published reverse-DCF screen for NVDA: $224.03 price, 24.40B shares, TTM FCF $127.01B at a
42% margin, optimized FCF $106.04B at a 35% margin, 55% growth for years 1-3, 10% discount
rate, 3% terminal growth, 10-year horizon.

Revenue base is `127.01 / 0.42 = 302.40B`. The screen publishes **4.7%** for years 4-10;
this engine solves **4.76%**, with a 17.83% implied revenue CAGR across the whole path.
That test is the model's contract with reality — if a change moves that number, the change
is wrong until proven otherwise.

## Where the numbers come from

With `--ticker` (CLI) or `GET /market/{ticker}` (API), five inputs are read off Yahoo
Finance through `yfinance`:

| Field | Source |
| --- | --- |
| `price`, `shares_outstanding` | `fast_info` (`lastPrice`, `shares`) |
| `revenue_ttm` | `Total Revenue`, last four quarterly columns summed |
| `fcf_ttm` | the `Free Cash Flow` row, or `Operating Cash Flow - abs(Capital Expenditure)` where Yahoo omits it |
| `net_debt` | `Total Debt` minus cash and short-term investments; falls back to the reported `Net Debt` row, then to zero |

Caveats worth knowing before trusting a snapshot:

- yfinance is an unofficial scraper. Row labels move, symbols go missing, and a request can
  simply fail — every such case surfaces as a `MarketDataError` naming the field, never as
  a silent zero inside a valuation.
- Share counts are the current figure, not the weighted average, and multi-class companies
  (GOOGL, BRK) or ADRs frequently report only one class. Check the market cap in the header
  against a source you trust before leaning on the result.
- A company with fewer than four reported quarters (recent IPO) is refused rather than
  annualized from partial data.
- Snapshots are cached under `.artifacts/market/` for 15 minutes by default. Nothing here is
  a real-time quote.

## What the model does not do

- No mid-year discounting convention — cash arrives at year end.
- No share-count drift; dilution or buybacks have to be baked into the share count you pass.
- One solved rate for all open years (no fade curve). A fade is a plausible extension, but
  it makes the headline number harder to argue about, which is the whole point of the tool.
- No provider supplies assumptions. Optimized margin, growth, discount rate and terminal
  growth are always yours — a ticker only fills in the observable facts.
