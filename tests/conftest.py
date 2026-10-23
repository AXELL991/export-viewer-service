"""
Fixtures y configuración compartida para los tests del export-viewer-service.

Los llamados a los downstream (extractor y CRUD) se mockean con respx, por lo
que no se necesita levantar ninguno de los otros servicios ni MongoDB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import app.core.downstream as downstream
import app.main as main_module
from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def point_urls_to_mock(monkeypatch):
    """Redirige los downstream a URLs ficticias mockeadas con respx."""
    monkeypatch.setattr(settings, "extractor_url", "http://extractor.test")
    monkeypatch.setattr(settings, "crud_url", "http://crud.test")
    monkeypatch.setattr(settings, "internal_api_token", "test-token")
    monkeypatch.setattr(settings, "rate_limit_max", 10000)
    monkeypatch.setattr(settings, "max_file_size_mb", 10)
    # Asegura que el rate limiter se recree con el nuevo límite al arrancar.
    main_module._rate_limiter = None
    # Aísla el circuit breaker entre tests (es un singleton de proceso).
    downstream.http_client._breakers.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"X-Internal-Token": "test-token"}


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
164
%%EOF"""
