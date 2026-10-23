# export-viewer-service

Servicio orquestador. Es el **único punto de entrada público** de la plataforma de extracción
de PDF. Recibe un PDF, lo envía al servicio extractor, obtiene el texto y lo guarda mediante el
servicio CRUD (el único dueño de MongoDB).

## Arquitectura

```text
         Cliente
           |
           |  POST /v1/documents/upload  (PDF + X-Internal-Token)
           v
+---------------------------+
| export-viewer-service     |  Orquestador (público, puerto 8000)
|                           |
|  - valida tamaño (stream) |-->  POST /v1/extract
|  - hash SHA-256 del PDF   |        pdf-extractor-service (8001)
|  - Idempotency-Key        |        (sin estado, pool de procesos)
|  - reenvía al CRUD        |
+---------------------------+
           |  POST /v1/documents (Idempotency-Key)
           v
+---------------------------+
| document-crud-service     |  CRUD (único dueño de MongoDB)
|                           |--> MongoDB (document_crud_db)
|  - POST /v1/documents     |
|  - GET  /v1/documents{,/id}|
+---------------------------+
```

Flujo de upload:
1. El cliente envía el PDF al orquestador (`POST /v1/documents/upload`).
2. El orquestador lee el archivo en **streaming**, corta si supera `MAX_FILE_SIZE_MB` y valida
   los magic bytes `%PDF-`.
3. Calcula el hash SHA-256 del PDF y deriva la `Idempotency-Key`.
4. Llama al extractor (`POST /v1/extract`). Nunca reintenta tras un timeout de lectura.
5. Si el extractor tiene éxito, llama al CRUD (`POST /v1/documents`) con la misma
   `Idempotency-Key`. El mismo PDF subido dos veces genera **un único documento**.
6. Si el CRUD falla tras la extracción, se devuelve 502; el cliente puede reintentar sin
   duplicar (la `Idempotency-Key` es la misma).

### Tabla de errores del orquestador

| Código | Causa | Estado tras el fallo |
|--------|-------|----------------------|
| 401 | Token interno inválido | No se avanza |
| 413 | PDF mayor al límite (streaming, sin cargar todo) | No se avanza |
| 415 | No es un PDF (magic bytes) | No se avanza |
| 422 | PDF cifrado/corrupto o formato de export inválido | No se avanza |
| 429 | Rate limit del orquestador o cola del extractor llena | No se avanza |
| 502 | CRUD falló tras extraer (reintentar sin duplicar) o extractor falló | CRUD no tocado si falló el extractor |
| 503 | Circuito abierto o extractor/CRUD inaccesibles | No se avanza |
| 504 | Timeout de lectura del extractor | No se avanza |

Endpoints:
- `POST /v1/documents/upload` — sube PDF (multipart, campo `file`).
- `GET /v1/documents` — lista paginada (`page`, `page_size`).
- `GET /v1/documents/{id}` — obtiene un documento.
- `GET /v1/documents/{id}/export?format=txt\|json` — exporta texto o JSON.
- `GET /health/live`, `GET /health/ready`.

Todos los endpoints (salvo `/health/*`) requieren la cabecera `X-Internal-Token`.
Se propaga `X-Request-ID` y `X-Internal-Token` a los servicios downstream.

## Requisitos

- Docker + Compose v2, **o**
- Python 3.12 + uv.

## Clonado

Los tres repos deben quedar como **carpetas hermanas**:

```bash
git clone <repo-orchestrator>     export-viewer-service
git clone <repo-extractor>        pdf-extractor-service
git clone <repo-crud>             document-crud-service
ls
# export-viewer-service  pdf-extractor-service  document-crud-service
```

## Configuración

Desde la carpeta `export-viewer-service`:

```bash
cp .env.example .env
# Editar .env con los valores reales (ver tabla más abajo)
# Generar el token interno:
openssl rand -hex 32
```

En producción, crear un usuario de Mongo limitado a la base de datos `document_crud_db`.

## Cómo ejecutar

### Opción A — Docker Compose (recomendado)

Desde `export-viewer-service`:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f export-viewer-service
```

Verificar:

```bash
curl http://localhost:8000/health/ready
# Swagger UI:
open http://localhost:8000/docs
```

Solo el orquestador publica el puerto (`${PUBLIC_PORT:-8000}:8000`). Mongo, extractor y CRUD
quedan inaccesibles desde el host (solo red interna).

### Opción B — Local sin Docker

1. Levantar solo Mongo:

```bash
docker compose up -d mongo
```

2. En cada terminal, arrancar un servicio con `uv run uvicorn app.main:app --host 0.0.0.0 --port <puerto>`:

```bash
# terminal 1 - extractor (8001)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

# terminal 2 - CRUD (8002)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002

# terminal 3 - orquestador (8000)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ajustar `EXTRACTOR_URL=http://localhost:8001` y `CRUD_URL=http://localhost:8002` en el `.env`
del orquestador.

## Cómo cerrar la ejecución de FastAPI

### Docker

- `docker compose stop` — detiene y conserva los contenedores.
- `docker compose down` — elimina contenedores y red, **conserva** los datos de Mongo.
- `docker compose down -v` — **BORRA el volumen de Mongo** (los datos se pierden irreversiblemente).

> **Advertencia:** `docker compose down -v` borra permanentemente el volumen `mongo-data` con toda la información de MongoDB.

### Local

- `Ctrl+C` en cada terminal produce un apagado ordenado, esperando las requests en curso.

### Segundo plano

Linux/macOS:

```bash
lsof -i :8000      # obtener PID
kill -TERM <PID>   # apagado ordenado
```

Windows:

```cmd
netstat -ano | findstr :8000   # obtener PID
taskkill /PID <PID>
```

Usar `kill -9` o `taskkill /F` solo si el proceso no responde tras 30 s.

### Orden recomendado de cierre

1. export-viewer-service (orquestador)
2. pdf-extractor-service y document-crud-service
3. mongo (al final)

## Solución de problemas

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| Puerto 8000 ocupado | Otro proceso escucha | Liberar el puerto o cambiar `PUBLIC_PORT` |
| `/health/ready` en 503 | Un downstream no responde | Revisar `docker compose logs` de extractor/CRUD/mongo |
| Servicio caído | Contenedor sin `healthy` | Revisar healthchecks y logs |
| Token inválido (401) | `X-Internal-Token` no coincide | Sincronizar `INTERNAL_API_TOKEN` en los 3 `.env` |

## Referencia

### Variables de entorno (orquestador)

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `EXTRACTOR_URL` | `http://pdf-extractor-service:8000` | URL del extractor |
| `CRUD_URL` | `http://document-crud-service:8000` | URL del CRUD |
| `CONNECT_TIMEOUT` | `5` | Timeout de conexión TCP (s) |
| `EXTRACTOR_READ_TIMEOUT` | `60` | Timeout de lectura del extractor (s) |
| `CRUD_READ_TIMEOUT` | `5` | Timeout de lectura del CRUD (s) |
| `RETRY_ATTEMPTS` | `3` | Reintentos a downstream |
| `RETRY_BACKOFF_BASE` | `0.5` | Base del backoff exponencial (s) |
| `CIRCUIT_BREAKER_FAILURES` | `5` | Fallos para abrir el circuito |
| `CIRCUIT_BREAKER_RECOVERY` | `30` | Segundos de circuito abierto |
| `RATE_LIMIT_MAX` | `60` | Requests máximos por IP en ventana |
| `RATE_LIMIT_WINDOW` | `60` | Ventana del rate limit (s) |
| `TRUSTED_PROXY` | `false` | Confiar en `X-Forwarded-For` |
| `MAX_FILE_SIZE_MB` | `10` | Tamaño máximo de PDF (MB) |
| `LOGLEVEL` | `info` | Nivel de logging |
| `INTERNAL_API_TOKEN` | `change-me` | Token interno (misma valor en los 3 servicios) |
| `PUBLIC_PORT` | `8000` | Puerto publicado del orquestador |

### Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/v1/documents/upload` | Subir PDF (extraer + guardar) |
| GET | `/v1/documents` | Listar paginado |
| GET | `/v1/documents/{id}` | Obtener documento |
| GET | `/v1/documents/{id}/export?format=txt\|json` | Exportar |
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness (incluye downstream) |

## Tests y CI

```bash
uv sync --frozen
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

CI (GitHub Actions): `ruff`, `pytest` y `docker build`.
