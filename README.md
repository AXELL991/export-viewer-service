# export-viewer-service — Orquestador (punto de entrada)

Servicio FastAPI que actúa como único punto de entrada público del stack de extracción de PDF. Recibe un archivo PDF del cliente, lo envía al servicio extractor para obtener el texto, y persiste el resultado mediante el servicio CRUD. No almacena datos por sí mismo ni se conecta directamente a MongoDB.

## Acceso rápido (para entrar a la página localmente)

Si nunca has usado este proyecto, sigue estos 3 pasos:

1. Abre una terminal en la carpeta del proyecto (`export-viewer-service`).
2. Ejecuta:

   ```bash
   docker compose up --build -d
   ```

   Esto levanta toda la infraestructura y los microservicios automáticamente.

3. Espera a que los contenedores estén arriba y abre tu navegador en:

   **http://localhost:8000**

Esa es la página principal del sistema. Desde ahí puedes subir un PDF, ver el texto extraído y consultar los documentos guardados.

### URLs útiles

| Qué quieres hacer | URL |
|-------------------|-----|
| Página principal | http://localhost:8000 |
| Documentación de la API (Swagger) | http://localhost:8000/docs |
| Panel de Traefik | http://localhost:8080/dashboard/ |
| MongoDB Compass (puerto publicado) | localhost:27017 |

## Conectar con MongoDB Compass

MongoDB almacena los documentos extraídos y es accesible desde tu computadora para inspección visual con [MongoDB Compass](https://www.mongodb.com/products/compass).

### Paso 1: Levantar todo el stack

Desde la carpeta `export-viewer-service`, ejecuta:

```bash
docker compose up --build -d
```

Esto levanta junto: MongoDB, Redis, Traefik, document-crud-service, pdf-extractor-service y export-viewer-service.

El puerto `27017` de MongoDB está publicado en tu host.

### Paso 2: Abrir MongoDB Compass

1. Abre **MongoDB Compass**.
2. Haz clic en **"New Connection"**.
3. Pega la siguiente URI de conexión:

```
mongodb://pdf_admin:tu_contraseña@localhost:27017/pdf_extractor_db?authSource=admin
```

Reemplaza `tu_contraseña` por el valor de `MONGO_ROOT_PASSWORD` en el archivo `.env` del proyecto padre.

O bien, rellena los campos por separado:

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Puerto | `27017` |
| Usuario | `pdf_admin` |
| Contraseña | `tu_contraseña` (de `MONGO_ROOT_PASSWORD` en `.env`) |
| Auth DB | `admin` |

4. Haz clic en **Connect**.
5. Verás la base de datos `pdf_extractor_db` con sus colecciones.

### Paso 3: Cambiar la contraseña de MongoDB (opcional)

Si cambiaste `MONGO_ROOT_PASSWORD` en el archivo `.env` y necesitas que surta efecto:

1. Detén y borra todo (incluye el volumen de datos de MongoDB):

```bash
docker compose down -v
```

2. Levanta todo de nuevo:

```bash
docker compose up --build -d
```

⚠️ **Importante:** `MONGO_ROOT_PASSWORD` solo se aplica la **primera vez** que MongoDB inicia (cuando el volumen de datos está vacío). Si ya existen datos, el cambio en `.env` **no surtirá efecto** hasta que borres el volumen con `docker compose down -v` (esto elimina todos los documentos guardados).

## Responsabilidades

- Recibir PDFs vía `POST /v1/documents/upload`
- Validar tamaño del archivo y magic bytes (`%PDF-`)
- Calcular el hash SHA-256 del PDF para idempotencia
- Llamar a `pdf-extractor-service` para extraer el texto
- Llamar a `document-crud-service` para persistir el documento
- Exponer endpoints de consulta y exportación de documentos
- Aplicar cabeceras de seguridad y trazabilidad (`X-Request-ID`)

## Endpoints

Todos los endpoints de `/v1/*` requieren el header `X-Internal-Token`.

| Método | Ruta | Descripción | Respuesta exitosa |
|--------|------|-------------|-------------------|
| POST | `/v1/documents/upload` | Sube PDF, extrae texto y guarda | `201` |
| GET | `/v1/documents` | Lista documentos (paginado) | `200` |
| GET | `/v1/documents/{id}` | Obtiene un documento por ID | `200` |
| GET | `/v1/documents/{id}/export?format=txt\|json` | Exporta documento | `200` |
| GET | `/health/live` | Sonda de vitalidad | `200` |
| GET | `/health/ready` | Sonda de readiness (consulta downstream) | `200` |

## Variables de entorno

Se leen desde `.env` (copiar de `.env.example`).

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `EXTRACTOR_URL` | URL del servicio extractor | `http://pdf-extractor-service:8000` |
| `CRUD_URL` | URL del servicio CRUD | `http://document-crud-service:8000` |
| `CONNECT_TIMEOUT` | Timeout de conexión (segundos) | `5` |
| `EXTRACTOR_READ_TIMEOUT` | Timeout de lectura del extractor (segundos) | `60` |
| `CRUD_READ_TIMEOUT` | Timeout de lectura del CRUD (segundos) | `5` |
| `RETRY_ATTEMPTS` | Número de reintentos ante fallo downstream | `3` |
| `RETRY_BACKOFF_BASE` | Base de backoff exponencial (segundos) | `0.5` |
| `MAX_FILE_SIZE_MB` | Tamaño máximo de PDF en MB | `10` |
| `LOGLEVEL` | Nivel de logging | `info` |
| `INTERNAL_API_TOKEN` | Token interno para autenticación entre servicios | `change-me-in-production` |
| `PUBLIC_PORT` | Puerto publicado en el host | `8000` |

## Cómo ejecutar

### Desde el directorio del servicio

```bash
cd export-viewer-service
```

### Copiar variables de entorno

```bash
cp .env.example .env
```

### Levantar el stack completo (desde este directorio)

```bash
docker compose up --build -d
```

Esto levanta MongoDB, Redis, Traefik y los tres microservicios.

### Levantar solo infraestructura primero

```bash
docker compose -f ../docker-compose.infra.yml up --build -d
docker compose up --build -d
```

### Probar la API

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "X-Internal-Token: change-me-in-production" \
  -F "file=@documento.pdf"
```

Respuesta esperada: `201 { "sha256": "...", "filename": "...", "text": "...", "pages": N, ... }`

### Detener y limpiar

```bash
docker compose down                   # negocio
docker compose -f ../docker-compose.infra.yml down  # infraestructura
docker compose down -v                # incluye volúmenes
```

## Dependencias

- Python 3.12
- FastAPI, uvicorn
- httpx (cliente HTTP hacia downstream)
- pydantic-settings (configuración)
- python-json-logger (logging estructurado en JSON)
- python-multipart (upload de archivos)

## Tests

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

Los tests mockean los servicios downstream (extractor y CRUD) con `respx`, por lo que no requieren levantar el stack completo.
