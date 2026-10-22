"""Outside services the signals read, besides EDGAR (which lives in the library's marketdata).

Each module turns an answer into values with a pure function the tests drive with a recorded
answer, and fetches through an injectable `Fetch` so the gate never touches the network.
A changed answer is a SourceChangedError — the check reports INVALID instead of a wrong number.
"""
