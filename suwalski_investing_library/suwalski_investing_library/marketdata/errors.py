class MarketDataError(Exception):
    """The provider could not produce a usable snapshot."""


class UnknownTickerError(MarketDataError):
    """The symbol does not resolve to a company with financial statements."""
