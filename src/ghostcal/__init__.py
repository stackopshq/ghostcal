"""GhostCal — fast, correct scheduling.

Hexagonal layout:
    domain/         pure business logic, zero I/O (availability engine, booking rules)
    application/    use cases + ports (protocol interfaces implemented by infrastructure)
    infrastructure/ adapters: db, calendars, email, payments, cache
    presentation/   FastAPI routers, schemas, auth
"""

__version__ = "0.1.0"
