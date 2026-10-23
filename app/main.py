"""
Punto de entrada del export-viewer-service (orquestador).

Es el ÚNICO punto de entrada público. Orquesta:
  PDF (cliente) -> extractor -> CRUD -> respuesta al cliente.

Rutas:
  POST   /v1/documents/upload           - Sube PDF, extrae y guarda
  GET    /v1/documents                  - Listar documentos (paginado)
  GET    /v1/documents/{id}             - Obtener documento
  GET    /v1/documents/{id}/export      - Exportar (txt|json)
  GET    /health/live                   - Liveness
  GET    /health/ready                  - Readiness (consulta downstream)
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.downstream import (
    DownstreamError,
    DownstreamTimeout,
    DownstreamUnavailable,
    http_client,
)
from app.core.logging_config import configure_logging
from app.core.rate_limit import RateLimiter

configure_logging(settings.loglevel.upper())
logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 65536  # 64 KiB


def _httpx_timeout(connect: float, read: float) -> httpx.Timeout:
    """Construye un httpx.Timeout con todos los parámetros requeridos por httpx 0.28+."""
    return httpx.Timeout(connect=connect, read=read, write=read, pool=30.0)

_rate_limiter: RateLimiter | None = None


def _client_ip(request: Request) -> str:
    """Devuelve la IP del cliente. Solo usa X-Forwarded-For si TRUSTED_PROXY=true."""
    if settings.trusted_proxy:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


async def _verify_internal_token(x_internal_token: str | None) -> None:
    if not secrets.compare_digest(
        (x_internal_token or "").encode(), settings.internal_api_token.encode()
    ):
        raise HTTPException(status_code=401, detail="Token interno inválido")


def _map_downstream_error(exc: Exception) -> HTTPException:
    """Traduce errores downstream a HTTPException del orquestador."""
    if isinstance(exc, DownstreamTimeout):
        return HTTPException(status_code=504, detail=exc.detail, headers=exc.headers)
    if isinstance(exc, DownstreamUnavailable):
        return HTTPException(status_code=503, detail=exc.detail, headers=exc.headers)
    if isinstance(exc, DownstreamError):
        return HTTPException(
            status_code=exc.status_code, detail=exc.detail, headers=exc.headers
        )
    return HTTPException(status_code=502, detail="Error en servicio downstream")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _rate_limiter
    await http_client.start()
    _rate_limiter = RateLimiter(settings.rate_limit_max, settings.rate_limit_window)
    logger.info("export-viewer-service iniciado")
    try:
        yield
    finally:
        await http_client.stop()
        logger.info("export-viewer-service detenido")


app = FastAPI(
    title="export-viewer-service",
    description="Orquestador público: extrae PDF y guarda vía CRUD",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def ui_index():
    return FileResponse("app/static/index.html")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception("Error no manejado", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
        headers={"X-Request-ID": request_id},
    )


# ---------------------------------------------------------------------------
# Middleware: X-Request-ID
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
        extra={"request_id": request_id},
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Middleware: auth interna (/health/* exento)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def internal_auth_middleware(request: Request, call_next):
    if request.url.path.startswith(("/health", "/docs", "/openapi.json", "/", "/static")):
        return await call_next(request)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    token = request.headers.get("X-Internal-Token")
    if not secrets.compare_digest(
        (token or "").encode(), settings.internal_api_token.encode()
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token interno inválido"},
            headers={"X-Request-ID": request_id},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Middleware: rate limit por IP
# ---------------------------------------------------------------------------
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/health"):
        return await call_next(request)
    assert _rate_limiter is not None
    ip = _client_ip(request)
    if not _rate_limiter.allow(ip):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=429,
            content={"detail": "Demasiadas peticiones. Intente más tarde."},
            headers={"Retry-After": "5", "X-Request-ID": request_id},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    """Consulta el /health/ready del extractor y del CRUD con timeout corto."""
    dependencies = {}
    overall = True

    for name, url in (
        ("extractor", f"{settings.extractor_url}/health/ready"),
        ("crud", f"{settings.crud_url}/health/ready"),
    ):
        try:
            resp = await http_client.client.get(url, timeout=_httpx_timeout(2.0, 3.0))
            dependencies[name] = "ok" if resp.status_code == 200 else "degraded"
            if resp.status_code != 200:
                overall = False
        except Exception as exc:  # noqa: BLE001
            dependencies[name] = f"unreachable: {exc}"
            overall = False

    if overall:
        return {"status": "ok", "dependencies": dependencies}
    raise HTTPException(
        status_code=503,
        detail={"status": "degraded", "dependencies": dependencies},
    )


# ---------------------------------------------------------------------------
# POST /v1/documents/upload
# ---------------------------------------------------------------------------
@app.post("/v1/documents/upload", tags=["documentos"])
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Archivo PDF a procesar"),
    x_internal_token: str | None = Header(default=None),
):
    """
    Recibe un PDF, lo envía al extractor y guarda el resultado en el CRUD.

    Errores:
    - 413: el archivo supera MAX_FILE_SIZE_MB (se corta en streaming).
    - 415: no es un PDF (magic bytes %PDF-).
    - 422: PDF cifrado/corrupto o supera límite de páginas.
    - 429: cola del extractor llena (Retry-After).
    - 502/503/504: fallo del extractor o del CRUD.
    """
    await _verify_internal_token(x_internal_token)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # Lectura en streaming con tope de tamaño y cálculo del hash SHA-256.
    chunks: list[bytes] = []
    total = 0
    max_bytes = settings.max_file_size_bytes
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo supera el límite de {settings.max_file_size_mb} MB",
            )
        chunks.append(chunk)
    pdf_bytes = b"".join(chunks)

    if not pdf_bytes.startswith(PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El archivo no es un PDF válido",
        )

    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    idempotency_key = f"pdf:{pdf_hash}"
    filename = file.filename or "documento.pdf"

    extract_headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Request-ID": request_id,
    }

    # 1) Extraer texto (nunca se reintenta tras timeout de lectura).
    try:
        extract_timeout = _httpx_timeout(settings.connect_timeout, settings.extractor_read_timeout)
        extract_resp = await http_client.call(
            "POST",
            f"{settings.extractor_url}/v1/extract",
            service_name="extractor",
            headers=extract_headers,
            files={
                "file": (
                    filename,
                    pdf_bytes,
                    file.content_type or "application/pdf",
                )
            },
            timeout=extract_timeout,
            idempotent=False,
        )
    except DownstreamError as exc:
        raise _map_downstream_error(exc)

    if extract_resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Cola del extractor llena. Intente más tarde.",
            headers={"Retry-After": extract_resp.headers.get("Retry-After", "5")},
        )
    if extract_resp.status_code == 413:
        raise HTTPException(
            status_code=413,
            detail=extract_resp.json().get("detail", "Archivo demasiado grande"),
        )
    if extract_resp.status_code == 415:
        raise HTTPException(
            status_code=415,
            detail=extract_resp.json().get("detail", "No es un PDF"),
        )
    if extract_resp.status_code == 422:
        raise HTTPException(
            status_code=422,
            detail=extract_resp.json().get("detail", "PDF inválido"),
        )
    if extract_resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="El extractor falló")

    try:
        extract_data = extract_resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="El extractor devolvió una respuesta inválida")

    text = extract_data.get("text", "")
    pages = extract_data.get("pages", 0)

    # 2) Guardar en CRUD (reintentable: lleva Idempotency-Key).
    crud_payload = {
        "filename": filename,
        "text": text,
        "pages": pages,
        "pdf_hash": pdf_hash,
    }
    crud_headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Request-ID": request_id,
        "Idempotency-Key": idempotency_key,
    }
    crud_timeout = _httpx_timeout(settings.connect_timeout, settings.crud_read_timeout)
    try:
        crud_resp = await http_client.call(
            "POST",
            f"{settings.crud_url}/v1/documents",
            service_name="crud",
            headers=crud_headers,
            json=crud_payload,
            timeout=crud_timeout,
            idempotent=True,
        )
    except DownstreamError:
        # Si falla el CRUD tras extraer, se devuelve 502 y el cliente puede
        # reintentar sin duplicar (misma Idempotency-Key).
        raise HTTPException(status_code=502, detail="No se pudo guardar el documento en el CRUD")

    if crud_resp.status_code == 409:
        raise HTTPException(
            status_code=409,
            detail=crud_resp.json().get("detail", "Conflicto de idempotencia"),
        )
    if crud_resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="El CRUD falló")

    body = crud_resp.json()
    return JSONResponse(status_code=201, content=body, headers={"X-Request-ID": request_id})


# ---------------------------------------------------------------------------
# GET /v1/documents  (paginado, se reenvía al CRUD)
# ---------------------------------------------------------------------------
@app.get("/v1/documents", tags=["documentos"])
async def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    x_internal_token: str | None = Header(default=None),
):
    await _verify_internal_token(x_internal_token)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    params = {"page": page, "page_size": page_size}
    try:
        resp = await http_client.call(
            "GET",
            f"{settings.crud_url}/v1/documents",
            service_name="crud",
            headers={
                "X-Internal-Token": settings.internal_api_token,
                "X-Request-ID": request_id,
            },
            params=params,
            timeout=_httpx_timeout(settings.connect_timeout, settings.crud_read_timeout),
            idempotent=True,
        )
    except DownstreamError as exc:
        raise _map_downstream_error(exc)
    return JSONResponse(content=resp.json(), headers={"X-Request-ID": request_id})


# ---------------------------------------------------------------------------
# GET /v1/documents/{id}
# ---------------------------------------------------------------------------
@app.get("/v1/documents/{doc_id}", tags=["documentos"])
async def get_document(
    request: Request,
    doc_id: str,
    x_internal_token: str | None = Header(default=None),
):
    await _verify_internal_token(x_internal_token)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        resp = await http_client.call(
            "GET",
            f"{settings.crud_url}/v1/documents/{doc_id}",
            service_name="crud",
            headers={
                "X-Internal-Token": settings.internal_api_token,
                "X-Request-ID": request_id,
            },
            timeout=_httpx_timeout(settings.connect_timeout, settings.crud_read_timeout),
            idempotent=True,
        )
    except DownstreamError as exc:
        raise _map_downstream_error(exc)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return JSONResponse(content=resp.json(), headers={"X-Request-ID": request_id})


# ---------------------------------------------------------------------------
# GET /v1/documents/{id}/export?format=txt|json
# ---------------------------------------------------------------------------
@app.get("/v1/documents/{doc_id}/export", tags=["documentos"])
async def export_document(
    request: Request,
    doc_id: str,
    format: str = Query("txt", description="txt o json"),
    x_internal_token: str | None = Header(default=None),
):
    await _verify_internal_token(x_internal_token)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        resp = await http_client.call(
            "GET",
            f"{settings.crud_url}/v1/documents/{doc_id}",
            service_name="crud",
            headers={
                "X-Internal-Token": settings.internal_api_token,
                "X-Request-ID": request_id,
            },
            timeout=_httpx_timeout(settings.connect_timeout, settings.crud_read_timeout),
            idempotent=True,
        )
    except DownstreamError as exc:
        raise _map_downstream_error(exc)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    doc = resp.json()
    if format == "json":
        return JSONResponse(content=doc, headers={"X-Request-ID": request_id})
    if format == "txt":
        return PlainTextResponse(
            content=doc.get("text", ""),
            headers={
                "X-Request-ID": request_id,
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
    raise HTTPException(status_code=422, detail="Formato no válido. Use 'txt' o 'json'.")
