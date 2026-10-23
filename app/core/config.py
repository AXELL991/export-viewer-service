"""Configuración central del export-viewer-service (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Logging
    loglevel: str = "INFO"

    # URLs de los servicios downstream (incluye esquema y puerto).
    # Valores por defecto para desarrollo local (sin Docker). En Docker Compose
    # se sobrescriben con los nombres de servicio de la red interna.
    extractor_url: str = "http://localhost:8001"
    crud_url: str = "http://localhost:8002"

    # Timeouts separados (segundos)
    connect_timeout: float = 5.0
    extractor_read_timeout: float = 60.0
    crud_read_timeout: float = 5.0

    # Reintentos con backoff exponencial y jitter
    retry_attempts: int = 3
    retry_backoff_base: float = 0.5

    # Circuit breaker por downstream
    circuit_breaker_failures: int = 5
    circuit_breaker_recovery: float = 30.0

    # Rate limit por IP (memoria, por proceso)
    rate_limit_max: int = 60
    rate_limit_window: int = 60
    trusted_proxy: bool = False

    # Límites
    max_file_size_mb: int = 10

    # Redis para rate limiting compartido (bulk head)
    redis_url: str = "redis://localhost:6379/0"

    # Auth interna (requerido, sin valor por defecto inseguro)
    internal_api_token: str

    # Puerto público (documentado para compose)
    public_port: int = 8000

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
