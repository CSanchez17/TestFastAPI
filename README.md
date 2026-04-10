# TestFastAPI (FastAPI + SQLAlchemy Async + SQLite)

Proyecto de ejemplo que muestra una arquitectura modular y clara para FastAPI con base de datos SQLite usando SQLAlchemy async.

## Estructura de archivos

- `myapi.py` - API principal y rutas. Maneja el ciclo de vida y endpoints REST.
- `database.py` - Configuración de SQLAlchemy, engine async y `init_db()`.
- `models.py` - Modelo ORM `Student`.
- `schemas.py` - Esquema Pydantic `StudentRead` para respuestas.

## Dependencias

- Python 3.14
- fastapi
- uvicorn
- sqlalchemy
- aiosqlite
- pydantic

Instalación:

```bash
cd c:\Users\Sanch\Desktop\Projekte\Test\TestFastAPI
c:/Users/Sanch/Desktop/Projekte/Test/Gen_AI/venv/Scripts/python.exe -m pip install fastapi uvicorn sqlalchemy aiosqlite pydantic
```

## Ejecución

```bash
cd c:\Users\Sanch\Desktop\Projekte\Test\TestFastAPI
c:/Users/Sanch/Desktop/Projekte/Test/Gen_AI/venv/Scripts/python.exe -m uvicorn myapi:app --reload
```

## Configuración de IA

Este proyecto incluye funcionalidades de IA usando modelos locales con Ollama o servicios en la nube.

### Configuración

1. Copia el archivo `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edita `.env` según tus necesidades. Para usar Ollama con deepseek-r1:8b:
   ```
   CONCIERGE_LLM_PROVIDER=local
   LOCAL_LLM_MODEL=deepseek-r1:8b
   ```

3. Asegúrate de que Ollama esté corriendo:
   ```bash
   ollama serve
   ```

4. Instala el modelo si no lo tienes:
   ```bash
   ollama pull deepseek-r1:8b
   ```

### Variables de Entorno

- `CONCIERGE_LLM_PROVIDER`: `none`, `local`, `cloud`, `auto`
- `LOCAL_LLM_MODEL`: Nombre del modelo en Ollama (ej: `deepseek-r1:8b`)
- `LOCAL_LLM_BASE_URL`: URL de Ollama (default: `http://localhost:11434`)
- `CLOUD_LLM_API_KEY`: API key para servicios en la nube
- `CLOUD_LLM_MODEL`: Modelo en la nube (ej: `gpt-4o-mini`)

Para cambiar el modelo fácilmente, solo modifica la variable `LOCAL_LLM_MODEL` en tu archivo `.env`.

1. `myapi.py` usa `lifespan` con `init_db()` de `database.py` para inicializar DB en startup.
2. `database.py`:
   - Crea `engine` async y `AsyncSessionLocal`.
   - Crea tabla `students` y datos semilla con `init_db()`.
3. `models.py` define el modelo `Student`.
4. `schemas.py` define `StudentRead` y `orm_mode` para serializar objetos ORM.
5. `myapi.py`:
   - Endpoint `GET /students/{student_id}`
   - Usa sesión async para query `Student` y retorna `StudentRead`.

## Arquitectura recomendada con separación de capas

1. `routers/students.py` (handlers de rutas)
2. `services/student_service.py` (lógica del negocio)
3. `repositories/student_repo.py` (consultas DB)
4. `database.py` (infraestructura DB)
5. `models.py` (ORM)
6. `schemas.py` (DTO)

## Testing básico

- Unit tests con `pytest` y `sqlite+aiosqlite:///:memory:` para evitar usar disco.
- Verificar endpoint por request con `httpx`.

```python
import pytest
from httpx import AsyncClient
from myapi import app

@pytest.mark.asyncio
async def test_get_student_1():
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/students/1")
        assert r.status_code == 200
        assert r.json()["name"] == "Alice"
```

---

## Diagrama de Arquitectura

Se incluye un diagrama detallado en `Docs/Components_workflow.png` y `Docs/Arquitecture.png`. Revisa el archivo para la visualización completa.

### Arquitectura
![Architecture Diagram](Docs/Arquitecture.png)

Este diagrama representa una arquitectura **basada en capas** (inspirada en *Clean Architecture* u *Onion Architecture*). La idea central es que el código no sea un "espagueti" donde todo está mezclado, sino que cada archivo tenga una misión única y sagrada.

---

## 🧩 Desglose de los Componentes

### 1. `myapi.py` (La Capa de Entrada / Controlador)
Es el "portero" de tu aplicación. Su único trabajo es recibir peticiones HTTP, llamar a las funciones correctas y devolver una respuesta.
*   **No sabe** cómo se guardan los datos en la base de datos.
*   **Solo sabe** que necesita una "sesión" y que debe devolver un JSON válido.

### 2. `database.py` (La Infraestructura / Fontanería)
Aquí reside la configuración técnica. Define cómo nos conectamos al mundo exterior (en este caso, SQLite).
*   Configura el `engine` y el `AsyncSessionLocal`.
*   Es el lugar donde decides si usas PostgreSQL, MySQL o una simple base de datos en memoria.

### 3. `models.py` (El Dominio / Entidades ORM)
Es la representación de tus tablas en código Python. Es el lenguaje que entiende **SQLAlchemy**.
*   Define que un "Estudiante" tiene un nombre (string) y una edad (integer).
*   Es el puente entre tu código y las filas de la base de datos.

### 4. `schemas.py` (El Contrato / DTO)
Aquí es donde **Pydantic** brilla. Mientras que los `models` son para la DB, los `schemas` son para el cliente (el navegador o la app móvil).
*   **Validación:** Se asegura de que, si pides un ID, sea un número y no un texto.
*   **Filtrado:** Permite ocultar datos sensibles (como contraseñas) para que no salgan en la respuesta JSON.

---

## 🚀 ¿Por qué es útil esta arquitectura?

Utilizar este enfoque no es por capricho estético; tiene beneficios prácticos muy claros:



### 1. Separación de Responsabilidades (SoC)
Si tienes un error en la validación de datos, vas directo a `schemas.py`. Si la base de datos no conecta, vas a `database.py`. No tienes que rebuscar en un archivo de 2,000 líneas de código para encontrar el problema.

### 2. Facilidad de Testing
Como las capas están separadas, puedes probar la lógica de tus rutas en `myapi.py` usando una base de datos de prueba (mocking) sin afectar tus datos reales. Es mucho más sencillo aislar componentes.

### 3. Intercambiabilidad (Mantenimiento a largo plazo)
Imagina que hoy usas SQLite, pero mañana tu app es un éxito y necesitas **PostgreSQL**. 
*   **En una mala arquitectura:** Tendrías que cambiar código en todos tus archivos.
*   **En esta arquitectura:** Solo cambias la URL de conexión en `database.py` y quizás algún detalle menor en `models.py`. El resto de la app ni se entera del cambio.

### 4. Escalabilidad
Cuando necesites agregar "Profesores", "Cursos" o "Calificaciones", simplemente sigues el patrón: creas su modelo, su esquema y su ruta. El proyecto crece de forma organizada y predecible, evitando el código redundante.

> **En resumen:** Esta arquitectura separa **qué** hace tu aplicación (negocio/modelos) de **cómo** lo hace (infraestructura/DB) y de **cómo** se muestra (API/schemas). Es la diferencia entre un cajón de sastre y una caja de herramientas profesional.

---
## Flujo de componentes:
![Componentsworkflow Diagram](Docs/Components_workflow.png)




- **Estructura del Proyecto**: En la parte superior, verás los dos grandes subgrafos: `APP[FASTAPI APP]` (que contiene `myapi.py`) e `INFRA[INFRASTRUCTURE]` (que contiene `database.py`, `models.py` y `schemas.py`). Las flechas `USES` muestran cómo la aplicación principal interactúa con cada componente de la infraestructura.

- **El Flujo de Trabajo**: En la parte inferior, se desglosa el flujo paso a paso de una solicitud `GET /students/{student_id}`:

  1. `myapi.py` utiliza `database.py` para abrir una sesión (`AsyncSessionLocal` factory).
  2. Se ejecuta una consulta (`select(Student)`) utilizando el modelo ORM definido en `models.py` contra la base de datos SQLite (`students.db`).
  3. El resultado ORM crudo se procesa y valida utilizando los esquemas Pydantic definidos en `schemas.py` (convirtiéndolo en `StudentRead`).
  4. Se devuelve la respuesta final en formato JSON limpio a la API.

- **Ventajas de la Arquitectura**: En el panel lateral derecho, se resumen los puntos clave que mencionaste sobre por qué este diseño es moderno y escalable, incluyendo la Separación de Responsabilidades, Testabilidad Fácil, Escalabilidad y la Facilidad para Cambiar de Base de Datos.

---

## Migrations
Cuando modificas tus modelos (`models.py`) y necesitas que la base de datos se actualice sin romperse, sigue estos pasos:

---

### 1. Preparación del Modelo (`models.py`)
Antes de ejecutar cualquier comando, asegúrate de que el código sea "amigable" con la base de datos:

*   **Regla de Oro:** Si añades una columna `NOT NULL` (obligatoria), debe tener un `server_default` como **string**.
*   **Ejemplo:** `server_default="1"` (si es un ID) o `server_default="pendiende"` (si es un texto).

---

### 2. Generación de la Migración
Este paso crea el "plano" de los cambios. Alembic compara tu código con la base de datos actual.

**Comando:**
```bash
alembic revision --autogenerate -m "descripción_del_cambio"
```
*   **¿Qué hace?** Crea un archivo `.py` en la carpeta `alembic/versions/`.
*   **Consejo Pro:** Abre ese archivo y revisa las funciones `upgrade()` y `downgrade()`. Es buena práctica verificar que Alembic haya detectado los cambios correctamente antes de aplicarlos.

---

### 3. Aplicación de la Migración
Este paso ejecuta el SQL real en tu archivo `.db`.

**Comando:**
```bash
alembic upgrade head
```
*   **`head`**: Significa "llévame a la versión más reciente disponible".
*   **Resultado esperado:** Deberías ver un mensaje como `INFO [alembic.runtime.migration] Running upgrade -> [ID], descripción`.


---

### 4. Sincronización de Datos Iniciales (Seeding)
Una vez que la estructura (el esqueleto) está lista, necesitas que los datos (el contenido) tengan sentido.

**Acción:** Ejecuta tu aplicación FastAPI.
*   Tu función `init_db()` (que definimos antes) entrará en acción.
*   Verificará si el usuario Admin (ID 1) existe. Si no, lo crea.
*   Esto garantiza que el `server_default="1"` que pusimos en la migración tenga un usuario real al cual apuntar.

---

### 🚨 ¿Qué hacer si algo sale mal? (Plan de Rescate)

Si el `upgrade head` falla y te da errores de "columna duplicada" o "inconsistencia", usa el **Reset de Emergencia**:

1.  **Borra el archivo `.db`** (Solo en desarrollo).
2.  **Borra los archivos** dentro de `alembic/versions/` (limpia el historial).
3.  **Genera la migración inicial de nuevo:**
    ```bash
    alembic revision --autogenerate -m "initial_schema"
    ```
4.  **Aplica:**
    ```bash
    alembic upgrade head
    ```

---
