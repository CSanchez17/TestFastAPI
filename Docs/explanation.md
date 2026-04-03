## 🧠 Explicación para entrevista técnica (texto simple)

### 1. myapi.py (capa API / controlador)
- Es el punto de entrada de FastAPI.
- Define un `lifespan` con `asynccontextmanager` para inicializar DB en startup (`init_db()`).
- Tiene endpoint:
  - `GET /students/{student_id}`
  - Abre sesión asíncrona `AsyncSessionLocal()`
  - Ejecuta consulta `select(Student).where(Student.id==student_id)`
  - Si no existe devuelve 404
  - Si existe, retorna `StudentRead` (Pydantic) con datos JSON limpios.
- Ventaja: mantiene lógica HTTP separada del acceso DB.

### 2. database.py (infraestructura de datos)
- Define `DATABASE_URL` con driver async (`sqlite+aiosqlite`).
- Crea `engine` asíncrono `create_async_engine`.
- Crea `AsyncSessionLocal` (factory de sesión).
- Define `Base = declarative_base()` para modelos ORM.
- `init_db()`: 
  - crea tablas `Base.metadata.create_all`.
  - inserta datos semilla (`Alice`, `Bob`) si no existen.
- Ventaja: centraliza conexión y setup de DB.

### 3. models.py (modelo ORM / entidad)
- Define `class Student(Base)`:
  - `__tablename__ = "students"`
  - columnas: `id`, `name`, `age`, `year`
- Ventaja: abstracción de la tabla a clase Python y evitar SQL duro.

### 4. schemas.py (DTO / validación)
- Define `class StudentRead(BaseModel)`:
  - `student_id`, `name`, `age`, `year`
  - `Config.orm_mode=True`
- Ventaja: FastAPI puede retornar ORM -> JSON automáticamente con validación.

---

## 🔗 Flujo de petición

1. Llega `GET /students/{id}`.
2. `myapi` abre sesión con `AsyncSessionLocal`.
3. Consulta ORM `select(Student)` en `models`.
4. DB responde (SQLite `students.db`) usando infraestructura de `database`.
5. Resultado se mapea a `StudentRead`.
6. FastAPI envía JSON.

---

## 🚀 Por qué este diseño es “moderno”

- Separación clara (capa HTTP, capa infraestructura, modelo, DTO).
- Uso de async (`async`/`await`) para concurrencia y eficiencia I/O.
- Fácil de testear (se puede mockear `AsyncSessionLocal` y usar SQLite in-memory).
- Escalable a más features (`POST`, `PUT`, `DELETE`, servicio intermedio, repositorio).
- Cambiar DB (Postgres) es mínimo: solo `DATABASE_URL` + driver.

---

## 📝 Cómo explicarlo en entrevista

1. Di que encapsulaste acceso DB en database.py.
2. Menciona que models.py define entidad y schemas.py el contrato de API.
3. Explica que myapi.py solo orquesta y no hace SQL manual.
4. Señala que el diagrama (`Docs/Architecture.png`) muestra `App` -> `Infra` y workflow 1-4.
5. Termina con beneficio: código mantenible, prueba fácil, y migración de DB tranquila.