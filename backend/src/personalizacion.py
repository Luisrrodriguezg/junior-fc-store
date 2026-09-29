"""Lambda jfc-personalizacion — jersey name and number, stored in RDS.

Routes (API Gateway HTTP API, payload 2.0):
  GET    /personalizaciones/opciones   public: personalizable jerseys, patches, rules
  GET    /personalizaciones            the signed-in user's personalizations
  POST   /personalizaciones            create or update one (one per user and jersey)
  DELETE /personalizaciones/{id}       delete one of the user's own

The user is always the `sub` claim of the Cognito token that API Gateway's JWT authorizer already
verified — never a value sent in the request body.
"""

import base64
import json
import logging
import time

import pymysql

from jfc import db, validacion
from jfc.respuestas import ErrorApi, error, ok

log = logging.getLogger()
log.setLevel(logging.INFO)

_SELECT = """
    SELECT p.id, p.sku, pr.nombre AS producto, pr.color1, pr.color2, p.nombre, p.numero,
           p.parche, pa.nombre AS parche_nombre, pr.precio AS precio_base, pa.precio AS precio_parche,
           p.precio_final, p.actualizado
      FROM personalizacion p
      JOIN producto pr ON pr.sku = p.sku
      JOIN parche pa ON pa.codigo = p.parche
"""

# Blocked words change rarely; a warm container re-reads them every 5 minutes.
_bloqueadas = {"palabras": [], "leidas": 0.0}


def _palabras_bloqueadas(cur):
    if time.time() - _bloqueadas["leidas"] > 300:
        cur.execute("SELECT palabra FROM palabra_bloqueada")
        _bloqueadas["palabras"] = [fila["palabra"] for fila in cur.fetchall()]
        _bloqueadas["leidas"] = time.time()
    return _bloqueadas["palabras"]


def _usuario(event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    if not claims.get("sub"):
        raise ErrorApi(401, "NO_AUTENTICADO", "Inicia sesión para personalizar tu camiseta.")
    return claims["sub"], claims.get("email")


def _cuerpo(event):
    crudo = event.get("body") or ""
    if event.get("isBase64Encoded"):
        crudo = base64.b64decode(crudo).decode("utf-8")
    try:
        datos = json.loads(crudo or "{}")
    except ValueError:
        datos = None
    if not isinstance(datos, dict):
        raise ErrorApi(400, "CUERPO_INVALIDO", "El cuerpo de la solicitud debe ser un objeto JSON.")
    return datos


def opciones(event):
    with db.conexion().cursor() as cur:
        cur.execute(
            "SELECT sku, nombre, precio, color1, color2 FROM producto WHERE personalizable ORDER BY sku"
        )
        productos = cur.fetchall()
        cur.execute("SELECT codigo, nombre, precio FROM parche WHERE activo ORDER BY orden")
        parches = cur.fetchall()
        cur.execute("SELECT numero, motivo FROM dorsal_reservado ORDER BY numero")
        reservados = cur.fetchall()
    return ok({
        "productos": productos,
        "parches": parches,
        "dorsales_reservados": reservados,
        "reglas": {
            "nombre_max": validacion.NOMBRE_MAX,
            "numero_min": validacion.NUMERO_MIN,
            "numero_max": validacion.NUMERO_MAX,
        },
    })


def listar(event):
    sub, _email = _usuario(event)
    with db.conexion().cursor() as cur:
        cur.execute(_SELECT + " WHERE p.user_sub = %s ORDER BY p.actualizado DESC", (sub,))
        return ok(cur.fetchall())


def guardar(event):
    sub, email = _usuario(event)
    datos = _cuerpo(event)
    sku = str(datos.get("sku") or "").strip().upper()
    nombre = validacion.normalizar_nombre(datos.get("nombre"))
    numero = validacion.validar_numero(datos.get("numero"))
    codigo_parche = str(datos.get("parche") or "NINGUNO").strip().upper()

    with db.conexion().cursor() as cur:
        cur.execute("SELECT sku, nombre, precio, personalizable FROM producto WHERE sku = %s", (sku,))
        producto = cur.fetchone()
        if not producto or not producto["personalizable"]:
            raise ErrorApi(400, "PRODUCTO_NO_PERSONALIZABLE", "Ese producto no admite nombre y número.")

        validacion.validar_nombre(nombre, _palabras_bloqueadas(cur))

        cur.execute("SELECT motivo FROM dorsal_reservado WHERE numero = %s", (numero,))
        reservado = cur.fetchone()
        if reservado:
            raise ErrorApi(400, "DORSAL_RESERVADO", reservado["motivo"])

        cur.execute("SELECT codigo, precio FROM parche WHERE codigo = %s AND activo", (codigo_parche,))
        parche = cur.fetchone()
        if not parche:
            raise ErrorApi(400, "PARCHE_INVALIDO", "Ese parche no está disponible.")

        # Name and number are free for members, as the store's membership section promises;
        # only the optional patch adds to the jersey's price.
        precio_final = producto["precio"] + parche["precio"]

        cur.execute(
            """
            INSERT INTO personalizacion (user_sub, email, sku, nombre, numero, parche, precio_final)
            VALUES (%s, %s, %s, %s, %s, %s, %s) AS nuevo
            ON DUPLICATE KEY UPDATE email = nuevo.email, nombre = nuevo.nombre, numero = nuevo.numero,
                                    parche = nuevo.parche, precio_final = nuevo.precio_final
            """,
            (sub, email, sku, nombre, numero, parche["codigo"], precio_final),
        )
        # MySQL reports 1 for an insert, 2 for an update, 0 when nothing changed.
        creada = cur.rowcount == 1
        cur.execute(_SELECT + " WHERE p.user_sub = %s AND p.sku = %s", (sub, sku))
        guardada = cur.fetchone()

    log.info("personalizacion %s sku=%s numero=%s", "creada" if creada else "actualizada", sku, numero)
    return ok(guardada, 201 if creada else 200)


def eliminar(event):
    sub, _email = _usuario(event)
    ident = str((event.get("pathParameters") or {}).get("id", ""))
    if not ident.isdigit():
        raise ErrorApi(404, "NO_ENCONTRADA", "Esa personalización no existe.")
    with db.conexion().cursor() as cur:
        # The user_sub condition is the ownership check: someone else's id simply matches nothing.
        cur.execute("DELETE FROM personalizacion WHERE id = %s AND user_sub = %s", (int(ident), sub))
        if cur.rowcount == 0:
            raise ErrorApi(404, "NO_ENCONTRADA", "Esa personalización no existe.")
    return {"statusCode": 204, "body": ""}


RUTAS = {
    "GET /personalizaciones/opciones": opciones,
    "GET /personalizaciones": listar,
    "POST /personalizaciones": guardar,
    "DELETE /personalizaciones/{id}": eliminar,
}


def handler(event, context):
    accion = RUTAS.get(event.get("routeKey", ""))
    try:
        if accion is None:
            raise ErrorApi(404, "RUTA_NO_ENCONTRADA", "Ruta no encontrada.")
        return accion(event)
    except ErrorApi as e:
        return error(e.status, e.codigo, e.mensaje)
    except pymysql.Error:
        log.exception("error de base de datos")
        return error(503, "BASE_DE_DATOS_NO_DISPONIBLE", "No pudimos guardar tu personalización. Intenta de nuevo.")
