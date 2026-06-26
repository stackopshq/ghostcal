"""Pure domain logic. No I/O, no framework imports, no wall-clock reads.

Everything here is a pure function of its arguments so it can be exhaustively property-tested.
The current time is never read here — it is injected as a value (see application.ports.clock).
"""
