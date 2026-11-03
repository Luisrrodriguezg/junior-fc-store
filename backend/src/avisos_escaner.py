"""Lambda jfc-avisos-escaner — finds ticket holds that are about to expire and queues a notice for each.

Runs every minute (EventBridge). A hold lasts 10 minutes and the window is the last two, so every
hold passes through the window on at least one run. The table aviso_reserva is the "already queued"
memory: its primary key lets exactly one run claim a hold, even if two runs overlap.

The scanner only decides *who* to warn. Sending is the notifier's job, on the other side of an SQS
queue, so a slow or failing mail service never delays the scan and a failed notice is retried and
finally parked in a dead-letter queue instead of being lost.
"""

import json
import logging
import os

import pymysql

from jfc import db

log = logging.getLogger()
log.setLevel(logging.INFO)

_sqs = None

_PENDIENTES = """
    SELECT r.id, r.codigo, r.email, r.tribuna, r.cantidad, r.total, r.expira_en, p.rival
      FROM reserva r
      JOIN partido p ON p.id = r.partido_id
      LEFT JOIN aviso_reserva a ON a.reserva_id = r.id
     WHERE r.estado = 'RETENIDA'
       AND r.expira_en > UTC_TIMESTAMP()
       AND r.expira_en <= UTC_TIMESTAMP() + INTERVAL %s SECOND
       AND a.reserva_id IS NULL
"""


def _cola():
    global _sqs
    if _sqs is None:
        import boto3

        _sqs = boto3.client("sqs")
    return _sqs


def escanear(cur, cola, url_cola, ventana):
    cur.execute(_PENDIENTES, (ventana,))
    encoladas = 0
    for r in cur.fetchall():
        # Claim first: if another run already did, rowcount is 0 and this one skips the hold.
        cur.execute("INSERT IGNORE INTO aviso_reserva (reserva_id) VALUES (%s)", (r["id"],))
        if cur.rowcount != 1:
            continue
        cuerpo = {
            "reserva_id": r["id"], "codigo": r["codigo"], "email": r["email"], "rival": r["rival"],
            "tribuna": r["tribuna"], "cantidad": r["cantidad"], "total": r["total"],
            "expira_en": r["expira_en"].replace(microsecond=0).isoformat() + "Z",
        }
        try:
            cola.send_message(QueueUrl=url_cola, MessageBody=json.dumps(cuerpo))
        except Exception:
            # Un-claim, so the next run tries again while the hold is still inside the window.
            cur.execute("DELETE FROM aviso_reserva WHERE reserva_id = %s", (r["id"],))
            raise
        encoladas += 1
    return encoladas


def handler(event, context):
    ventana = int(os.environ.get("AVISO_ANTES_SEG", "120"))
    try:
        with db.conexion().cursor() as cur:
            encoladas = escanear(cur, _cola(), os.environ["AVISOS_QUEUE_URL"], ventana)
    except pymysql.Error:
        # RDS is stopped between work sessions on purpose; that is not an incident.
        log.warning("base de datos no disponible; se omite este escaneo")
        return {"encoladas": 0, "omitido": True}
    if encoladas:
        log.info("avisos encolados: %s", encoladas)
    return {"encoladas": encoladas}
