"""
Límite de tasa por cliente (IP) en el orquestador.

Es en memoria y por proceso: si se escalan varios contenedores del orquestador
detrás de un balanceador, cada uno aplica su propio límite. No se comparte
estado entre procesos.

Solo se confía en la cabecera ``X-Forwarded-For`` cuando ``TRUSTED_PROXY=true``.
"""
from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # ip -> lista de timestamps de requests en la ventana actual
        self._buckets: dict[str, list[float]] = {}

    def allow(self, client_ip: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._buckets.get(client_ip, [])
        # Conservar solo los de la ventana actual
        recent = [t for t in timestamps if t > window_start]
        if len(recent) >= self.max_requests:
            self._buckets[client_ip] = recent
            return False
        recent.append(now)
        self._buckets[client_ip] = recent
        return True
