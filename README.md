# export-viewer-service

Orquestador de microservicios para extraer texto de PDF. Es el único punto de entrada público.

## ¿Qué hace?

Recibe un PDF, lo envía al servicio extractor para obtener el texto, lo guarda en el servicio CRUD y te permite descargar el resultado en Markdown.

## Inicio rápido (Docker)

Los 3 microservicios deben quedar como carpetas hermanas:

```
export-viewer-service/
pdf-extractor-service/
document-crud-service/
```

Desde `export-viewer-service`:

```bash
cp .env.example .env
docker compose up --build -d
```

Luego entra a:

```
http://localhost:8000/
```

## Interfaz web

En la página principal puedes:

1. Pegar el token interno (`X-Internal-Token`) — se guarda en tu navegador.
2. Subir un PDF.
3. Ver el texto extraído y el número de páginas.
4. Descargar el contenido como archivo Markdown (`.md`).
5. Copiar el texto al portapapeles.

## API

Los endpoints de la API (`/v1/*`) requieren el header `X-Internal-Token`:

| Método | Ruta |
|--------|------|
| POST | `/v1/documents/upload` |
| GET | `/v1/documents` |
| GET | `/v1/documents/{id}` |
| GET | `/v1/documents/{id}/export?format=txt` |

Documentación Swagger: `http://localhost:8000/docs`

## Detener

```bash
docker compose stop
```

Para volver a usarlo:

```bash
docker compose start
```

Para eliminar todo:

```bash
docker compose down
```

## Variables clave (en `.env`)

| Variable | Descripción |
|----------|-------------|
| `INTERNAL_API_TOKEN` | Token interno (mismo valor en los 3 servicios) |
| `EXTRACTOR_URL` | URL del servicio extractor |
| `CRUD_URL` | URL del servicio CRUD |
| `PUBLIC_PORT` | Puerto publicado (por defecto 8000) |
