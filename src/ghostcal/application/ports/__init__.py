"""Ports: protocol interfaces the infrastructure layer implements (repositories,
calendar clients, email sender, clock). The domain and use cases depend on these
abstractions, never on concrete adapters.
"""

from ghostcal.application.ports.clock import Clock

__all__ = ["Clock"]
