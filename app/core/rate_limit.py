"""
Límite de tasa por cliente (IP) usando Redis como almacén compartido.

Permite que múltiples instancias del orquestador detrás de Traefik
compartan el mismo contador de peticiones por IP (bulk head).
Si Redis no está disponible, cae a un límite en memoria por proceso.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, redis_client: Optional[redis.Redis] = None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis = redis_client
        # Fallback en memoria por proceso si Redis no está disponible
        self._buckets: dict[str, list[float]] = {}

    def allow(self, client_ip: str) -> bool:
        if self._redis is not None:
            return self._allow_redis(client_ip)
        return self._allow_memory(client_ip)

    def _allow_redis(self, client_ip: str) -> bool:
        key = f"ratelimit:{client_ip}"
        now = time.time()
        try:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window_seconds)
            results = pipe.execute()
            count = results[0]
            if count == 1:
                # Primera petición en esta clave, asegurar expiración
                pass
            if count > self.max_requests:
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis rate limit falló, usando memoria: %s", exc)
            self._redis = None
            return self._allow_memory(client_ip)

    def _allow_memory(self, client_ip: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._buckets.get(client_ip, [])
        recent = [t for t in timestamps if t > window_start]
        if len(recent) >= self.max_requests:
            self._buckets[client_ip] = recent
            return False
        recent.append(now)
        self._buckets[client_ip] = recent
        return True


def create_redis_client(redis_url: str) -> Optional[redis.Redis]:
    """Crea un cliente Redis. Devuelve None si no se puede conectar."""
    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo conectar a Redis (%s), rate limit en memoria", exc)
        return None
