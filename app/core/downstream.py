"""
Cliente HTTP hacia los servicios downstream (extractor y CRUD).

Un único ``httpx.AsyncClient`` se crea en el ``lifespan`` de FastAPI.
Los reintentos usan backoff exponencial con jitter y respetan ``Retry-After``.
Nunca se reintenta el POST de extracción tras un timeout de lectura.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings

logger = logging.getLogger(__name__)

# Estados que merecen reintento (según contrato).
RETRYABLE_STATUS = {429, 502, 503, 504}


class DownstreamError(Exception):
    """Error genérico downstream (se traduce a 502 salvo que se indique otro)."""

    def __init__(self, detail: str, status_code: int = 502, headers: dict | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.headers = headers or {}


class DownstreamUnavailable(DownstreamError):
    def __init__(self, detail: str, headers: dict | None = None):
        super().__init__(detail, status_code=503, headers=headers)


class DownstreamTimeout(DownstreamError):
    def __init__(self, detail: str = "Timeout en servicio downstream", headers: dict | None = None):
        super().__init__(detail, status_code=504, headers=headers)


class DownstreamClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._breakers: dict[str, CircuitBreaker] = {}

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        self._client = httpx.AsyncClient(limits=limits, follow_redirects=True)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HTTP client no iniciado")
        return self._client

    def breaker_for(self, service_name: str) -> CircuitBreaker:
        breaker = self._breakers.get(service_name)
        if breaker is None:
            breaker = CircuitBreaker(
                failures=settings.circuit_breaker_failures,
                recovery=settings.circuit_breaker_recovery,
            )
            self._breakers[service_name] = breaker
        return breaker

    # ------------------------------------------------------------------ backoff
    @staticmethod
    def _retry_after(headers: httpx.Headers) -> float | None:
        raw = headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    async def _sleep_before_retry(self, attempt: int, headers: httpx.Headers) -> None:
        ra = self._retry_after(headers)
        if ra is not None and ra > 0:
            delay = min(ra, 30.0)
        else:
            delay = min(settings.retry_backoff_base * (2**attempt), 15.0) + random.uniform(
                0, settings.retry_backoff_base
            )
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------ request
    async def call(
        self,
        method: str,
        url: str,
        *,
        service_name: str,
        headers: dict | None = None,
        content: bytes | None = None,
        files: dict | None = None,
        data: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
        timeout: httpx.Timeout | None = None,
        idempotent: bool = False,
    ) -> httpx.Response:
        """
        Ejecuta una petición con reintentos y circuit breaker.

        - ``idempotent=True`` permite reintentar POST (envía Idempotency-Key).
        - El POST de extractor (idempotent=False) NUNCA se reintenta tras un
          timeout de lectura.
        """
        breaker = self.breaker_for(service_name)
        if breaker.is_open():
            raise DownstreamUnavailable(
                f"Circuito abierto para {service_name}",
            )

        last_error: Exception | None = None
        max_attempts = settings.retry_attempts + 1

        for attempt in range(max_attempts):
            try:
                resp = await self.client.request(
                    method,
                    url,
                    headers=headers,
                    content=content,
                    files=files,
                    data=data,
                    json=json,
                    params=params,
                    timeout=timeout,
                )

                # Éxito: cerrar circuito y devolver.
                if resp.status_code < 400:
                    breaker.record_success()
                    return resp

                # Errores que merecen reintento.
                if resp.status_code in RETRYABLE_STATUS:
                    breaker.record_failure()
                    last_error = DownstreamError(
                        f"{service_name} devolvió {resp.status_code}",
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                    )
                    if attempt + 1 < max_attempts:
                        await self._sleep_before_retry(attempt, resp.headers)
                        continue
                    # Último intento: propagar.
                    raise DownstreamError(
                        f"{service_name} devolvió {resp.status_code}",
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                    )

                # Otros errores de cliente/servidor: no se reintentan.
                breaker.record_failure()
                raise DownstreamError(
                    f"{service_name} devolvió {resp.status_code}",
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )

            except DownstreamError:
                raise
            except httpx.ReadTimeout as exc:
                breaker.record_failure()
                last_error = exc
                # El POST del extractor (no idempotente) NUNCA se reintenta
                # tras timeout de lectura.
                if not idempotent:
                    raise DownstreamTimeout("Timeout de lectura en " + service_name)
                if attempt + 1 < max_attempts:
                    await self._sleep_before_retry(attempt, httpx.Headers())
                    continue
                raise DownstreamTimeout("Timeout de lectura en " + service_name)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                breaker.record_failure()
                last_error = exc
                if attempt + 1 < max_attempts:
                    await self._sleep_before_retry(attempt, httpx.Headers())
                    continue
                raise DownstreamUnavailable(f"No se pudo conectar con {service_name}")
            except httpx.HTTPError as exc:
                breaker.record_failure()
                last_error = exc
                if attempt + 1 < max_attempts:
                    await self._sleep_before_retry(attempt, httpx.Headers())
                    continue
                raise DownstreamUnavailable(f"Error de HTTP con {service_name}: {exc}")

        # No debería llegarse aquí.
        if isinstance(last_error, DownstreamError):
            raise last_error
        raise DownstreamUnavailable(f"Error desconocido con {service_name}: {last_error}")


# Cliente compartido (singleton). Se arranca en el lifespan.
http_client = DownstreamClient()
