"""Lambda jfc-avisos-notificador — delivers "your hold is about to expire" notices from the SQS queue.

Two channels, both optional and configured by environment:
  * email to the buyer through Amazon SES (AVISOS_REMITENTE = a verified sender; "none" disables it)
  * a message in the class group chat through a webhook (AVISOS_WEBHOOK = Discord, Slack or Telegram
    URL; "none" disables it)

Before sending, it re-reads the hold: if the buyer paid or released it in the meantime, a "your seats
are about to expire" message would be wrong, so the notice is dropped. A message that fails is
reported back to SQS (partial batch response), retried, and after 3 attempts lands in the
dead-letter queue.
"""

import json
import logging
import os
import urllib.request

from jfc import avisos, db

log = logging.getLogger()
log.setLevel(logging.INFO)

_ses = None

# SES refusals that retrying can't fix (sandbox: recipient not verified, bad sender, ...).
_NO_REINTENTAR = {"MessageRejected", "MailFromDomainNotVerifiedException", "AccountSendingPausedException"}


def _correo():
    global _ses
    if _ses is None:
        import boto3

        _ses = boto3.client("sesv2")
    return _ses


def _configurado(nombre):
    valor = os.environ.get(nombre, "none")
    return None if valor in ("", "none") else valor


def segundos_restantes(cur, reserva_id):
    """Seconds left on a hold that is still open, or None if it was paid, released or expired."""
    cur.execute(
        """SELECT TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), expira_en) AS seg FROM reserva
            WHERE id = %s AND estado = 'RETENIDA' AND expira_en > UTC_TIMESTAMP()""",
        (reserva_id,),
    )
    fila = cur.fetchone()
    return int(fila["seg"]) if fila else None


def enviar_correo(aviso, asunto, texto):
    remitente = _configurado("AVISOS_REMITENTE")
    if not remitente or not aviso.get("email"):
        return False
    try:
        _correo().send_email(
            FromEmailAddress=remitente,
            Destination={"ToAddresses": [aviso["email"]]},
            Content={"Simple": {"Subject": {"Data": asunto, "Charset": "UTF-8"},
                                "Body": {"Text": {"Data": texto, "Charset": "UTF-8"}}}},
        )
        return True
    except Exception as e:  # noqa: BLE001 — botocore's ClientError carries .response; anything else is retried
        codigo = getattr(e, "response", {}).get("Error", {}).get("Code")
        if codigo in _NO_REINTENTAR:
            log.warning("SES rechazó el correo (%s); no se reintenta", codigo)
            return False
        raise


def enviar_grupo(texto):
    url = _configurado("AVISOS_WEBHOOK")
    if not url:
        return False
    # "content" is Discord's field, "text" is Slack's and Telegram's; each ignores the other.
    cuerpo = json.dumps({"content": texto, "text": texto}).encode()
    req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8):
        pass
    return True


def procesar(aviso, cur):
    segundos = segundos_restantes(cur, aviso["reserva_id"])
    if segundos is None:
        log.info("reserva %s ya no está retenida; aviso descartado", aviso["codigo"])
        return "descartado"
    asunto, texto = avisos.mensaje(aviso, segundos)
    correo = enviar_correo(aviso, asunto, texto)
    grupo = enviar_grupo(avisos.mensaje_grupo(aviso, segundos))
    log.info("aviso reserva=%s correo=%s grupo=%s", aviso["codigo"], correo, grupo)
    return "enviado"


def handler(event, context):
    fallidos = []
    with db.conexion().cursor() as cur:
        for registro in event.get("Records", []):
            try:
                procesar(json.loads(registro["body"]), cur)
            except Exception:  # noqa: BLE001 — report this message as failed, keep processing the batch
                log.exception("falló el aviso %s", registro.get("messageId"))
                fallidos.append({"itemIdentifier": registro["messageId"]})
    return {"batchItemFailures": fallidos}
