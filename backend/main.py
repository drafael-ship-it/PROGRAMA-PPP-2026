from fastapi import FastAPI, Form, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from typing import List
import asyncio
import base64
import hmac
import json
import os
import pymysql
import hashlib
import time
import re
import unicodedata
from dotenv import load_dotenv
from datetime import datetime
from pypdf import PdfWriter

load_dotenv()

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiados intentos fallidos. Espere un momento antes de intentar de nuevo."}
    )

app.mount("/formatos", StaticFiles(directory="formatos"), name="formatos")
app.mount("/archivos_expedientes", StaticFiles(directory="archivos_expedientes"), name="archivos_expedientes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_DIR = "archivos_expedientes"
TOKEN_SECRET = os.environ.get("PPP_TOKEN_SECRET", "cambiar-este-secreto-en-produccion")
TOKEN_DURATION_SECONDS = 30 * 60
DOCENTE_DEFAULT_ID = int(os.environ.get("PPP_DOCENTE_DEFAULT_ID", "1"))
EXPEDIENTES_FINALES_DIR = "expedientes_finales"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
DOMINIO_CORREO_PERMITIDO = os.getenv("DOMINIO_CORREO_PERMITIDO", "@lamolina.edu.pe").strip().lower()
FRONTEND_INDEX_URL = os.getenv("FRONTEND_INDEX_URL", os.getenv("FRONTEND_ALUMNO_URL", "/tramites/practicas_PreProfesionales/index.html"))
ALUMNO_FRONTEND_URL = os.getenv("ALUMNO_FRONTEND_URL", "/tramites/practicas_PreProfesionales/alumno.html")
GOOGLE_OAUTH_TIMEOUT_SECONDS = float(os.getenv("GOOGLE_OAUTH_TIMEOUT_SECONDS", "10"))
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
os.makedirs(EXPEDIENTES_FINALES_DIR, exist_ok=True)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY or os.urandom(32).hex(),
    same_site="lax",
    https_only=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
)

oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        # Metadata oficial: https://accounts.google.com/.well-known/openid-configuration
        # Se configuran endpoints explicitos para que /login no dependa de una llamada saliente previa.
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        access_token_url="https://oauth2.googleapis.com/token",
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        issuer="https://accounts.google.com",
        client_kwargs={"scope": "openid email profile"},
        timeout=GOOGLE_OAUTH_TIMEOUT_SECONDS,
    )


def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
        charset=os.getenv("DB_CHARSET", "utf8mb4")
    )


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def crear_token(payload: dict) -> str:
    payload = payload.copy()
    payload["exp"] = int(time.time()) + TOKEN_DURATION_SECONDS
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _base64url_encode(payload_bytes)
    firma = hmac.new(TOKEN_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_base64url_encode(firma)}"


def verificar_token(token: str) -> dict:
    try:
        payload_b64, firma_b64 = token.split(".", 1)
        firma_esperada = hmac.new(TOKEN_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        firma_recibida = _base64url_decode(firma_b64)

        if not hmac.compare_digest(firma_esperada, firma_recibida):
            raise ValueError("firma invalida")

        payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("token expirado")

        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalido o expirado.")


def obtener_payload_autorizado(authorization: str | None, rol: str | None = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticacion requerido.")

    payload = verificar_token(authorization.replace("Bearer ", "", 1).strip())
    if rol and payload.get("rol") != rol:
        raise HTTPException(status_code=403, detail="No autorizado.")

    return payload


def obtener_id_usuario_docente(cursor, usuario: str) -> int:
    try:
        cursor.execute("SELECT id_usuario FROM usuarios WHERE username = %s LIMIT 1", (usuario,))
        fila = cursor.fetchone()
        if fila:
            return fila["id_usuario"]
    except Exception:
        pass

    return DOCENTE_DEFAULT_ID


def registrar_auditoria(
    cursor,
    evento: str,
    entidad: str | None = None,
    id_entidad: int | None = None,
    detalle: dict | None = None,
    id_usuario: int | None = None,
    request: Request | None = None
):
    try:
        ip_origen = request.client.host if request and request.client else None
        cursor.execute("""
            INSERT INTO auditoria_eventos (
                id_usuario,
                evento,
                entidad,
                id_entidad,
                detalle,
                ip_origen
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            id_usuario,
            evento,
            entidad,
            id_entidad,
            json.dumps(detalle or {}, ensure_ascii=False, default=str),
            ip_origen
        ))
    except Exception:
        # La auditoria no debe interrumpir el tramite principal.
        pass


def registrar_auditoria_login_google(evento: str, detalle: dict | None = None, request: Request | None = None):
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            registrar_auditoria(
                cursor,
                evento,
                "alumnos_snapshot",
                None,
                detalle or {},
                request=request
            )
        connection.commit()
    except Exception:
        pass
    finally:
        if connection:
            connection.close()


@app.middleware("http")
async def auditar_descargas_documentos(request: Request, call_next):
    response = await call_next(request)

    if (
        request.method == "GET"
        and response.status_code < 400
        and (
            request.url.path.startswith("/formatos/")
            or request.url.path.startswith("/archivos_expedientes/")
        )
    ):
        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                registrar_auditoria(
                    cursor,
                    "DESCARGA_DOCUMENTO",
                    "documentos",
                    None,
                    {
                        "ruta": request.url.path,
                        "archivo": os.path.basename(request.url.path),
                        "origen": "formatos" if request.url.path.startswith("/formatos/") else "archivos_expedientes"
                    },
                    request=request
                )
            connection.commit()
        except Exception:
            pass
        finally:
            if connection:
                connection.close()

    return response


def generar_codigo_expediente(codigo_alumno: str) -> str:
    return f"EXP-{codigo_alumno}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def calcular_hash_sha256(ruta_archivo: str) -> str:
    sha256 = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        for bloque in iter(lambda: f.read(4096), b""):
            sha256.update(bloque)
    return sha256.hexdigest()


def obtener_fase_por_numero(cursor, numero_fase: int):
    cursor.execute(
        "SELECT id_fase, nombre, numero_fase FROM fases WHERE numero_fase = %s AND activo = TRUE",
        (numero_fase,)
    )
    fase = cursor.fetchone()

    if not fase:
        raise HTTPException(status_code=404, detail=f"No existe la Fase {numero_fase}.")

    return fase


def obtener_expediente_por_codigo(cursor, codigo_alumno: str):
    cursor.execute("""
        SELECT 
            e.id_expediente,
            e.codigo_expediente,
            e.id_alumno,
            e.id_departamento,
            e.id_fase_actual,
            e.estado_general,
            a.codigo_alumno,
            a.nombres,
            a.apellidos
        FROM expedientes_practica e
        JOIN alumnos_snapshot a ON a.id_alumno = e.id_alumno
        WHERE a.codigo_alumno = %s
        ORDER BY e.id_expediente DESC
        LIMIT 1
    """, (codigo_alumno,))

    return cursor.fetchone()


def obtener_convocatoria_activa(cursor):
    cursor.execute("""
        SELECT id_convocatoria, nombre, fecha_inicio, fecha_fin, activo
        FROM convocatorias
        WHERE activo = 1
        ORDER BY id_convocatoria DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def convocatoria_acepta_registros(convocatoria) -> bool:
    if not convocatoria:
        return False

    ahora = datetime.now()
    fecha_inicio = convocatoria.get("fecha_inicio")
    fecha_fin = convocatoria.get("fecha_fin")

    if fecha_inicio and fecha_inicio > ahora:
        return False
    if fecha_fin and fecha_fin < ahora:
        return False
    return True

def alumno_cumple_creditos(creditos_aprobados) -> bool:
    if creditos_aprobados is None:
        return False

    return int(creditos_aprobados) > 160


def validar_alumno_fuente_apto(alumno: dict):
    if not alumno.get("activo"):
        raise HTTPException(
            status_code=400,
            detail="El alumno no se encuentra activo en la fuente academica."
        )

    if alumno["estado_matricula"] != "MATRICULADO":
        raise HTTPException(
            status_code=400,
            detail="El alumno no figura como matriculado."
        )

    if not alumno.get("id_departamento") or not alumno.get("departamento"):
        raise HTTPException(
            status_code=400,
            detail="El alumno no tiene un departamento academico valido."
        )

    if not alumno_cumple_creditos(alumno["creditos_aprobados"]):
        raise HTTPException(
            status_code=400,
            detail=f"El alumno cuenta con {alumno['creditos_aprobados']} creditos. El requisito es tener mas de 160 creditos aprobados."
        )


def obtener_alumno_fuente_validado(cursor, codigo_alumno: str):
    cursor.execute("""
        SELECT 
            a.codigo_alumno,
            a.apellido_paterno,
            a.apellido_materno,
            a.nombres,
            a.creditos_aprobados,
            a.id_departamento,
            a.estado_matricula,
            a.activo,
            d.nombre AS departamento
        FROM alumnos_fuente_prueba a
        JOIN departamentos d ON d.id_departamento = a.id_departamento
        WHERE a.codigo_alumno = %s
        LIMIT 1
    """, (codigo_alumno,))

    alumno = cursor.fetchone()

    if not alumno:
        raise HTTPException(
            status_code=404,
            detail="No se encontro informacion academica para el codigo ingresado."
        )

    validar_alumno_fuente_apto(alumno)
    return alumno


def tabla_columna_existe(cursor, tabla: str, columna: str) -> bool:
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (tabla, columna))
    resultado = cursor.fetchone()
    return bool(resultado and resultado["total"])


def obtener_alumno_fuente_por_correo_validado(cursor, correo_institucional: str):
    if not tabla_columna_existe(cursor, "alumnos_fuente_prueba", "correo_institucional"):
        raise HTTPException(
            status_code=500,
            detail=(
                "Falta la columna correo_institucional en alumnos_fuente_prueba. "
                "Sugerencia: ALTER TABLE alumnos_fuente_prueba "
                "ADD COLUMN correo_institucional VARCHAR(150) NULL UNIQUE;"
            )
        )

    cursor.execute("""
        SELECT 
            a.codigo_alumno,
            a.apellido_paterno,
            a.apellido_materno,
            a.nombres,
            a.creditos_aprobados,
            a.id_departamento,
            a.estado_matricula,
            a.activo,
            a.correo_institucional,
            d.nombre AS departamento
        FROM alumnos_fuente_prueba a
        JOIN departamentos d ON d.id_departamento = a.id_departamento
        WHERE LOWER(a.correo_institucional) = LOWER(%s)
        LIMIT 1
    """, (correo_institucional,))

    alumno = cursor.fetchone()
    if not alumno:
        raise HTTPException(
            status_code=404,
            detail="No se encontro informacion academica para el correo institucional autenticado."
        )

    validar_alumno_fuente_apto(alumno)
    return alumno


def sincronizar_alumno_snapshot(cursor, alumno: dict):
    apellidos = f"{alumno['apellido_paterno']} {alumno['apellido_materno']}".strip()

    cursor.execute("""
        INSERT INTO alumnos_snapshot (
            codigo_alumno,
            nombres,
            apellidos,
            id_departamento,
            creditos_aprobados,
            estado_matricula,
            cumple_requisitos,
            fuente_datos
        )
        VALUES (%s, %s, %s, %s, %s, %s, TRUE, 'ALUMNOS_FUENTE_PRUEBA')
        ON DUPLICATE KEY UPDATE
            nombres = VALUES(nombres),
            apellidos = VALUES(apellidos),
            id_departamento = VALUES(id_departamento),
            creditos_aprobados = VALUES(creditos_aprobados),
            estado_matricula = VALUES(estado_matricula),
            cumple_requisitos = TRUE,
            fuente_datos = 'ALUMNOS_FUENTE_PRUEBA',
            fecha_validacion = CURRENT_TIMESTAMP
    """, (
        alumno["codigo_alumno"],
        alumno["nombres"],
        apellidos,
        alumno["id_departamento"],
        alumno["creditos_aprobados"],
        alumno["estado_matricula"]
    ))

    cursor.execute("""
        SELECT
            s.id_alumno,
            s.codigo_alumno,
            s.nombres,
            s.apellidos,
            s.creditos_aprobados,
            s.id_departamento,
            s.estado_matricula,
            s.cumple_requisitos,
            d.nombre AS departamento
        FROM alumnos_snapshot s
        JOIN departamentos d ON d.id_departamento = s.id_departamento
        WHERE s.codigo_alumno = %s
        LIMIT 1
    """, (alumno["codigo_alumno"],))

    return cursor.fetchone()


def asegurar_expediente_alumno(cursor, request: Request, alumno: dict, id_alumno: int, convocatoria: dict):
    cursor.execute("""
        SELECT id_expediente, estado_general
        FROM expedientes_practica
        WHERE id_alumno = %s
          AND id_convocatoria = %s
        ORDER BY id_expediente DESC
        LIMIT 1
    """, (id_alumno, convocatoria["id_convocatoria"]))
    expediente = cursor.fetchone()

    if expediente:
        return expediente

    cursor.execute("""
        SELECT id_expediente, estado_general
        FROM expedientes_practica
        WHERE id_alumno = %s
        ORDER BY id_expediente DESC
        LIMIT 1
    """, (id_alumno,))
    expediente_anterior = cursor.fetchone()

    if expediente_anterior and expediente_anterior["estado_general"] == "FINALIZADO":
        return expediente_anterior

    if not convocatoria_acepta_registros(convocatoria):
        raise HTTPException(
            status_code=403,
            detail="El registro de nuevos alumnos para esta convocatoria ya cerro. Solo pueden ingresar alumnos registrados previamente."
        )

    fase1 = obtener_fase_por_numero(cursor, 1)
    codigo_expediente = generar_codigo_expediente(alumno["codigo_alumno"])

    cursor.execute("""
        INSERT INTO expedientes_practica (
            codigo_expediente,
            id_alumno,
            id_departamento,
            id_convocatoria,
            id_fase_actual,
            estado_general,
            creditos_al_inicio
        )
        VALUES (%s, %s, %s, %s, %s, 'INICIADO', %s)
    """, (
        codigo_expediente,
        id_alumno,
        alumno["id_departamento"],
        convocatoria["id_convocatoria"],
        fase1["id_fase"],
        alumno["creditos_aprobados"]
    ))

    id_expediente = cursor.lastrowid

    cursor.execute("SELECT id_fase, numero_fase FROM fases WHERE activo = TRUE ORDER BY numero_fase")
    fases = cursor.fetchall()

    for fase in fases:
        estado = "DISPONIBLE" if fase["numero_fase"] == 1 else "BLOQUEADA"

        if fase["numero_fase"] == 1:
            cursor.execute("""
                INSERT INTO expediente_fases (
                    id_expediente,
                    id_fase,
                    estado_fase,
                    fecha_habilitada
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (id_expediente, fase["id_fase"], estado))
        else:
            cursor.execute("""
                INSERT INTO expediente_fases (
                    id_expediente,
                    id_fase,
                    estado_fase
                )
                VALUES (%s, %s, %s)
            """, (id_expediente, fase["id_fase"], estado))

    cursor.execute("""
        INSERT INTO historial_expediente (
            id_expediente,
            accion,
            descripcion,
            estado_nuevo
        )
        VALUES (%s, 'CREACION_EXPEDIENTE', %s, 'INICIADO')
    """, (
        id_expediente,
        f"Expediente creado para el alumno {alumno['codigo_alumno']}."
    ))

    registrar_auditoria(
        cursor,
        "EXPEDIENTE_CREADO",
        "expedientes_practica",
        id_expediente,
        {
            "codigo_alumno": alumno["codigo_alumno"],
            "id_convocatoria": convocatoria["id_convocatoria"],
            "codigo_expediente": codigo_expediente
        },
        request=request
    )

    return {"id_expediente": id_expediente, "estado_general": "INICIADO"}


def obtener_orden_documento_expediente(nombre_archivo: str):
    
    nombre = nombre_archivo.lower()

    if "formato7" in nombre or "formato_7" in nombre or "formato vii" in nombre:
        return 1

    if "formato1" in nombre or "formato_1" in nombre or "formato i" in nombre:
        return 2

    if "formato2" in nombre or "formato_2" in nombre or "formato ii" in nombre:
        return 3

    if "formato3" in nombre or "formato_3" in nombre or "formato iii" in nombre:
        return 4

    if "convenio" in nombre or "contrato" in nombre:
        return 5

    if "constancia" in nombre or "certificado" in nombre:
        return 6

    if "formato4" in nombre or "formato_4" in nombre or "formato iv" in nombre:
        return 7

    if "formato5" in nombre or "formato_5" in nombre or "formato v" in nombre:
        return 8

    if "declaracion" in nombre or "declaración" in nombre or "jurada" in nombre or "ddjj" in nombre:
        return 9

    return None

def normalizar_texto_archivo(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = texto.lower()
    return re.sub(r"[^a-z0-9]+", " ", texto)


def obtener_orden_documento_expediente(nombre_archivo: str):
    nombre = normalizar_texto_archivo(nombre_archivo)

    patrones_formato = {
        1: r"\bformato\s*(7|vii)\b",
        2: r"\bformato\s*(1|i)\b",
        3: r"\bformato\s*(2|ii)\b",
        4: r"\bformato\s*(3|iii)\b",
        7: r"\bformato\s*(4|iv)\b",
        8: r"\bformato\s*(5|v)\b",
    }

    for orden, patron in patrones_formato.items():
        if re.search(patron, nombre):
            return orden

    if re.search(r"\b(convenio|contrato)\b", nombre):
        return 5

    if re.search(r"\b(constancia|certificado)\b", nombre):
        return 6

    if re.search(r"\b(declaracion|jurada|ddjj)\b", nombre):
        return 9

    return None

def es_pdf_valido(nombre_archivo: str) -> bool:
    if not nombre_archivo:
        return False

    return nombre_archivo.lower().endswith(".pdf")

def convocatoria_esta_abierta(convocatoria, fecha_actual=None) -> bool:
    if not convocatoria:
        return False

    if fecha_actual is None:
        fecha_actual = datetime.now()

    activo = convocatoria.get("activo")
    fecha_inicio = convocatoria.get("fecha_inicio")
    fecha_fin = convocatoria.get("fecha_fin")

    if not activo:
        return False

    if fecha_inicio and fecha_actual < fecha_inicio:
        return False

    if fecha_fin and fecha_actual > fecha_fin:
        return False

    return True

def expediente_permite_creacion(expediente) -> bool:
    """
    Devuelve False si el alumno ya tiene expediente FINALIZADO.
    Devuelve True si no tiene expediente o si el expediente aún no está finalizado.
    """

    if not expediente:
        return True

    return expediente.get("estado_general") != "FINALIZADO"

def expediente_tiene_documentos_completos(ordenes_documentos) -> bool:
    """
    Valida que existan los 9 documentos obligatorios del expediente.
    Recibe una lista de órdenes encontrados: [1,2,3,4,5,6,7,8,9]
    """

    ordenes_requeridos = set(range(1, 10))
    ordenes_encontrados = set(ordenes_documentos)

    return ordenes_requeridos.issubset(ordenes_encontrados)


@app.get("/api/departamentos")
async def listar_departamentos():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id_departamento, codigo, nombre
                FROM departamentos
                WHERE activo = 1
                ORDER BY nombre
            """)
            departamentos = cursor.fetchall()
        connection.close()
        return departamentos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar departamentos: {str(e)}")


@app.post("/api/registro/alumno")
@limiter.limit("5/minute")
async def registrar_alumno(
    request: Request,
    nombres: str = Form(...),
    apellidos: str = Form(...),
    codigo_alumno: str = Form(...),
    id_departamento: int = Form(...)
):
    try:
        codigo_limpio = codigo_alumno.strip()
        nombres_limpio = nombres.strip()
        apellidos_limpio = apellidos.strip()

        connection = get_db_connection()

        with connection.cursor() as cursor:
            alumno = obtener_alumno_fuente_validado(cursor, codigo_limpio)

            if alumno["id_departamento"] != id_departamento:
                raise HTTPException(
                    status_code=400,
                    detail="El departamento seleccionado no coincide con la informacion academica del codigo ingresado."
                )

            convocatoria = obtener_convocatoria_activa(cursor)
            if not convocatoria:
                raise HTTPException(
                    status_code=403,
                    detail="El sistema esta cerrado. No hay una convocatoria activa disponible."
                )

            if not convocatoria_acepta_registros(convocatoria):
                raise HTTPException(
                    status_code=403,
                    detail="El registro de nuevos alumnos para esta convocatoria ya cerro."
                )

            cursor.execute("""
                INSERT INTO alumnos_snapshot (
                    codigo_alumno,
                    nombres,
                    apellidos,
                    id_departamento,
                    creditos_aprobados,
                    estado_matricula,
                    cumple_requisitos,
                    fuente_datos
                )
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, 'ALUMNOS_FUENTE_PRUEBA')
                ON DUPLICATE KEY UPDATE
                    nombres = VALUES(nombres),
                    apellidos = VALUES(apellidos),
                    id_departamento = VALUES(id_departamento),
                    creditos_aprobados = VALUES(creditos_aprobados),
                    estado_matricula = VALUES(estado_matricula),
                    cumple_requisitos = TRUE,
                    fuente_datos = 'ALUMNOS_FUENTE_PRUEBA',
                    fecha_validacion = CURRENT_TIMESTAMP
            """, (
                codigo_limpio,
                nombres_limpio,
                apellidos_limpio,
                alumno["id_departamento"],
                alumno["creditos_aprobados"],
                alumno["estado_matricula"]
            ))

            cursor.execute("""
                SELECT id_alumno
                FROM alumnos_snapshot
                WHERE codigo_alumno = %s
            """, (codigo_limpio,))
            alumno_snapshot = cursor.fetchone()
            id_alumno = alumno_snapshot["id_alumno"]

            expediente = asegurar_expediente_alumno(cursor, request, alumno, id_alumno, convocatoria)

            registrar_auditoria(
                cursor,
                "REGISTRO_ALUMNO",
                "alumnos_snapshot",
                id_alumno,
                {
                    "codigo_alumno": codigo_limpio,
                    "id_convocatoria": convocatoria["id_convocatoria"],
                    "id_expediente": expediente["id_expediente"]
                },
                request=request
            )

            connection.commit()

        connection.close()

        return {
            "status": "success",
            "codigo_alumno": codigo_limpio,
            "nombre": f"{nombres_limpio} {apellidos_limpio}",
            "departamento": alumno["departamento"],
            "creditos": alumno["creditos_aprobados"],
            "access_token": crear_token({
                "rol": "alumno",
                "codigo_alumno": codigo_limpio,
            }),
            "token_type": "bearer"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar alumno: {str(e)}")


@app.post("/api/login/alumno")
@limiter.limit("5/minute")
async def login_alumno(request: Request, codigo_alumno: str = Form(...), password: str = Form(...)):
    raise HTTPException(
        status_code=410,
        detail="El ingreso de alumnos con codigo y contrasena ya no esta habilitado. Use Google institucional."
    )


def google_oauth_configurado() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and SESSION_SECRET_KEY)


def correo_tiene_dominio_permitido(email: str) -> bool:
    dominio = DOMINIO_CORREO_PERMITIDO
    if not dominio.startswith("@"):
        dominio = f"@{dominio}"
    return email.lower().endswith(dominio)


def construir_respuesta_sesion_alumno(alumno_registrado: dict, alumno_fuente: dict, expediente: dict) -> dict:
    status = "finalizado" if expediente["estado_general"] == "FINALIZADO" else "success"
    return {
        "status": status,
        "codigo_alumno": alumno_registrado["codigo_alumno"],
        "nombre": f"{alumno_registrado['nombres']} {alumno_registrado['apellidos']}",
        "departamento": alumno_registrado["departamento"],
        "creditos": alumno_fuente["creditos_aprobados"],
        "access_token": crear_token({
            "rol": "alumno",
            "codigo_alumno": alumno_registrado["codigo_alumno"],
        }),
        "token_type": "bearer"
    }


def frontend_index_con_login_error(codigo_error: str) -> str:
    separador = "&" if "?" in FRONTEND_INDEX_URL else "?"
    return f"{FRONTEND_INDEX_URL}{separador}login={codigo_error}"


@app.get("/api/auth/google/login")
async def login_google_alumno(request: Request):
    if not google_oauth_configurado():
        registrar_auditoria_login_google(
            "LOGIN_GOOGLE_ERROR",
            {"motivo": "oauth_google_no_configurado"},
            request=request
        )
        raise HTTPException(status_code=500, detail="Google OAuth no esta configurado.")

    redirect_uri = GOOGLE_REDIRECT_URI or str(request.url_for("callback_google_alumno"))
    try:
        return await asyncio.wait_for(
            oauth.google.authorize_redirect(request, redirect_uri),
            timeout=GOOGLE_OAUTH_TIMEOUT_SECONDS
        )
    except TimeoutError:
        registrar_auditoria_login_google(
            "LOGIN_GOOGLE_ERROR",
            {"motivo": "timeout_google_authorize_redirect"},
            request=request
        )
        raise HTTPException(status_code=504, detail="Google no respondio a tiempo. Revise salida HTTPS desde el servidor.")


@app.get("/api/auth/google/callback")
async def callback_google_alumno(request: Request):
    if not google_oauth_configurado():
        registrar_auditoria_login_google(
            "LOGIN_GOOGLE_ERROR",
            {"motivo": "oauth_google_no_configurado"},
            request=request
        )
        raise HTTPException(status_code=500, detail="Google OAuth no esta configurado.")

    connection = None
    email = None

    try:
        token = await asyncio.wait_for(
            oauth.google.authorize_access_token(request),
            timeout=GOOGLE_OAUTH_TIMEOUT_SECONDS
        )
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = await asyncio.wait_for(
                oauth.google.userinfo(token=token),
                timeout=GOOGLE_OAUTH_TIMEOUT_SECONDS
            )

        email = (userinfo.get("email") or "").strip().lower()
        email_verified = userinfo.get("email_verified", True)

        if not email or not email_verified:
            registrar_auditoria_login_google(
                "LOGIN_GOOGLE_ERROR",
                {"motivo": "correo_no_verificado_o_ausente"},
                request=request
            )
            return RedirectResponse(url=frontend_index_con_login_error("google_error"), status_code=303)

        if not correo_tiene_dominio_permitido(email):
            registrar_auditoria_login_google(
                "LOGIN_GOOGLE_DOMINIO_INVALIDO",
                {"dominio_permitido": DOMINIO_CORREO_PERMITIDO},
                request=request
            )
            return RedirectResponse(url=frontend_index_con_login_error("dominio_invalido"), status_code=303)

        connection = get_db_connection()

        with connection.cursor() as cursor:
            try:
                alumno_fuente = obtener_alumno_fuente_por_correo_validado(cursor, email)
            except HTTPException as he:
                if he.status_code >= 500:
                    raise he

                evento = "LOGIN_GOOGLE_ALUMNO_NO_ENCONTRADO" if he.status_code == 404 else "LOGIN_GOOGLE_ALUMNO_NO_APTO"
                registrar_auditoria(
                    cursor,
                    evento,
                    "alumnos_snapshot",
                    None,
                    {
                        "motivo": he.detail,
                        "correo_hash": hashlib.sha256(email.encode("utf-8")).hexdigest()
                    },
                    request=request
                )
                connection.commit()
                return RedirectResponse(url=frontend_index_con_login_error("alumno_no_apto"), status_code=303)

            convocatoria = obtener_convocatoria_activa(cursor)
            if not convocatoria:
                registrar_auditoria(
                    cursor,
                    "LOGIN_GOOGLE_ALUMNO_NO_APTO",
                    "alumnos_snapshot",
                    None,
                    {
                        "motivo": "sin_convocatoria_activa",
                        "codigo_alumno": alumno_fuente["codigo_alumno"]
                    },
                    request=request
                )
                connection.commit()
                return RedirectResponse(url=frontend_index_con_login_error("convocatoria_cerrada"), status_code=303)

            alumno_registrado = sincronizar_alumno_snapshot(cursor, alumno_fuente)
            try:
                expediente = asegurar_expediente_alumno(
                    cursor,
                    request,
                    alumno_fuente,
                    alumno_registrado["id_alumno"],
                    convocatoria
                )
            except HTTPException as he:
                registrar_auditoria(
                    cursor,
                    "LOGIN_GOOGLE_ALUMNO_NO_APTO",
                    "alumnos_snapshot",
                    alumno_registrado["id_alumno"],
                    {
                        "motivo": he.detail,
                        "codigo_alumno": alumno_registrado["codigo_alumno"],
                        "id_convocatoria": convocatoria["id_convocatoria"]
                    },
                    request=request
                )
                connection.commit()
                return RedirectResponse(url=frontend_index_con_login_error("alumno_no_apto"), status_code=303)

            sesion_alumno = construir_respuesta_sesion_alumno(alumno_registrado, alumno_fuente, expediente)
            request.session["alumno"] = {
                "codigo_alumno": sesion_alumno["codigo_alumno"],
                "nombre": sesion_alumno["nombre"],
                "access_token": sesion_alumno["access_token"],
                "token_type": sesion_alumno["token_type"],
                "estado_expediente": expediente["estado_general"],
            }

            registrar_auditoria(
                cursor,
                "LOGIN_GOOGLE_ALUMNO_OK",
                "alumnos_snapshot",
                alumno_registrado["id_alumno"],
                {
                    "codigo_alumno": alumno_registrado["codigo_alumno"],
                    "id_convocatoria": convocatoria["id_convocatoria"],
                    "id_expediente": expediente["id_expediente"]
                },
                request=request
            )

            connection.commit()

        return RedirectResponse(url=ALUMNO_FRONTEND_URL, status_code=303)

    except OAuthError:
        registrar_auditoria_login_google(
            "LOGIN_GOOGLE_ERROR",
            {"motivo": "oauth_error"},
            request=request
        )
        return RedirectResponse(url=frontend_index_con_login_error("google_error"), status_code=303)
    except TimeoutError:
        registrar_auditoria_login_google(
            "LOGIN_GOOGLE_ERROR",
            {"motivo": "timeout_google_callback"},
            request=request
        )
        return RedirectResponse(url=frontend_index_con_login_error("google_error"), status_code=303)
    except Exception as e:
        if connection:
            try:
                with connection.cursor() as cursor:
                    registrar_auditoria(
                        cursor,
                        "LOGIN_GOOGLE_ERROR",
                        "alumnos_snapshot",
                        None,
                        {"correo_hash": hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None},
                        request=request
                    )
                connection.commit()
            except Exception:
                pass
        else:
            registrar_auditoria_login_google(
                "LOGIN_GOOGLE_ERROR",
                {"correo_hash": hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None},
                request=request
            )
        return RedirectResponse(url=frontend_index_con_login_error("google_error"), status_code=303)
    finally:
        if connection:
            connection.close()


@app.get("/api/auth/google/session")
async def obtener_sesion_google_alumno(request: Request):
    alumno = request.session.get("alumno")
    if not alumno:
        raise HTTPException(status_code=401, detail="No existe una sesion Google de alumno activa.")

    return {
        "status": "success",
        "codigo_alumno": alumno["codigo_alumno"],
        "nombre": alumno["nombre"],
        "access_token": alumno["access_token"],
        "token_type": alumno["token_type"],
    }


@app.post("/api/login/docente")
@limiter.limit("5/minute")
async def login_docente(request: Request, usuario: str = Form(...), password: str = Form(...)):
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id_usuario, username
                FROM usuarios
                WHERE username = %s
                  AND password_hash = SHA2(%s, 256)
                  AND activo = 1
                LIMIT 1
            """, (usuario, password))
            docente = cursor.fetchone()

            if docente:
                registrar_auditoria(
                    cursor,
                    "LOGIN_DOCENTE_OK",
                    "usuarios",
                    docente["id_usuario"],
                    {"usuario": usuario},
                    id_usuario=docente["id_usuario"],
                    request=request
                )
            else:
                registrar_auditoria(
                    cursor,
                    "LOGIN_DOCENTE_FALLIDO",
                    "usuarios",
                    None,
                    {"usuario": usuario},
                    request=request
                )
            connection.commit()
        connection.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al autenticar: {str(e)}")

    if not docente:
        raise HTTPException(status_code=401, detail="Usuario o clave incorrectos")

    return {
        "status": "success",
        "message": "Autenticado",
        "usuario": docente["username"],
        "access_token": crear_token({
            "rol": "docente",
            "usuario": docente["username"],
            "id_usuario": docente["id_usuario"],
        }),
        "token_type": "bearer"
    }


@app.get("/api/alumno/estado/{codigo_alumno}")
async def obtener_estado_alumno(codigo_alumno: str):
    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            expediente = obtener_expediente_por_codigo(cursor, codigo_alumno)

            if not expediente:
                return {
                    "fase1_estado": "bloqueado",
                    "fase2_estado": "bloqueado",
                    "fase3_estado": "bloqueado"
                }

            cursor.execute("""
                SELECT 
                    f.numero_fase,
                    ef.estado_fase
                FROM expediente_fases ef
                JOIN fases f ON f.id_fase = ef.id_fase
                WHERE ef.id_expediente = %s
                ORDER BY f.numero_fase
            """, (expediente["id_expediente"],))

            fases = cursor.fetchall()

        connection.close()

        # Adaptación para que tu alumno.html actual siga funcionando
        estados = {
            "fase1_estado": "bloqueado",
            "fase2_estado": "bloqueado",
            "fase3_estado": "bloqueado"
        }

        mapa_estados = {
            "BLOQUEADA": "bloqueado",
            "DISPONIBLE": "no-enviado",
            "EN_CARGA": "pendiente",
            "EN_REVISION": "pendiente",
            "OBSERVADA": "observado",
            "EN_SUBSANACION": "observado",
            "APROBADA": "aprobado",
            "RECHAZADA": "observado",
            "VENCIDA": "observado",
            "HABILITADA_POR_EXCEPCION": "no-enviado"
        }

        for fase in fases:
            key = f"fase{fase['numero_fase']}_estado"
            estados[key] = mapa_estados.get(fase["estado_fase"], "bloqueado")

        return estados

    except Exception:
        return {
            "fase1_estado": "bloqueado",
            "fase2_estado": "bloqueado",
            "fase3_estado": "bloqueado"
        }

@app.post("/api/subir-fase/{numero_fase}")
async def subir_documentos_fase(
    request: Request,
    numero_fase: int,
    codigo_alumno: str = Form(...),
    archivos: List[UploadFile] = File(...)
):
    if numero_fase not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Fase inválida.")

    for archivo in archivos:
        if not es_pdf_valido(archivo.filename):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo '{archivo.filename}' no es un PDF válido."
            )

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            expediente = obtener_expediente_por_codigo(cursor, codigo_alumno)

            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente para el alumno.")

            fase = obtener_fase_por_numero(cursor, numero_fase)

            # Verificar que la fase esté disponible, observada o en subsanación
            cursor.execute("""
                SELECT estado_fase
                FROM expediente_fases
                WHERE id_expediente = %s
                  AND id_fase = %s
            """, (expediente["id_expediente"], fase["id_fase"]))

            expediente_fase = cursor.fetchone()

            if not expediente_fase:
                raise HTTPException(status_code=404, detail="La fase no existe en el expediente.")

            if expediente_fase["estado_fase"] == "BLOQUEADA":
                raise HTTPException(status_code=400, detail="Esta fase aún está bloqueada.")

            if expediente_fase["estado_fase"] == "APROBADA":
                raise HTTPException(status_code=400, detail="Esta fase ya fue aprobada.")
            
            documentos_reemplazados = 0
            if expediente_fase["estado_fase"] in ["OBSERVADA", "EN_SUBSANACION"]:
                cursor.execute("""
                    UPDATE documentos_expediente
                    SET estado_documento = 'REEMPLAZADO'
                    WHERE id_expediente = %s
                        AND id_fase = %s
                        AND estado_documento = 'OBSERVADO'
                """, (
                    expediente["id_expediente"],
                    fase["id_fase"]
                ))
                documentos_reemplazados = cursor.rowcount

                cursor.execute("""
                    UPDATE observaciones_documento
                    SET estado_observacion = 'CERRADA'
                    WHERE id_expediente = %s
                        AND id_fase = %s
                        AND estado_observacion = 'ABIERTA'
                """, (
                    expediente["id_expediente"],
                    fase["id_fase"]
                ))

            carpeta_alumno = os.path.join(UPLOAD_DIR, codigo_alumno, f"fase_{numero_fase}")
            os.makedirs(carpeta_alumno, exist_ok=True)

            documentos_guardados = []

            for idx, archivo in enumerate(archivos):
                nombre_limpio = archivo.filename.replace(" ", "_")
                nombre_final = f"fase{numero_fase}_{codigo_alumno}_{nombre_limpio}"
                ruta_final = os.path.join(carpeta_alumno, nombre_final)

                contenido = await archivo.read()

                with open(ruta_final, "wb") as f:
                    f.write(contenido)

                hash_archivo = calcular_hash_sha256(ruta_final)

                cursor.execute("""
                    INSERT INTO documentos_expediente (
                        id_expediente,
                        id_fase,
                        id_documento_requerido,
                        nombre_original,
                        nombre_guardado,
                        ruta_archivo,
                        mime_type,
                        tamanio_bytes,
                        hash_archivo,
                        estado_documento
                    )
                    VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, 'EN_REVISION')
                """, (
                    expediente["id_expediente"],
                    fase["id_fase"],
                    archivo.filename,
                    nombre_final,
                    ruta_final,
                    archivo.content_type or "application/pdf",
                    len(contenido),
                    hash_archivo
                ))

                documentos_guardados.append(nombre_final)

            # Cambiar estado de fase a EN_REVISION
            cursor.execute("""
                UPDATE expediente_fases
                SET estado_fase = 'EN_REVISION',
                    fecha_envio = CURRENT_TIMESTAMP
                WHERE id_expediente = %s
                  AND id_fase = %s
            """, (expediente["id_expediente"], fase["id_fase"]))

            cursor.execute("""
                UPDATE expedientes_practica
                SET estado_general = 'EN_PROCESO',
                    id_fase_actual = %s
                WHERE id_expediente = %s
            """, (fase["id_fase"], expediente["id_expediente"]))

            cursor.execute("""
                INSERT INTO historial_expediente (
                    id_expediente,
                    accion,
                    descripcion,
                    estado_nuevo
                )
                VALUES (%s, 'SUBIDA_DOCUMENTOS', %s, 'EN_REVISION')
            """, (
                expediente["id_expediente"],
                f"El alumno subió {len(archivos)} documento(s) para la Fase {numero_fase}."
            ))

            registrar_auditoria(
                cursor,
                "DOCUMENTOS_SUBIDOS",
                "expedientes_practica",
                expediente["id_expediente"],
                {
                    "codigo_alumno": codigo_alumno,
                    "fase": numero_fase,
                    "cantidad_archivos": len(archivos),
                    "archivos": documentos_guardados
                },
                request=request
            )

            if documentos_reemplazados:
                registrar_auditoria(
                    cursor,
                    "DOCUMENTO_REEMPLAZADO",
                    "expedientes_practica",
                    expediente["id_expediente"],
                    {
                        "codigo_alumno": codigo_alumno,
                        "fase": numero_fase,
                        "cantidad_reemplazada": documentos_reemplazados,
                        "archivos_nuevos": documentos_guardados
                    },
                    request=request
                )

            connection.commit()

        connection.close()

        return {
            "status": "success",
            "message": f"{len(archivos)} archivo(s) subidos correctamente para la Fase {numero_fase}.",
            "archivos": documentos_guardados
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar los archivos: {str(e)}")


@app.post("/api/subir-fase1")
async def subir_fase1(request: Request, codigo_alumno: str = Form(...), archivos: List[UploadFile] = File(...)):
    return await subir_documentos_fase(request, 1, codigo_alumno, archivos)


@app.post("/api/subir-fase2")
async def subir_fase2(request: Request, codigo_alumno: str = Form(...), archivos: List[UploadFile] = File(...)):
    return await subir_documentos_fase(request, 2, codigo_alumno, archivos)


@app.post("/api/subir-fase3")
async def subir_fase3(request: Request, codigo_alumno: str = Form(...), archivos: List[UploadFile] = File(...)):
    return await subir_documentos_fase(request, 3, codigo_alumno, archivos)

@app.get("/api/alumno/observaciones/{codigo_alumno}")
async def obtener_observaciones_alumno(codigo_alumno: str):
    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            expediente = obtener_expediente_por_codigo(cursor, codigo_alumno)

            if not expediente:
                return []

            cursor.execute("""
                SELECT
                    f.numero_fase,
                    de.nombre_original,
                    de.nombre_guardado,
                    od.mensaje,
                    od.estado_observacion
                FROM observaciones_documento od
                JOIN documentos_expediente de ON de.id_documento = od.id_documento
                JOIN fases f ON f.id_fase = od.id_fase
                WHERE od.id_expediente = %s
                  AND od.estado_observacion = 'ABIERTA'
                ORDER BY f.numero_fase
            """, (expediente["id_expediente"],))

            observaciones = cursor.fetchall()

        connection.close()
        return observaciones

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener observaciones: {str(e)}")

@app.get("/api/docente/expedientes")
async def listar_expedientes(
    id_convocatoria: int | None = None,
    authorization: str | None = Header(None)
):
    obtener_payload_autorizado(authorization, "docente")

    if not id_convocatoria:
        return []

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    e.id_expediente,
                    e.codigo_expediente,
                    e.estado_general,
                    e.creado_en,
                    e.id_convocatoria,
                    c.nombre AS convocatoria,
                    a.codigo_alumno,
                    a.nombres,
                    a.apellidos,
                    a.creditos_aprobados,
                    d.nombre AS departamento,
                    MAX(CASE WHEN f.numero_fase = 1 THEN ef.estado_fase END) AS fase1_estado_bd,
                    MAX(CASE WHEN f.numero_fase = 2 THEN ef.estado_fase END) AS fase2_estado_bd,
                    MAX(CASE WHEN f.numero_fase = 3 THEN ef.estado_fase END) AS fase3_estado_bd
                FROM expedientes_practica e
                JOIN convocatorias c ON c.id_convocatoria = e.id_convocatoria
                JOIN alumnos_snapshot a ON a.id_alumno = e.id_alumno
                JOIN departamentos d ON d.id_departamento = e.id_departamento
                JOIN expediente_fases ef ON ef.id_expediente = e.id_expediente
                JOIN fases f ON f.id_fase = ef.id_fase
                WHERE e.id_convocatoria = %s
                GROUP BY 
                    e.id_expediente,
                    e.codigo_expediente,
                    e.estado_general,
                    e.creado_en,
                    e.id_convocatoria,
                    c.nombre,
                    a.codigo_alumno,
                    a.nombres,
                    a.apellidos,
                    a.creditos_aprobados,
                    d.nombre
                ORDER BY e.creado_en DESC
            """, (id_convocatoria,))

            expedientes = cursor.fetchall()

            for exp in expedientes:
                exp["fase1_estado"] = convertir_estado_frontend(exp["fase1_estado_bd"])
                exp["fase2_estado"] = convertir_estado_frontend(exp["fase2_estado_bd"])
                exp["fase3_estado"] = convertir_estado_frontend(exp["fase3_estado_bd"])

                for numero_fase in [1, 2, 3]:
                    cursor.execute("""
                        SELECT 
                            de.id_documento,
                            de.nombre_guardado,
                            de.estado_documento
                        FROM documentos_expediente de
                        JOIN fases f ON f.id_fase = de.id_fase
                        WHERE de.id_expediente = %s
                            AND f.numero_fase = %s
                            AND de.estado_documento <> 'REEMPLAZADO'
                        ORDER BY de.subido_en ASC
                    """, (exp["id_expediente"], numero_fase))

                    archivos = cursor.fetchall()

                    exp[f"fase{numero_fase}_archivo"] = ";;".join([
                        f"{archivo['id_documento']}|{archivo['nombre_guardado']}|{archivo['estado_documento']}"
                        for archivo in archivos
                    ])

        connection.close()

        return expedientes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def convertir_estado_frontend(estado_bd: str) -> str:
    mapa = {
        "BLOQUEADA": "bloqueado",
        "DISPONIBLE": "no-enviado",
        "EN_CARGA": "pendiente",
        "EN_REVISION": "pendiente",
        "OBSERVADA": "observado",
        "EN_SUBSANACION": "observado",
        "APROBADA": "aprobado",
        "RECHAZADA": "observado",
        "VENCIDA": "observado",
        "HABILITADA_POR_EXCEPCION": "no-enviado"
    }

    return mapa.get(estado_bd, "bloqueado")


@app.post("/api/docente/documento/evaluar")
async def evaluar_documento(
    request: Request,
    id_documento: int = Form(...),
    nuevo_estado: str = Form(...),
    observacion: str = Form(None),
    authorization: str | None = Header(None)
):
    docente = obtener_payload_autorizado(authorization, "docente")
    id_usuario_docente = int(docente.get("id_usuario") or DOCENTE_DEFAULT_ID)

    if nuevo_estado not in ["VALIDO", "OBSERVADO"]:
        raise HTTPException(status_code=400, detail="Estado de documento inválido.")

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    de.id_documento,
                    de.id_expediente,
                    de.id_fase,
                    de.estado_documento
                FROM documentos_expediente de
                WHERE de.id_documento = %s
                  AND de.estado_documento <> 'REEMPLAZADO'
            """, (id_documento,))

            documento = cursor.fetchone()

            if not documento:
                raise HTTPException(status_code=404, detail="Documento no encontrado o ya fue reemplazado.")

            cursor.execute("""
                UPDATE documentos_expediente
                SET estado_documento = %s
                WHERE id_documento = %s
            """, (nuevo_estado, id_documento))

            if nuevo_estado == "OBSERVADO":
                if not observacion or not observacion.strip():
                    raise HTTPException(status_code=400, detail="Debe registrar una observacion para observar el documento.")

                cursor.execute("""
                    UPDATE expediente_fases
                    SET estado_fase = 'OBSERVADA',
                        fecha_revision = CURRENT_TIMESTAMP
                    WHERE id_expediente = %s
                      AND id_fase = %s
                """, (
                    documento["id_expediente"],
                    documento["id_fase"]
                ))

                cursor.execute("""
                    UPDATE expedientes_practica
                    SET estado_general = 'OBSERVADO'
                    WHERE id_expediente = %s
                """, (documento["id_expediente"],))

                cursor.execute("""
                    INSERT INTO observaciones_documento (
                        id_documento,
                        id_expediente,
                        id_fase,
                        id_usuario,       
                        mensaje,
                        estado_observacion
                    )
                    VALUES (%s, %s, %s, %s, %s, 'ABIERTA')
                """, (
                    id_documento,
                    documento["id_expediente"],
                    documento["id_fase"],
                    id_usuario_docente,
                    observacion.strip()
                ))

            cursor.execute("""
                INSERT INTO historial_expediente (
                    id_expediente,
                    accion,
                    descripcion,
                    estado_nuevo
                )
                VALUES (%s, 'EVALUACION_DOCUMENTO', %s, %s)
            """, (
                documento["id_expediente"],
                f"Documento {id_documento} marcado como {nuevo_estado}.",
                nuevo_estado
            ))

            registrar_auditoria(
                cursor,
                "DOCUMENTO_EVALUADO",
                "documentos_expediente",
                id_documento,
                {
                    "id_expediente": documento["id_expediente"],
                    "id_fase": documento["id_fase"],
                    "estado_anterior": documento["estado_documento"],
                    "estado_nuevo": nuevo_estado,
                    "observacion": observacion.strip() if observacion else None
                },
                id_usuario=id_usuario_docente,
                request=request
            )

            connection.commit()

        connection.close()

        return {
            "status": "success",
            "message": f"Documento actualizado a {nuevo_estado}."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al evaluar documento: {str(e)}")

@app.post("/api/docente/evaluar")
async def evaluar_fase(
    request: Request,
    codigo_alumno: str = Form(...),
    fase: int = Form(...),
    nuevo_estado: str = Form(...),
    authorization: str | None = Header(None)
):
    docente = obtener_payload_autorizado(authorization, "docente")
    id_usuario_docente = int(docente.get("id_usuario") or DOCENTE_DEFAULT_ID)

    if nuevo_estado not in ["aprobado", "observado"]:
        raise HTTPException(status_code=400, detail="Estado inválido.")

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            expediente = obtener_expediente_por_codigo(cursor, codigo_alumno)

            if not expediente:
                raise HTTPException(status_code=404, detail="No se encontró expediente del alumno.")

            fase_actual = obtener_fase_por_numero(cursor, fase)

            if nuevo_estado == "aprobado":
                estado_bd = "APROBADA"
                estado_general = "EN_PROCESO"
            else:
                estado_bd = "OBSERVADA"
                estado_general = "OBSERVADO"
            expediente_finalizado = False

            # Actualizar documentos de la fase
            if nuevo_estado == "aprobado":
                cursor.execute("""
                    UPDATE documentos_expediente
                    SET estado_documento = 'VALIDO'
                    WHERE id_expediente = %s
                      AND id_fase = %s
                      AND estado_documento <> 'REEMPLAZADO'
                """, (expediente["id_expediente"], fase_actual["id_fase"]))
            else:
                cursor.execute("""
                    UPDATE documentos_expediente
                    SET estado_documento = 'OBSERVADO'
                    WHERE id_expediente = %s
                      AND id_fase = %s
                      AND estado_documento <> 'REEMPLAZADO'
                """, (expediente["id_expediente"], fase_actual["id_fase"]))

            # Actualizar fase evaluada
            cursor.execute("""
                UPDATE expediente_fases
                SET estado_fase = %s,
                    fecha_revision = CURRENT_TIMESTAMP,
                    fecha_aprobacion = CASE WHEN %s = 'APROBADA' THEN CURRENT_TIMESTAMP ELSE fecha_aprobacion END
                WHERE id_expediente = %s
                  AND id_fase = %s
            """, (
                estado_bd,
                estado_bd,
                expediente["id_expediente"],
                fase_actual["id_fase"]
            ))

            # Si aprueba, habilitar siguiente fase
            if nuevo_estado == "aprobado":
                siguiente_numero_fase = fase + 1

                cursor.execute("""
                    SELECT id_fase
                    FROM fases
                    WHERE numero_fase = %s
                      AND activo = TRUE
                """, (siguiente_numero_fase,))

                siguiente_fase = cursor.fetchone()

                if siguiente_fase:
                    cursor.execute("""
                        UPDATE expediente_fases
                        SET estado_fase = 'DISPONIBLE',
                            fecha_habilitada = CURRENT_TIMESTAMP
                        WHERE id_expediente = %s
                          AND id_fase = %s
                          AND estado_fase = 'BLOQUEADA'
                    """, (expediente["id_expediente"], siguiente_fase["id_fase"]))

                    cursor.execute("""
                        UPDATE expedientes_practica
                        SET id_fase_actual = %s,
                            estado_general = 'EN_PROCESO'
                        WHERE id_expediente = %s
                    """, (siguiente_fase["id_fase"], expediente["id_expediente"]))
                else:
                    # Si no hay siguiente fase, finaliza expediente
                    estado_general = "FINALIZADO"
                    expediente_finalizado = True
                    cursor.execute("""
                        UPDATE expedientes_practica
                        SET estado_general = 'FINALIZADO'
                        WHERE id_expediente = %s
                    """, (expediente["id_expediente"],))
            else:
                cursor.execute("""
                    UPDATE expedientes_practica
                    SET estado_general = %s
                    WHERE id_expediente = %s
                """, (estado_general, expediente["id_expediente"]))

            cursor.execute("""
                INSERT INTO historial_expediente (
                    id_expediente,
                    accion,
                    descripcion,
                    estado_nuevo
                )
                VALUES (%s, 'EVALUACION_FASE', %s, %s)
            """, (
                expediente["id_expediente"],
                f"Fase {fase} evaluada como {nuevo_estado}.",
                estado_bd
            ))

            registrar_auditoria(
                cursor,
                "FASE_APROBADA" if nuevo_estado == "aprobado" else "FASE_OBSERVADA",
                "expedientes_practica",
                expediente["id_expediente"],
                {
                    "codigo_alumno": codigo_alumno,
                    "fase": fase,
                    "estado_nuevo": estado_bd,
                    "estado_general": estado_general
                },
                id_usuario=id_usuario_docente,
                request=request
            )

            if expediente_finalizado:
                registrar_auditoria(
                    cursor,
                    "EXPEDIENTE_FINALIZADO",
                    "expedientes_practica",
                    expediente["id_expediente"],
                    {
                        "codigo_alumno": codigo_alumno,
                        "fase_final": fase,
                        "estado_general": estado_general
                    },
                    id_usuario=id_usuario_docente,
                    request=request
                )

            connection.commit()

        connection.close()

        return {
            "status": "success",
            "message": f"Fase {fase} actualizada a {nuevo_estado}."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def normalizar_fecha_form(valor: str | None) -> str | None:
    if not valor:
        return None
    return valor.replace("T", " ")[:19]


@app.get("/api/convocatorias")
async def listar_convocatorias():
    """Devuelve todas las convocatorias ordenadas de más reciente a más antigua."""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id_convocatoria, nombre, fecha_inicio, fecha_fin, activo
                FROM convocatorias
                ORDER BY id_convocatoria DESC
            """)
            convocatorias = cursor.fetchall()
        connection.close()
 
        for c in convocatorias:
            c["fecha_inicio"] = str(c["fecha_inicio"]) if c["fecha_inicio"] else None
            c["fecha_fin"]    = str(c["fecha_fin"])    if c["fecha_fin"]    else None
 
        return convocatorias
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar convocatorias: {str(e)}")
 
 
@app.get("/api/convocatorias/activa")
async def convocatoria_activa():
    """Devuelve la convocatoria activa actual, o None si el sistema está cerrado."""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            conv = obtener_convocatoria_activa(cursor)
        connection.close()
 
        if not conv:
            return {"activa": False, "registro_abierto": False, "convocatoria": None}
 
        registro_abierto = convocatoria_acepta_registros(conv)
        conv["fecha_inicio"] = str(conv["fecha_inicio"]) if conv["fecha_inicio"] else None
        conv["fecha_fin"]    = str(conv["fecha_fin"])    if conv["fecha_fin"]    else None
        return {
            "activa": True,
            "registro_abierto": registro_abierto,
            "convocatoria": conv
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar convocatoria activa: {str(e)}")
 
 
@app.post("/api/docente/convocatorias")
async def crear_convocatoria(
    request: Request,
    nombre: str = Form(...),
    fecha_inicio: str = Form(None),
    fecha_fin: str = Form(None),
    authorization: str | None = Header(None)
):
    """Crea una nueva convocatoria(inactiva por defecto)"""
    docente = obtener_payload_autorizado(authorization, "docente")
    id_usuario_docente = int(docente.get("id_usuario") or DOCENTE_DEFAULT_ID)
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO convocatorias (nombre, fecha_inicio, fecha_fin, activo)
                VALUES (%s, %s, %s, 0)
            """, (
                nombre.strip(),
                normalizar_fecha_form(fecha_inicio),
                normalizar_fecha_form(fecha_fin)
            ))
            nuevo_id = cursor.lastrowid
            registrar_auditoria(
                cursor,
                "CONVOCATORIA_CREADA",
                "convocatorias",
                nuevo_id,
                {
                    "nombre": nombre.strip(),
                    "fecha_inicio": normalizar_fecha_form(fecha_inicio),
                    "fecha_fin": normalizar_fecha_form(fecha_fin),
                    "activo": 0
                },
                id_usuario=id_usuario_docente,
                request=request
            )
        connection.commit()
        connection.close()
        return {"status": "success", "id_convocatoria": nuevo_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear convocatoria: {str(e)}")
 
 
@app.put("/api/docente/convocatorias/{id_convocatoria}")
async def actualizar_convocatoria(
    request: Request,
    id_convocatoria: int,
    nombre: str = Form(None),
    fecha_inicio: str = Form(None),
    fecha_fin: str = Form(None),
    activo: int = Form(None),
    authorization: str | None = Header(None)
):

    docente = obtener_payload_autorizado(authorization, "docente")
    id_usuario_docente = int(docente.get("id_usuario") or DOCENTE_DEFAULT_ID)
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # Si se está activando esta convocatoria, cerrar todas las demás
            if activo == 1:
                cursor.execute("UPDATE convocatorias SET activo = 0")
 
            campos = []
            valores = []
 
            if nombre is not None:
                campos.append("nombre = %s"); valores.append(nombre.strip())
            if fecha_inicio is not None:
                campos.append("fecha_inicio = %s"); valores.append(normalizar_fecha_form(fecha_inicio))
            if fecha_fin is not None:
                campos.append("fecha_fin = %s"); valores.append(normalizar_fecha_form(fecha_fin))
            if activo is not None:
                campos.append("activo = %s"); valores.append(activo)
 
            if not campos:
                raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
 
            valores.append(id_convocatoria)
            cursor.execute(f"UPDATE convocatorias SET {', '.join(campos)} WHERE id_convocatoria = %s", valores)

            registrar_auditoria(
                cursor,
                "CONVOCATORIA_ACTUALIZADA",
                "convocatorias",
                id_convocatoria,
                {
                    "nombre": nombre.strip() if nombre is not None else None,
                    "fecha_inicio": normalizar_fecha_form(fecha_inicio) if fecha_inicio is not None else None,
                    "fecha_fin": normalizar_fecha_form(fecha_fin) if fecha_fin is not None else None,
                    "activo": activo,
                    "campos": campos
                },
                id_usuario=id_usuario_docente,
                request=request
            )
 
        connection.commit()
        connection.close()
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar convocatoria: {str(e)}")

@app.get("/api/expediente/{codigo_alumno}/pdf-completo")
async def descargar_expediente_pdf_completo(request: Request, codigo_alumno: str):
    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            # 1. Buscar expediente finalizado
            cursor.execute("""
                SELECT 
                    e.id_expediente,
                    e.codigo_expediente,
                    e.estado_general,
                    a.codigo_alumno,
                    a.nombres,
                    a.apellidos
                FROM expedientes_practica e
                JOIN alumnos_snapshot a ON a.id_alumno = e.id_alumno
                WHERE a.codigo_alumno = %s
                  AND e.estado_general = 'FINALIZADO'
                ORDER BY e.id_expediente DESC
                LIMIT 1
            """, (codigo_alumno,))

            expediente = cursor.fetchone()

            if not expediente:
                raise HTTPException(
                    status_code=404,
                    detail="El alumno no tiene un expediente finalizado."
                )

            # 2. Verificar que las 3 fases estén aprobadas
            cursor.execute("""
                SELECT COUNT(*) AS total_aprobadas
                FROM expediente_fases ef
                JOIN fases f ON f.id_fase = ef.id_fase
                WHERE ef.id_expediente = %s
                  AND f.numero_fase IN (1, 2, 3)
                  AND ef.estado_fase = 'APROBADA'
            """, (expediente["id_expediente"],))

            fases = cursor.fetchone()

            if fases["total_aprobadas"] != 3:
                raise HTTPException(
                    status_code=400,
                    detail="El expediente aún no tiene las 3 fases aprobadas."
                )

            # 3. Obtener solo documentos válidos
            cursor.execute("""
                SELECT 
                    de.id_documento,
                    de.nombre_original,
                    de.nombre_guardado,
                    de.ruta_archivo,
                    de.estado_documento,
                    f.numero_fase,
                    de.subido_en
                FROM documentos_expediente de
                JOIN fases f ON f.id_fase = de.id_fase
                WHERE de.id_expediente = %s
                  AND de.estado_documento = 'VALIDO'
                ORDER BY f.numero_fase ASC, de.subido_en ASC
            """, (expediente["id_expediente"],))

            documentos = cursor.fetchall()

        connection.close()

        if not documentos:
            raise HTTPException(
                status_code=404,
                detail="No existen documentos válidos para generar el expediente."
            )

        documentos_por_orden = {}
        documentos_sin_orden_por_fase = {1: [], 2: [], 3: []}

        for doc in documentos:
            orden = obtener_orden_documento_expediente(doc["nombre_original"])

            if orden is None:
                orden = obtener_orden_documento_expediente(doc["nombre_guardado"])

            documento_pdf = {
                "orden": orden,
                "nombre_original": doc["nombre_original"],
                "nombre_guardado": doc["nombre_guardado"],
                "ruta_archivo": doc["ruta_archivo"],
                "numero_fase": doc["numero_fase"]
            }

            if orden is not None:
                documentos_por_orden[orden] = documento_pdf
            elif doc["numero_fase"] in documentos_sin_orden_por_fase:
                documentos_sin_orden_por_fase[doc["numero_fase"]].append(documento_pdf)

        if not documentos_por_orden and not any(documentos_sin_orden_por_fase.values()):
            raise HTTPException(
                status_code=400,
                detail="No se pudo identificar el orden de los documentos válidos."
            )

        # 4. Ordenar según expediente oficial
        ordenes_por_fase = {
            1: [1, 2, 3, 4],
            2: [5, 6],
            3: [7, 8, 9]
        }

        for numero_fase, ordenes_fase in ordenes_por_fase.items():
            ordenes_faltantes_fase = [
                orden for orden in ordenes_fase
                if orden not in documentos_por_orden
            ]

            for orden, doc in zip(ordenes_faltantes_fase, documentos_sin_orden_por_fase[numero_fase]):
                doc["orden"] = orden
                documentos_por_orden[orden] = doc

        documentos_ordenados = sorted(documentos_por_orden.values(), key=lambda x: x["orden"])

        # 5. Validar si faltan documentos del orden oficial
        ordenes_encontrados = set(documentos_por_orden.keys())
        ordenes_requeridos = set(range(1, 10))

        faltantes = ordenes_requeridos - ordenes_encontrados

        if faltantes:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede generar el expediente completo. Faltan documentos del orden: {sorted(list(faltantes))}"
            )

        # 6. Crear PDF combinado
        writer = PdfWriter()

        for doc in documentos_ordenados:
            ruta = doc["ruta_archivo"]

            if not os.path.isabs(ruta):
                ruta = os.path.join(os.getcwd(), ruta)

            if not os.path.exists(ruta):
                raise HTTPException(
                    status_code=404,
                    detail=f"No se encontró el archivo físico: {doc['nombre_guardado']}"
                )

            try:
                writer.append(ruta)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"No se pudo unir el PDF {doc['nombre_guardado']}: {str(e)}"
                )

        nombre_pdf_final = f"expediente_completo_{codigo_alumno}.pdf"
        ruta_pdf_final = os.path.join(EXPEDIENTES_FINALES_DIR, nombre_pdf_final)
        os.makedirs(EXPEDIENTES_FINALES_DIR, exist_ok=True)

        with open(ruta_pdf_final, "wb") as salida:
            writer.write(salida)

        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                registrar_auditoria(
                    cursor,
                    "DESCARGA_EXPEDIENTE_COMPLETO",
                    "expedientes_practica",
                    expediente["id_expediente"],
                    {
                        "codigo_alumno": codigo_alumno,
                        "codigo_expediente": expediente["codigo_expediente"],
                        "archivo": nombre_pdf_final,
                        "cantidad_documentos": len(documentos_ordenados)
                    },
                    request=request
                )
            connection.commit()
        except Exception:
            pass
        finally:
            if connection:
                connection.close()

        return FileResponse(
            path=ruta_pdf_final,
            media_type="application/pdf",
            filename=nombre_pdf_final
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar expediente completo: {str(e)}"
        )
