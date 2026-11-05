# export-viewer-service — Orquestador (punto de entrada)

Servicio FastAPI que actúa como único punto de entrada público del stack de extracción de PDF. Recibe un archivo PDF del cliente, lo envía al servicio extractor para obtener el texto, y persiste el resultado mediante el servicio CRUD. No almacena datos por sí mismo ni se conecta directamente a MongoDB.

## URLs útiles

| Qué quieres hacer | URL |
|-------------------|-----|
| Página principal | http://localhost:8000 |
| Documentación de la API (Swagger) | http://localhost:8000/docs |
| Panel de Traefik | http://localhost:8080/dashboard/ |
| MongoDB Compass (puerto publicado) | localhost:27017 |

---

## ⚙️ Configuración inicial (solo hay que hacerla UNA vez)

Estos pasos solo se ejecutan la primera vez que clonás o configurás el proyecto en tu máquina.

### 1. Copiar el archivo de variables de entorno

Desde la carpeta `export-viewer-service`:

```bash
cp .env.example .env
```

Edita `.env` si necesitás ajustar valores (contraseñas, puertos, límites, etc.). El `.env` real no se sube al repositorio (está en `.gitignore`).

### 2. Levantar todo el stack por primera vez

Desde la carpeta `export-viewer-service`:

```bash
docker compose up --build -d
```

Esto levanta automáticamente: MongoDB, Redis, Traefik, document-crud-service, pdf-extractor-service y export-viewer-service.

Elimina la necesidad de ejecutar comandos separados para infraestructura y microservicios.

---

## 🚀 Cada vez que quieras iniciar el proyecto

Desde la carpeta `export-viewer-service`:

```bash
docker compose up --build -d
```

Luego esperá a que los contenedores estén arriba y abrí tu navegador en:

**http://localhost:8000**

Desde ahí podés subir un PDF, ver el texto extraído y consultar los documentos guardados.

### Verificar que todo esté corriendo

```bash
docker ps
```

Deberían aparecer los contenedores: `mongo`, `redis`, `traefik`, `document-crud-service`, `pdf-extractor-service` y `export-viewer-service`.

---

## 🔌 Conectar con MongoDB Compass

MongoDB almacena los documentos extraídos y es accesible desde tu computadora para inspección visual con [MongoDB Compass](https://www.mongodb.com/products/compass).

### Paso 1: Levantar el stack

Asegurate de que el contenedor de MongoDB esté corriendo:

```bash
docker compose up --build -d
```

El puerto `27017` está publicado en tu host.

### Paso 2: Abrir MongoDB Compass

1. Abrí **MongoDB Compass**.
2. Hacé clic en **"New Connection"**.
3. Pegá la siguiente URI de conexión:

```
mongodb://pdf_admin:tu_contraseña@localhost:27017/pdf_extractor_db?authSource=admin
```

Reemplazá `tu_contraseña` por el valor de `MONGO_ROOT_PASSWORD` en el archivo `.env` del proyecto padre (raíz del repositorio).

O bien, rellená los campos por separado:

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Puerto | `27017` |
| Usuario | `pdf_admin` |
| Contraseña | `tu_contraseña` (de `MONGO_ROOT_PASSWORD` en `.env`) |
| Auth DB | `admin` |

4. Hacé clic en **Connect**.
5. Verás la base de datos `pdf_extractor_db` con sus colecciones.

⚠️ **Advertencia de versión:** MongoDB Compass puede mostrar un aviso indicando que la versión 6.0 es end-of-life (EOL). Esto es solo informativo; el proyecto sigue funcionando normalmente. Si necesitás actualizar, cambiá `image: mongo:6.0` por `mongo:7.0` (o `mongo:8.0`) en el `docker-compose.yml` y recreá el contenedor.

### Paso 3: Cambiar la contraseña de MongoDB (opcional)

`MONGO_ROOT_PASSWORD` solo se aplica la **primera vez** que MongoDB inicia (cuando el volumen de datos está vacío). Si ya existen datos, cambiarlo en `.env` no surtirá efecto hasta que borres el volumen:

```bash
docker compose down -v   # ⚠️ borra todos los documentos guardados de MongoDB
docker compose up --build -d
```

---

## 🛑 Para parar todo

Desde la carpeta `export-viewer-service`:

```bash
docker compose down          # detiene y elimina contenedores (mantiene datos de MongoDB)
```

Si querés borrar también los datos de MongoDB (volúmenes):

```bash
docker compose down -v       # detiene, elimina contenedores y borra datos de MongoDB
```

Verificá que todo se detuvo con:

```bash
docker ps
```

No debería aparecer ningún contenedor del proyecto.

---

## 📋 Endpoints

Todos los endpoints de `/v1/*` requieren el header `X-Internal-Token`.

| Método | Ruta | Descripción | Respuesta exitosa |
|--------|------|-------------|-------------------|
| POST | `/v1/documents/upload` | Sube PDF, extrae texto y guarda | `201` |
| GET | `/v1/documents` | Lista documentos (paginado) | `200` |
| GET | `/v1/documents/{id}` | Obtiene un documento por ID | `200` |
| GET | `/v1/documents/{id}/export?format=txt\|json` | Exporta documento | `200` |
| GET | `/health/live` | Sonda de vitalidad | `200` |
| GET | `/health/ready` | Sonda de readiness (consulta downstream) | `200` |

### Probar la API

```bash
curl -X POST http://localhost:8000/v1/documents/upload \
  -H "X-Internal-Token: change-me-in-production" \
  -F "file=@documento.pdf"
```

Respuesta esperada: `201 { "sha256": "...", "filename": "...", "text": "...", "pages": N, ... }`

---

## 🧠 Responsabilidades

- Recibir PDFs vía `POST /v1/documents/upload`
- Validar tamaño del archivo y magic bytes (`%PDF-`)
- Calcular el hash SHA-256 del PDF para idempotencia
- Llamar a `pdf-extractor-service` para extraer el texto
- Llamar a `document-crud-service` para persistir el documento
- Exponer endpoints de consulta y exportación de documentos
- Aplicar cabeceras de seguridad y trazabilidad (`X-Request-ID`)

---

## 📦 Variables de entorno

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

---

## 🔧 Dependencias

- Python 3.12
- FastAPI, uvicorn
- httpx (cliente HTTP hacia downstream)
- pydantic-settings (configuración)
- python-json-logger (logging estructurado en JSON)
- python-multipart (upload de archivos)

---

## 🧪 Tests

```bash
uv run pytest tests/ -v
uv run ruff check app/ tests/
```

Los tests mockean los servicios downstream (extractor y CRUD) con `respx`, por lo que no requieren levantar el stack completo.
