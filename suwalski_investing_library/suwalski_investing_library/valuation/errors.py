class ValuationError(Exception):
    """Domain error: inputs are individually valid but the model cannot answer.

    Raised for unsolvable reverse-DCF setups (no free years, price outside the
    reachable value range). Input-shape problems are pydantic ValidationErrors.
    """
