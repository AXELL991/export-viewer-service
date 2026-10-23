# Contract – Export Viewer Service

## Overview
The **Export Viewer Service** is the public entry point for clients (frontend, external callers). It orchestrates the workflow:
1. Receives a PDF file from the client.
2. Calls **pdf‑extractor‑service** (`POST /extract`) to obtain the extracted Markdown text.
3. Calls **document‑crud‑service** (`POST /documentos`) to persist the resulting document.
4. Provides read / export endpoints that proxy to **document‑crud‑service**.

The service **does not** store any data itself and never talks directly to MongoDB.

---

## Endpoints
| Method | Path | Description | Request | Response | Errors |
|--------|------|-------------|---------|----------|--------|
| **POST** | `/process` | Orchestrates full PDF processing: extract → persist. | `multipart/form-data` with file field `file` **or** raw PDF binary (`Content-Type: application/pdf`). | `201 Created` `UploadResponse` (status, message, filename, sha256). | `400 Bad Request` – invalid PDF, size limit, etc.<br>`409 Conflict` – duplicate document (from CRUD).<br>`502 Bad Gateway` – upstream service unavailable. |
| **GET** | `/documentos` | Proxy to **document‑crud‑service** list endpoint. | – | `200 OK` `ListaDocumentosResponse`. | `502 Bad Gateway` – if CRUD service down. |
| **GET** | `/documentos/{checksum}` | Proxy to **document‑crud‑service** retrieve endpoint. | – | `200 OK` `DocumentoResponse`. | `404 Not Found` – not in DB.<br>`502 Bad Gateway` – CRUD down. |
| **PUT** | `/documentos/{checksum}` | Proxy to update filename in the CRUD service. | `application/json` `ActualizarRequest`. | `200 OK` `MensajeResponse`. | `400 Bad Request`, `404 Not Found`, `502 Bad Gateway`. |
| **DELETE** | `/documentos/{checksum}` | Proxy to delete a document in the CRUD service. | – | `200 OK` `MensajeResponse`. | `404 Not Found`, `502 Bad Gateway`. |
| **GET** | `/health` | Health check that also verifies connectivity to both downstream services. | – | `200 OK` (all healthy) or `503 Service Unavailable` (any downstream unreachable). |
| **GET** | `/metrics` | Prometheus‑compatible metrics (optional). | – | `200 OK` plain‑text metrics. |

---

## Non‑functional Requirements (NFRs)
- **Reliability**: time‑outs and retries when calling downstream services (default 3 attempts, exponential back‑off, max 2 s per request).
- **Back‑pressure**: if either downstream service returns **429/503**, propagate the same status to the client.
- **Logging**: JSON logs to stdout, level via `LOGLEVEL`. Include request IDs for tracing across services.
- **Configuration**: URLs of the two downstream services (`EXTRACTOR_URL`, `CRUD_URL`) supplied via environment variables. All other settings via env vars (Twelve‑Factor).
- **Security**: Uniform error format `{ "error": "<code>", "message": "<text>" }` for any failure, never expose internal stack traces.
- **Docker resources**: container limited to **1 CPU** and **512 MiB–1 GiB** RAM.
- **Observability**: expose `/metrics` (Prometheus) and propagate trace IDs via `X‑Request‑Id` header.

---

## Contracts (JSON Schema snippets)
```json
// UploadResponse – same as in Document CRUD Service
{ "type": "object", "properties": { "status": { "type": "string" }, "message": { "type": "string" }, "filename": { "type": "string" }, "sha256": { "type": "string" } }, "required": ["status","message","filename","sha256"] }

// ListaDocumentosResponse – same as in Document CRUD Service
{ "type": "object", "properties": { "total": { "type": "integer" }, "documentos": { "type": "array", "items": { "$ref": "#/components/schemas/DocumentoResponse" } } }, "required": ["total","documentos"] }

// DocumentoResponse – same as in Document CRUD Service
{ "type": "object", "properties": { "archivo": { "type": "string" }, "texto": { "type": "string" }, "hash_seguridad": { "type": "string" } }, "required": ["archivo","texto","hash_seguridad"] }

// MensajeResponse – same as in Document CRUD Service
{ "type": "object", "properties": { "status": { "type": "string" }, "message": { "type": "string" } }, "required": ["status","message"] }

// ActualizarRequest – same as in Document CRUD Service
{ "type": "object", "properties": { "nuevo_nombre": { "type": "string" } }, "required": ["nuevo_nombre"] }
```

---

*Document version*: 1.0 – **2026‑10‑22**
