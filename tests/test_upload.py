"""Tests del export-viewer-service (orquestador). Los downstream se mockean.

Como ``DownstreamClient`` usa un único ``httpx.AsyncClient`` creado en el
``lifespan``, en cada test se sustituye ``http_client._client`` (después de que
el ``lifespan`` lo haya creado) por un cliente con ``httpx.MockTransport``
enlazado al router de respx, para que respx intercepte las llamadas a los
servicios downstream.
"""
from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

import app.core.downstream as downstream
from app.main import app


def _wire_respx(router: respx.Router) -> None:
    downstream.http_client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(router.handler)
    )


def test_health_live():
    with TestClient(app) as c:
        r = c.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_upload_no_token(valid_pdf_bytes):
    with TestClient(app) as c:
        r = c.post(
            "/v1/documents/upload",
            files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
        )
        assert r.status_code == 401


def test_upload_not_pdf(auth_headers):
    with TestClient(app) as c:
        r = c.post(
            "/v1/documents/upload",
            files={"file": ("notapdf.txt", b"hello world", "text/plain")},
            headers=auth_headers,
        )
        assert r.status_code == 415


def test_upload_too_large(auth_headers, monkeypatch):
    monkeypatch.setattr("app.main.settings.max_file_size_mb", 0)
    big = b"%PDF-" + b"x" * 10
    with TestClient(app) as c:
        r = c.post(
            "/v1/documents/upload",
            files={"file": ("big.pdf", big, "application/pdf")},
            headers=auth_headers,
        )
        assert r.status_code == 413


def test_upload_success(auth_headers, valid_pdf_bytes):
    with respx.mock as router:
        router.post("http://extractor.test/v1/extract").mock(
            return_value=httpx.Response(200, json={"text": "contenido extraído", "pages": 1})
        )
        router.post("http://crud.test/v1/documents").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "doc-1",
                    "filename": "test.pdf",
                    "text": "contenido extraído",
                    "pages": 1,
                    "pdf_hash": "hash123",
                    "idempotency_key": "pdf:hash123",
                },
            )
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text
            assert r.json()["id"] == "doc-1"


def test_upload_idempotent_returns_unique_document(auth_headers, valid_pdf_bytes):
    with respx.mock as router:
        router.post("http://extractor.test/v1/extract").mock(
            return_value=httpx.Response(200, json={"text": "texto", "pages": 1})
        )
        router.post("http://crud.test/v1/documents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "doc-mismo",
                    "filename": "test.pdf",
                    "text": "texto",
                    "pages": 1,
                    "pdf_hash": "hash-mismo",
                    "idempotency_key": "pdf:hash-mismo",
                },
            )
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r1 = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r1.status_code in (200, 201), r1.text
            id1 = r1.json()["id"]

            r2 = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r2.status_code in (200, 201), r2.text
            assert r2.json()["id"] == id1


def test_extractor_connection_error_returns_503(auth_headers, valid_pdf_bytes):
    with respx.mock as router:
        router.post("http://extractor.test/v1/extract").mock(
            side_effect=httpx.ConnectError("conexión rechazada")
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r.status_code == 503, r.text


def test_extractor_429_propagates(auth_headers, valid_pdf_bytes):
    with respx.mock as router:
        router.post("http://extractor.test/v1/extract").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "3"})
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r.status_code == 429, r.text
            assert r.headers.get("Retry-After") == "3"


def test_extractor_timeout_returns_504(auth_headers, valid_pdf_bytes):
    with respx.mock as router:
        router.post("http://extractor.test/v1/extract").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.post(
                "/v1/documents/upload",
                files={"file": ("test.pdf", valid_pdf_bytes, "application/pdf")},
                headers=auth_headers,
            )
            assert r.status_code == 504, r.text


def test_crud_endpoints_forward(auth_headers):
    with respx.mock as router:
        router.get("http://crud.test/v1/documents").mock(
            return_value=httpx.Response(
                200, json={"items": [], "total": 0, "page": 1, "page_size": 20}
            )
        )
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.get("/v1/documents", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["total"] == 0

    with respx.mock as router:
        router.get("http://crud.test/v1/documents/abc").mock(return_value=httpx.Response(404))
        with TestClient(app) as c:
            _wire_respx(router)
            r = c.get("/v1/documents/abc", headers=auth_headers)
            assert r.status_code == 404
