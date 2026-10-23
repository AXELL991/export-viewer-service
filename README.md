# export-viewer-service

Servicio orquestador. Es el **único punto de entrada público** de la plataforma de extracción de PDF. Recibe un PDF, lo valida en streaming, lo envía al servicio extractor para obtener el texto y lo guarda mediante el servicio CRUD (el único dueño de MongoDB).

## Qué es

El orquestador expone la API pública bajo el prefijo `/v1`. No toca MongoDB directamente: delega la extracción en `pdf-extractor-service` y la persistencia en `document-crud-service`.

```text
         Cliente
           |
           |  POST /v1/documents/upload  (PDF + X-Internal-Token)
           v
+---------------------------+
| export-viewer-service     |  Orquestador (puerto 8000)
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

## Requisitos

- Docker + Compose v2, **o**
- Python 3.12 + uv.

## Clonado

Los tres repos deben quedar como **carpetas hermanas**:

```bash
git clone https://github.com/AXELL991/export-viewer-service.git     export-viewer-service
git clone https://github.com/AXELL991/pdf-extractor-service.git    pdf-extractor-service
git clone https://github.com/AXELL991/document-crud-service.git    document-crud-service

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

El `.env` **nunca se sube a git** (está en `.gitignore`). El mismo `INTERNAL_API_TOKEN` debe configurarse en los tres servicios. En producción, crear un usuario de Mongo limitado a la base de datos `document_crud_db`.

## Cómo INICIAR la FastAPI

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

El compose define estos servicios (red interna `interna`):

| Servicio | Puerto publicado | Accesible desde host |
|----------|------------------|----------------------|
| mongo | — (no publicado) | No |
| document-crud-service | — (no publicado) | No |
| pdf-extractor-service | — (no publicado) | No |
| export-viewer-service | `${PUBLIC_PORT:-8000}:8000` | Sí |

Solo el orquestador publica puerto. Mongo, extractor y CRUD quedan inaccesibles desde el host (solo red interna). Los nombres de servicio coinciden con las URLs de `.env.example` (`EXTRACTOR_URL=http://pdf-extractor-service:8000`, `CRUD_URL=http://document-crud-service:8000`).

### Opción B — Local sin Docker

1. Levantar solo Mongo (desde `export-viewer-service`):

```bash
docker compose up -d mongo
```

2. En cada terminal, arrancar un servicio con `uv run uvicorn app.main:app --host 0.0.0.0 --port <puerto>`, en este orden:

```bash
# terminal 1 - extractor (8001)
cd ../pdf-extractor-service
cp .env.example .env   # ajustar INTERNAL_API_TOKEN igual que en el orquestador
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

# terminal 2 - CRUD (8002)
cd ../document-crud-service
cp .env.example .env   # ajustar MONGO_URI e INTERNAL_API_TOKEN
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002

# terminal 3 - orquestador (8000)
cd ../export-viewer-service
cp .env.example .env   # ajustar EXTRACTOR_URL y CRUD_URL a localhost
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ajustar en el `.env` del orquestador:

```env
EXTRACTOR_URL=http://localhost:8001
CRUD_URL=http://localhost:8002
```

El punto de entrada es `app.main:app` y expone `GET /health/live`, `GET /health/ready` y Swagger en `GET /docs`.

## Cómo CERRAR la FastAPI

### Docker

- `docker compose stop` — detiene y conserva los contenedores.
- `docker compose down` — elimina contenedores y red, **conserva** los datos de Mongo (volumen `mongo-data`).
- `docker compose down -v` — **BORRA el volumen de Mongo** (los datos se pierden irreversiblemente).

> **Advertencia:** `docker compose down -v` borra permanentemente el volumen `mongo-data` con toda la información de MongoDB.

### Local, en primer plano

- `Ctrl+C` en cada terminal produce un apagado ordenado. Uvicorn espera las requests en curso antes de salir (`--timeout-graceful-shutdown 25`).

### Local, en segundo plano

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

Usar `kill -9` o `taskkill /F` solo si el proceso no responde tras 30 segundos.

### Orden recomendado de cierre

1. export-viewer-service (orquestador)
2. pdf-extractor-service y document-crud-service
3. mongo (al final)

### Cómo confirmar que se cerró

- `docker compose ps` debe mostrar los contenedores detenidos/ausentes.
- `curl http://localhost:8000/health/ready` debe fallar (conexión rechazada).

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| Puerto 8000 ocupado | Otro proceso escucha | Liberar el puerto o cambiar `PUBLIC_PORT` |
| `/health/ready` en 503 | Un downstream no responde | Revisar `docker compose logs` de extractor/CRUD/mongo |
| Servicio caído | Contenedor sin `healthy` | Revisar healthchecks y logs |
| Token inválido (401) | `X-Internal-Token` no coincide | Sincronizar `INTERNAL_API_TOKEN` en los 3 `.env` |
| `.env` ausente | No se copió desde `.env.example` | Ejecutar `cp .env.example .env` y rellenar valores |

## Variables de entorno

Tomadas del `.env.example` real del orquestador:

| Variable | Valor de ejemplo | Descripción |
|----------|------------------|-------------|
| `EXTRACTOR_URL` | `http://pdf-extractor-service:8000` | URL del servicio extractor |
| `CRUD_URL` | `http://document-crud-service:8000` | URL del servicio CRUD |
| `CONNECT_TIMEOUT` | `5` | Timeout de conexión TCP (s) |
| `EXTRACTOR_READ_TIMEOUT` | `60` | Timeout de lectura del extractor (s) |
| `CRUD_READ_TIMEOUT` | `5` | Timeout de lectura del CRUD (s) |
| `RETRY_ATTEMPTS` | `3` | Reintentos a downstream |
| `RETRY_BACKOFF_BASE` | `0.5` | Base del backoff exponencial (s) |
| `CIRCUIT_BREAKER_FAILURES` | `5` | Fallos consecutivos para abrir el circuito |
| `CIRCUIT_BREAKER_RECOVERY` | `30` | Segundos de circuito abierto |
| `RATE_LIMIT_MAX` | `60` | Requests máximos por IP en ventana |
| `RATE_LIMIT_WINDOW` | `60` | Ventana del rate limit (s) |
| `TRUSTED_PROXY` | `false` | Confiar en `X-Forwarded-For` |
| `MAX_FILE_SIZE_MB` | `10` | Tamaño máximo de PDF (MB) |
| `LOGLEVEL` | `info` | Nivel de logging |
| `INTERNAL_API_TOKEN` | `change-me` | Token interno (misma valor en los 3 servicios) |
| `PUBLIC_PORT` | `8000` | Puerto publicado del orquestador |
| `MONGO_ROOT_USER` | `mongouser` | Usuario root de Mongo (compose) |
| `MONGO_ROOT_PASS` | `mongopassword` | Contraseña root de Mongo (compose) |

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/v1/documents/upload` | Subir PDF (extraer + guardar) |
| GET | `/v1/documents` | Listar paginado (`page`, `page_size`) |
| GET | `/v1/documents/{id}` | Obtener documento |
| GET | `/v1/documents/{id}/export?format=txt\|json` | Exportar texto o JSON |
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness (incluye downstream) |

Todos los endpoints salvo `/health/*` requieren la cabecera `X-Internal-Token`. Se propaga `X-Request-ID` y `X-Internal-Token` a los servicios downstream.

## Tests y CI

```bash
uv sync --frozen
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

CI (GitHub Actions): `ruff`, `pytest` y `docker build`.
