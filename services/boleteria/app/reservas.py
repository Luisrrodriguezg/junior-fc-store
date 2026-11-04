"""Ticket sale logic: matches, live availability, hold → confirm → tickets.

All times are compared with UTC_TIMESTAMP() inside MySQL, so every pod uses the database's clock.
"""

import secrets
import string
import time

import pymysql

from app import asientos, config, qr
from app.db import pool
from app.errores import ErrorApi
from app.estadio import estadio

_ALFABETO = string.ascii_uppercase + string.digits
_DUPLICADO = 1062
_REINTENTABLES = {1205, 1213}  # lock wait timeout, deadlock


def _codigo(n):
    return "".join(secrets.choice(_ALFABETO) for _ in range(n))


def _iso(fecha):
    return fecha.replace(microsecond=0).isoformat() + "Z" if fecha else None


def _exigir_estadio():
    if not estadio.cargado:
        raise ErrorApi(503, "ESTADIO_NO_CARGADO", "La boletería está iniciando. Intenta en unos segundos.")


def _partido(cur, partido_id):
    cur.execute(
        "SELECT id, rival, competencia, fecha_hora, estado, fecha_hora > UTC_TIMESTAMP() AS futuro FROM partido WHERE id = %s",
        (partido_id,),
    )
    partido = cur.fetchone()
    if not partido:
        raise ErrorApi(404, "PARTIDO_NO_ENCONTRADO", "Ese partido no existe.")
    return partido


def _partido_json(p):
    return {"id": p["id"], "rival": p["rival"], "competencia": p["competencia"], "fecha_hora": _iso(p["fecha_hora"])}


# ─────────────────────────────────────────────── consultas públicas

def partidos():
    _exigir_estadio()
    with pool.conexion() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, rival, competencia, fecha_hora FROM partido
                WHERE estado = 'EN_VENTA' AND fecha_hora > UTC_TIMESTAMP() ORDER BY fecha_hora"""
        )
        lista = cur.fetchall()
        cur.execute("SELECT partido_id, tribuna, precio FROM precio_tribuna")
        precios = {(p["partido_id"], p["tribuna"]): p["precio"] for p in cur.fetchall()}
        # Seat ids encode their section (id DIV 10000); sections 1xx–4xx map to the four stands.
        cur.execute(
            """SELECT partido_id, silla_id DIV 1000000 AS grupo, COUNT(*) AS ocupadas
                 FROM silla_partido
                WHERE estado = 'VENDIDA' OR expira_en > UTC_TIMESTAMP()
                GROUP BY partido_id, grupo"""
        )
        ocupadas = {(o["partido_id"], o["grupo"]): o["ocupadas"] for o in cur.fetchall()}

    grupo_tribuna = {1: "OCCIDENTAL", 2: "ORIENTAL", 3: "NORTE", 4: "SUR"}
    tribuna_grupo = {v: k for k, v in grupo_tribuna.items()}
    resultado = []
    for p in lista:
        tribunas = []
        for codigo in ("OCCIDENTAL", "ORIENTAL", "NORTE", "SUR"):
            total = estadio.total_por_tribuna.get(codigo, 0)
            libres = total - ocupadas.get((p["id"], tribuna_grupo[codigo]), 0)
            tribunas.append({"codigo": codigo, "precio": precios.get((p["id"], codigo)), "total": total, "libres": libres})
        resultado.append({**_partido_json(p), "tribunas": tribunas})
    return resultado


def disponibilidad(partido_id):
    """Per-section occupancy for the live stadium map (polled every few seconds by the store)."""
    _exigir_estadio()
    with pool.conexion() as conn, conn.cursor() as cur:
        _partido(cur, partido_id)
        cur.execute(
            """SELECT silla_id DIV 10000 AS seccion,
                      SUM(estado = 'VENDIDA') AS vendidas,
                      SUM(estado = 'RETENIDA' AND expira_en > UTC_TIMESTAMP()) AS retenidas
                 FROM silla_partido WHERE partido_id = %s
                GROUP BY seccion""",
            (partido_id,),
        )
        conteos = {c["seccion"]: c for c in cur.fetchall()}
        cur.execute("SELECT UTC_TIMESTAMP() AS ahora")
        ahora = cur.fetchone()["ahora"]

    secciones = []
    for s in estadio.secciones:
        c = conteos.get(s["codigo"], {})
        vendidas, retenidas = int(c.get("vendidas") or 0), int(c.get("retenidas") or 0)
        secciones.append({
            "codigo": s["codigo"], "tribuna": s["tribuna"], "orden": s["orden"], "total": s["total"],
            "vendidas": vendidas, "retenidas": retenidas, "libres": s["total"] - vendidas - retenidas,
        })
    return {"partido_id": partido_id, "secciones": secciones, "generado": _iso(ahora)}


# ─────────────────────────────────────────────── reservas del usuario

def _ocupadas(cur, partido_id, tribuna):
    cur.execute(
        """SELECT sp.silla_id FROM silla_partido sp JOIN silla s ON s.id = sp.silla_id
            WHERE sp.partido_id = %s AND s.tribuna = %s
              AND (sp.estado = 'VENDIDA' OR sp.expira_en > UTC_TIMESTAMP())""",
        (partido_id, tribuna),
    )
    return {fila["silla_id"] for fila in cur.fetchall()}


def _detalle(cur, reserva_id):
    cur.execute(
        """SELECT r.*, p.rival, p.competencia, p.fecha_hora,
                  GREATEST(0, TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), r.expira_en)) AS segundos_restantes
             FROM reserva r JOIN partido p ON p.id = r.partido_id WHERE r.id = %s""",
        (reserva_id,),
    )
    r = cur.fetchone()
    cur.execute("SELECT silla_id FROM silla_partido WHERE reserva_id = %s ORDER BY silla_id", (reserva_id,))
    silla_ids = [f["silla_id"] for f in cur.fetchall()]
    if not silla_ids:  # expired or cancelled: seats already released, tickets never issued
        cur.execute("SELECT silla_id FROM boleta WHERE reserva_id = %s ORDER BY silla_id", (reserva_id,))
        silla_ids = [f["silla_id"] for f in cur.fetchall()]
    ubicaciones = [estadio.ubicacion[i] for i in silla_ids if i in estadio.ubicacion]
    detalle = {
        "id": r["id"],
        "codigo": r["codigo"],
        "estado": r["estado"],
        "partido": {"id": r["partido_id"], "rival": r["rival"], "competencia": r["competencia"], "fecha_hora": _iso(r["fecha_hora"])},
        "tribuna": r["tribuna"],
        "seccion": ubicaciones[0][1] if ubicaciones else None,
        "fila": ubicaciones[0][2] if ubicaciones else None,
        "sillas": [u[3] for u in ubicaciones],
        "silla_ids": silla_ids,
        "cantidad": r["cantidad"],
        "precio_unitario": r["precio_unitario"],
        "total": r["total"],
        "expira_en": _iso(r["expira_en"]),
        "segundos_restantes": int(r["segundos_restantes"]) if r["estado"] == "RETENIDA" else 0,
    }
    if r["estado"] == "CONFIRMADA":
        detalle["boletas"] = _boletas(cur, "b.reserva_id = %s", (reserva_id,))
    return detalle


def _propia(cur, reserva_id, usuario, bloquear=False):
    cur.execute(
        "SELECT *, expira_en > UTC_TIMESTAMP() AS vigente FROM reserva WHERE id = %s" + (" FOR UPDATE" if bloquear else ""),
        (reserva_id,),
    )
    r = cur.fetchone()
    # Someone else's reservation looks exactly like a missing one.
    if not r or r["user_sub"] != usuario.sub:
        raise ErrorApi(404, "RESERVA_NO_ENCONTRADA", "Esa reserva no existe.")
    return r


def reservar(usuario, partido_id, tribuna, cantidad, precio_max=None):
    _exigir_estadio()
    tribuna = tribuna.strip().upper()
    if tribuna not in estadio.filas_por_tribuna:
        raise ErrorApi(400, "TRIBUNA_INVALIDA", "Elige Occidental, Oriental, Norte o Sur.")
    if not 1 <= cantidad <= config.MAX_BOLETAS_POR_COMPRA:
        raise ErrorApi(400, "CANTIDAD_INVALIDA", f"Puedes comprar entre 1 y {config.MAX_BOLETAS_POR_COMPRA} boletas.")

    with pool.conexion() as conn, conn.cursor() as cur:
        partido = _partido(cur, partido_id)
        if partido["estado"] != "EN_VENTA" or not partido["futuro"]:
            raise ErrorApi(409, "VENTA_CERRADA", "La venta para ese partido está cerrada.")
        cur.execute("SELECT precio FROM precio_tribuna WHERE partido_id = %s AND tribuna = %s", (partido_id, tribuna))
        fila_precio = cur.fetchone()
        if not fila_precio:
            raise ErrorApi(409, "TRIBUNA_SIN_VENTA", "Esa tribuna no está a la venta para este partido.")
        precio = fila_precio["precio"]
        if precio_max is not None and precio > precio_max:
            raise ErrorApi(409, "PRECIO_SUPERA_MAXIMO", f"En esa tribuna cada boleta cuesta ${precio:,}".replace(",", ".") + ", más que tu máximo.")
        cur.execute(
            """SELECT id FROM reserva WHERE user_sub = %s AND partido_id = %s
                AND estado = 'RETENIDA' AND expira_en > UTC_TIMESTAMP() LIMIT 1""",
            (usuario.sub, partido_id),
        )
        activa = cur.fetchone()
        if activa:
            raise ErrorApi(409, "RESERVA_ACTIVA", "Ya tienes sillas retenidas para este partido: confírmalas o libéralas primero.", reserva_id=activa["id"])
        conn.rollback()  # end the read snapshot before searching

        # Every buyer in the same stand would compute the same best block, so letting them race only
        # produces collisions and InnoDB deadlocks. Instead, a MySQL named lock per match+stand makes
        # search-and-hold a critical section shared by all pods; the primary key stays as the last
        # line of defense. Each turn takes a few milliseconds, so a queue of buyers drains fast.
        candado = f"jfc-reserva-{partido_id}-{tribuna}"
        cur.execute("SELECT GET_LOCK(%s, 10) AS obtenido", (candado,))
        if cur.fetchone()["obtenido"] != 1:
            raise ErrorApi(503, "ALTA_DEMANDA", "Hay mucha gente comprando en esa tribuna. Intenta de nuevo en unos segundos.")
        try:
            return _reservar_con_candado(conn, cur, usuario, partido_id, tribuna, cantidad, precio)
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (candado,))


def _reservar_con_candado(conn, cur, usuario, partido_id, tribuna, cantidad, precio):
    descartadas = set()
    for intento in range(1, 4):
        ocupadas = _ocupadas(cur, partido_id, tribuna) | descartadas
        conn.rollback()
        inicio = time.perf_counter()
        bloque, evaluados = asientos.mejor_bloque(estadio.filas_por_tribuna[tribuna], ocupadas, cantidad)
        busqueda_ms = round((time.perf_counter() - inicio) * 1000, 1)
        if bloque is None:
            raise ErrorApi(409, "SIN_DISPONIBILIDAD", f"No quedan {cantidad} sillas juntas en esa tribuna. Prueba otra tribuna o menos boletas.")
        ids = [s.id for s in bloque.sillas]
        try:
            cur.execute("SELECT UTC_TIMESTAMP() + INTERVAL %s SECOND AS expira", (config.RESERVA_TTL_SEGUNDOS,))
            expira = cur.fetchone()["expira"]
            # A hold that already expired but wasn't swept yet still occupies the primary key.
            cur.execute(
                f"""DELETE FROM silla_partido WHERE partido_id = %s AND estado = 'RETENIDA'
                     AND expira_en <= UTC_TIMESTAMP() AND silla_id IN ({",".join(["%s"] * len(ids))})""",
                (partido_id, *ids),
            )
            cur.execute(
                """INSERT INTO reserva (codigo, partido_id, user_sub, email, tribuna, cantidad, precio_unitario, total, expira_en)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (_codigo(8), partido_id, usuario.sub, usuario.email, tribuna, cantidad, precio, precio * cantidad, expira),
            )
            reserva_id = cur.lastrowid
            cur.executemany(
                "INSERT INTO silla_partido (partido_id, silla_id, estado, reserva_id, expira_en) VALUES (%s, %s, 'RETENIDA', %s, %s)",
                [(partido_id, silla, reserva_id, expira) for silla in ids],
            )
            conn.commit()
            break
        except pymysql.err.IntegrityError as e:
            # The primary key refused a seat someone else already holds (only possible if a writer
            # bypassed the stand lock). Search again without those seats.
            conn.rollback()
            if e.args[0] != _DUPLICADO:
                raise
            descartadas.update(ids)
        except pymysql.err.OperationalError as e:
            # Deadlock / lock wait with the expiry worker's sweep: InnoDB rolled us back, try again.
            conn.rollback()
            if e.args[0] not in _REINTENTABLES:
                raise
    else:
        raise ErrorApi(409, "SIN_DISPONIBILIDAD", "Mucha gente está comprando en esa tribuna ahora mismo. Intenta de nuevo.")

    detalle = _detalle(cur, reserva_id)
    detalle["busqueda"] = {
        "bloques_evaluados": evaluados,
        "milisegundos": busqueda_ms,
        "intentos": intento,
        "puntaje_vista": round(bloque.puntaje_vista, 1),
        "sillas_sueltas": bloque.sillas_sueltas,
        "pod": config.POD,
    }
    return detalle


def activa(usuario, partido_id):
    with pool.conexion() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM reserva WHERE user_sub = %s AND partido_id = %s
                AND estado = 'RETENIDA' AND expira_en > UTC_TIMESTAMP() ORDER BY id DESC LIMIT 1""",
            (usuario.sub, partido_id),
        )
        fila = cur.fetchone()
        return _detalle(cur, fila["id"]) if fila else None


def confirmar(usuario, reserva_id):
    """Simulated payment: the held seats become sold and one signed QR ticket is issued per seat."""
    with pool.conexion() as conn, conn.cursor() as cur:
        r = _propia(cur, reserva_id, usuario, bloquear=True)
        if r["estado"] == "CONFIRMADA":
            return _detalle(cur, reserva_id)  # a double click must not fail
        if r["estado"] != "RETENIDA" or not r["vigente"]:
            raise ErrorApi(410, "RESERVA_EXPIRADA", "Se acabaron los 10 minutos y las sillas volvieron a la venta. Busca de nuevo.")
        cur.execute(
            "UPDATE silla_partido SET estado = 'VENDIDA', expira_en = NULL WHERE reserva_id = %s AND estado = 'RETENIDA'",
            (reserva_id,),
        )
        if cur.rowcount != r["cantidad"]:
            conn.rollback()
            raise ErrorApi(410, "RESERVA_EXPIRADA", "Se acabaron los 10 minutos y las sillas volvieron a la venta. Busca de nuevo.")
        cur.execute("UPDATE reserva SET estado = 'CONFIRMADA', confirmada = UTC_TIMESTAMP() WHERE id = %s", (reserva_id,))
        cur.execute("SELECT silla_id FROM silla_partido WHERE reserva_id = %s ORDER BY silla_id", (reserva_id,))
        filas = []
        for f in cur.fetchall():
            codigo = _codigo(10)
            filas.append((codigo, reserva_id, r["partido_id"], f["silla_id"], qr.firmar(codigo, r["partido_id"], f["silla_id"], config.QR_HMAC_KEY)))
        cur.executemany(
            "INSERT INTO boleta (codigo, reserva_id, partido_id, silla_id, qr_payload) VALUES (%s, %s, %s, %s, %s)",
            filas,
        )
        conn.commit()
        return _detalle(cur, reserva_id)


def cancelar(usuario, reserva_id):
    with pool.conexion() as conn, conn.cursor() as cur:
        r = _propia(cur, reserva_id, usuario, bloquear=True)
        if r["estado"] != "RETENIDA":
            raise ErrorApi(409, "NO_CANCELABLE", "Solo se pueden liberar sillas que aún están retenidas.")
        cur.execute("DELETE FROM silla_partido WHERE reserva_id = %s AND estado = 'RETENIDA'", (reserva_id,))
        cur.execute("UPDATE reserva SET estado = 'CANCELADA' WHERE id = %s", (reserva_id,))
        conn.commit()


def _boletas(cur, condicion, parametros):
    cur.execute(
        f"""SELECT b.codigo, b.qr_payload, b.silla_id, b.partido_id, r.codigo AS reserva, r.tribuna,
                   r.precio_unitario, r.email, p.rival, p.competencia, p.fecha_hora
              FROM boleta b JOIN reserva r ON r.id = b.reserva_id JOIN partido p ON p.id = b.partido_id
             WHERE {condicion} ORDER BY p.fecha_hora, b.silla_id""",
        parametros,
    )
    boletas = []
    for b in cur.fetchall():
        tribuna, seccion, fila, numero = estadio.ubicacion.get(b["silla_id"], (b["tribuna"], None, None, None))
        boletas.append({
            "codigo": b["codigo"],
            "reserva": b["reserva"],
            "partido": {"id": b["partido_id"], "rival": b["rival"], "competencia": b["competencia"], "fecha_hora": _iso(b["fecha_hora"])},
            "tribuna": tribuna, "seccion": seccion, "fila": fila, "silla": numero, "silla_id": b["silla_id"],
            "precio": b["precio_unitario"],
            "titular": b["email"],
            "qr_svg": qr.svg(b["qr_payload"]),
        })
    return boletas


def mis_boletas(usuario):
    with pool.conexion() as conn, conn.cursor() as cur:
        return _boletas(cur, "r.user_sub = %s", (usuario.sub,))
