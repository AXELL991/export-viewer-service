"""
Circuit breaker simple por servicio downstream.

Tras ``failures`` fallos consecutivos se abre durante ``recovery`` segundos y
las llamadas se rechazan rápidamente con 503, sin contactar al servicio caído.
"""
from __future__ import annotations

import asyncio
import time


class CircuitBreaker:
    def __init__(self, failures: int, recovery: float):
        self.failures = max(1, failures)
        self.recovery = max(0.1, recovery)
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.recovery:
            # Medio abierto: permitir una prueba
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failures:
            self._opened_at = time.monotonic()
