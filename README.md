# export-viewer-service — Orquestador (PUNTO DE ENTRADA)

Este servicio es el **único punto de entrada público** del stack. Desde aquí se ejecuta TODO el entorno con un solo comando.

## Arquitectura del flujo

```
Cliente
  │
  ▼  POST /v1/documents/upload  (header: X-Internal-Token)
export-viewer-service  (extract.universidad.localhost)
  │
  ├─ valida tamaño y magic bytes %PDF-
  ├─ calcula SHA-256 (idempotencia)
  ├─ llama al extractor: POST http://pdf-extractor-service:8000/v1/extract
  │     ▼
  │   pdf-extractor-service  (5 réplicas, pymupdf + ProcessPoolExecutor)
  │   └─ devuelve { text, pages }
  │
  ▼
document-crud-service: POST /v1/documents  (Idempotency-Key)
  └─ guarda en MongoDB
        │
        ▼
Cliente recibe 201 { sha256, filename, text, pages, ... }
```

## Inicio rápido (Docker) — EJECUTAR DESDE ESTE DIRECTORIO

Los servicios deben quedar como carpetas hermanas:

```
pdf_extractor_microservicios/
├─ export-viewer-service/      ← ejecutá acá
├─ pdf-extractor-service/
├─ document-crud-service/
├─ traefik-proxy/
└─ docker-compose.yml          (referencia, fuente de verdad en raíz)
```

### 1. Copiar variables de entorno

```bash
cp .env.example .env
```

### 2. Levantar todo el stack

```bash
docker compose up --build -d
```

Esto levanta: mongodb, redis, document-crud-service, pdf-extractor-service (5 réplicas), export-viewer-service y traefik.

### 3. Verificar que todo esté arriba

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Debés ver las 5 réplicas del extractor y el orquestador en estado `Up (healthy)`.

### 4. Probar la API

Subí un PDF:

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "X-Internal-Token: change-me-in-production" \
  -F "file=@documento.pdf"
```

Respuesta esperada: `201 { "sha256": "...", "filename": "...", "text": "...", "pages": N, ... }`

Otros endpoints (requieren `X-Internal-Token`):

| Método | Ruta |
|--------|------|
| GET | `/v1/documents` |
| GET | `/v1/documents/{id}` |
| GET | `/v1/documents/{id}/export?format=txt\|json` |
| GET | `/health/live` |

UI web: `http://extract.universidad.localhost/`
Swagger: `http://extract.universidad.localhost/docs`
Traefik dashboard: `http://extract.universidad.localhost/dashboard/`

### 5. Detener y limpiar

| Acción | Comando |
|--------|---------|
| Detener (conservar contenedores/volúmenes) | `docker compose stop` |
| Reanudar | `docker compose start` |
| Detener y eliminar contenedores + redes | `docker compose down` |
| Eliminar TODO (incluido volumen de MongoDB) | `docker compose down -v` |

## API

Todos los endpoints de `/v1/*` requieren el header `X-Internal-Token`:

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/v1/documents/upload` | Sube PDF, extrae y guarda → `201` |
| GET | `/v1/documents` | Listar documentos (paginado) |
| GET | `/v1/documents/{id}` | Obtener documento por ID |
| GET | `/v1/documents/{id}/export?format=txt\|json` | Exportar documento |
| GET | `/health/live` | Liveness probe |

Documentación Swagger: `http://extract.universidad.localhost/docs`

## Variables clave (en `.env`)

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `INTERNAL_API_TOKEN` | — | Token interno (mismo en los 3 servicios, requerido sin default inseguro) |
| `EXTRACTOR_URL` | `http://pdf-extractor-service:8000` | URL del extractor |
| `CRUD_URL` | `http://document-crud-service:8000` | URL del CRUD |
| `MAX_FILE_SIZE_MB` | `10` | Límite de tamaño del PDF (orquestador) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis para rate limiting |
| `PUBLIC_PORT` | `8000` | Puerto publicado en el host |

## Pruebas de carga (k6)

Desde este directorio, con el stack levantado:

```bash
k6 run k6_load_test.js
```

O con variables personalizadas:

```bash
BASE_URL=http://localhost:8000 INTERNAL_TOKEN=change-me-in-production PDF_PATH=../pdf-extractor-service/tests/stress/pdfs/stress_9mb.pdf k6 run k6_load_test.js
```

## Cierre ordenado

`docker compose stop` envía `SIGTERM` a todos los contenedores. uvicorn usa `--timeout-graceful-shutdown 25` para finalizar las requests en vuelo antes de apagar. El `ProcessPoolExecutor` del extractor espera los jobs en curso.