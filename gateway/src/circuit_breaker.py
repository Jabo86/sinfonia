"""
Sinfonia — Circuit Breaker

Implementazione semplice e async-friendly di un circuit breaker.
Quando un provider fallisce N volte, viene isolato per un periodo.
"""

from __future__ import annotations

import time
from enum import Enum

import structlog

log = structlog.get_logger()


class BreakerState(str, Enum):
    CLOSED = "closed"      # funzionamento normale
    OPEN = "open"          # provider isolato
    HALF_OPEN = "half_open"  # verifica se il provider è tornato


class CircuitBreaker:
    """
    Circuit breaker per un singolo provider.

    - failure_threshold: numero di fallimenti consecutivi per aprire
    - recovery_timeout: secondi di cooldown prima di tentare HALF_OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 120.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = BreakerState.CLOSED
        self.opened_at: float | None = None

    def is_available(self) -> bool:
        """Verifica se il breaker permette la chiamata."""
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            elapsed = time.time() - (self.opened_at or 0)
            if elapsed >= self.recovery_timeout:
                self.state = BreakerState.HALF_OPEN
                log.info("circuit_breaker.half_open")
                return True
            return False
        # HALF_OPEN: permetti una chiamata di prova
        return True

    def record_success(self) -> None:
        """Registra una chiamata riuscita e resetta il breaker."""
        if self.state != BreakerState.CLOSED:
            log.info("circuit_breaker.closed", from_state=self.state.value)
        self.failures = 0
        self.state = BreakerState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        """Registra un fallimento e apre il breaker se necessario."""
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            log.warning(
                "circuit_breaker.opened",
                failures=self.failures,
                cooldown_seconds=self.recovery_timeout,
            )
