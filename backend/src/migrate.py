"""Lambda jfc-db-migrate — creates and fills the database. Not routed in API Gateway; invoke it:

  aws lambda invoke --function-name jfc-db-migrate --payload '{"accion":"migrar"}' \
      --cli-binary-format raw-in-base64-out /dev/stdout

Actions:
  migrar            (default) schema, least-privilege app user, reference data, seat map, earlier sales
  estado            row counts per table
  reiniciar_ventas  wipe every reservation/ticket and regenerate the earlier sales (demo reset)

Everything is idempotent. It connects as the RDS master user; the other services use the app user
this creates, which can only read and write rows.
"""

import logging
import os

from jfc import db, estadio

log = logging.getLogger()
log.setLevel(logging.INFO)

_SQL = os.path.join(os.path.dirname(__file__), "sql")
_LOTE = 2000
_USUARIO_TAQUILLA = "sistema-taquilla"


def _sentencias(archivo):
    with open(os.path.join(_SQL, archivo), encoding="utf-8") as f:
        # Comment lines are dropped before splitting: some of them contain ";".
        sql = "\n".join(linea for linea in f if not linea.lstrip().startswith("--"))
    return [s.strip() for s in sql.split(";") if s.strip()]


def _en_lotes(cur, sql, filas):
    filas = list(filas)
    for i in range(0, len(filas), _LOTE):
        cur.executemany(sql, filas[i : i + _LOTE])
    return len(filas)


def _crear_usuario_app(cur):
    usuario = os.environ["APP_DB_USER"]
    password = os.environ["APP_DB_PASSWORD"]
    base = os.environ.get("DB_NAME", "jfc")
    cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s REQUIRE SSL", (usuario, password))
    # Keeps the password in sync if it was rotated in the stack parameters.
    cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s REQUIRE SSL", (usuario, password))
    cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{base}`.* TO %s@'%%'", (usuario,))


def _ventas_previas(cur, partido_id):
    cur.execute(
        """
        INSERT INTO reserva (codigo, partido_id, user_sub, tribuna, cantidad, precio_unitario, total,
                             estado, expira_en, confirmada)
        VALUES (%s, %s, %s, 'TAQUILLA', 0, 0, 0, 'CONFIRMADA', UTC_TIMESTAMP(), UTC_TIMESTAMP())
        """,
        (f"TAQ{partido_id:05d}", partido_id, _USUARIO_TAQUILLA),
    )
    reserva_id = cur.lastrowid
    return _en_lotes(
        cur,
        "INSERT INTO silla_partido (partido_id, silla_id, estado, reserva_id) VALUES (%s, %s, 'VENDIDA', %s)",
        ((partido_id, silla, reserva_id) for silla in estadio.ventas_previas(partido_id)),
    )


def migrar(conn):
    resumen = {}
    with conn.cursor() as cur:
        for sentencia in _sentencias("schema.sql"):
            cur.execute(sentencia)
        _crear_usuario_app(cur)
        for sentencia in _sentencias("seed.sql"):
            cur.execute(sentencia)

        cur.execute("SELECT COUNT(*) AS n FROM silla")
        if cur.fetchone()["n"] == 0:
            _en_lotes(cur, "INSERT INTO seccion (codigo, tribuna, orden) VALUES (%s, %s, %s)", estadio.secciones())
            resumen["sillas_creadas"] = _en_lotes(
                cur,
                "INSERT INTO silla (id, tribuna, seccion, fila, numero, puntaje_vista) VALUES (%s, %s, %s, %s, %s, %s)",
                estadio.sillas(),
            )

        cur.execute(
            """
            SELECT p.id FROM partido p
             WHERE NOT EXISTS (SELECT 1 FROM reserva r WHERE r.partido_id = p.id AND r.user_sub = %s)
            """,
            (_USUARIO_TAQUILLA,),
        )
        for fila in cur.fetchall():
            resumen[f"vendidas_previas_partido_{fila['id']}"] = _ventas_previas(cur, fila["id"])
    conn.commit()
    return resumen


def estado(conn):
    tablas = ["producto", "parche", "dorsal_reservado", "palabra_bloqueada", "personalizacion", "partido",
              "tribuna", "seccion", "precio_tribuna", "silla", "silla_partido", "reserva", "boleta"]
    with conn.cursor() as cur:
        conteos = {}
        for tabla in tablas:
            cur.execute(f"SELECT COUNT(*) AS n FROM `{tabla}`")
            conteos[tabla] = cur.fetchone()["n"]
    return conteos


def reiniciar_ventas(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM boleta")
        cur.execute("DELETE FROM silla_partido")
        cur.execute("DELETE FROM reserva")
    conn.commit()
    return migrar(conn)


ACCIONES = {"migrar": migrar, "estado": estado, "reiniciar_ventas": reiniciar_ventas}


def handler(event, context):
    accion = (event or {}).get("accion", "migrar")
    if accion not in ACCIONES:
        return {"ok": False, "error": f"acción desconocida: {accion}", "acciones": sorted(ACCIONES)}
    conn = db.conectar(autocommit=False)
    try:
        resultado = ACCIONES[accion](conn)
    finally:
        conn.close()
    log.info("%s: %s", accion, resultado)
    return {"ok": True, "accion": accion, "resultado": resultado}
