"""Lambda jfc-agente — "Juni", the ticketing assistant (Amazon Bedrock + tool use).

Route (API Gateway HTTP API, payload 2.0, Cognito JWT required):
  POST /agente/mensajes   {"mensaje": "quiero 2 boletas para el próximo partido", "historial": [...]}
                          → {"data": {"respuesta", "historial", "acciones"}}

The agent's tools are the store's own endpoints (/boleteria/*) called through API Gateway with the
caller's token; see jfc/conversacion.py. This function holds no database connection.
"""

import base64
import json
import logging
import os

from jfc import conversacion
from jfc.respuestas import ErrorApi, error, ok

log = logging.getLogger()
log.setLevel(logging.INFO)


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


def handler(event, context):
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
        token = (event.get("headers") or {}).get("authorization", "")
        if not claims.get("sub") or not token.lower().startswith("bearer "):
            raise ErrorApi(401, "NO_AUTENTICADO", "Inicia sesión para hablar con Juni.")
        datos = _cuerpo(event)

        servicios = conversacion.Servicios(os.environ["API_BASE_URL"], token.split(" ", 1)[1])
        respuesta, historial, acciones = conversacion.conversar(
            datos.get("mensaje"), datos.get("historial"), servicios, os.environ["AGENTE_MODEL_ID"]
        )
        log.info("agente sub=%s herramientas=%s", claims["sub"], [a["herramienta"] for a in acciones])
        return ok({"respuesta": respuesta, "historial": historial, "acciones": acciones})
    except ErrorApi as e:
        return error(e.status, e.codigo, e.mensaje)
    except Exception:  # noqa: BLE001 — Bedrock throttling, missing model access, a malformed history...
        # None of it is something the fan can fix, and API Gateway would turn a crash into a bare 500.
        log.exception("el agente falló")
        return error(503, "ASISTENTE_NO_DISPONIBLE", "Juni no está disponible en este momento. Intenta de nuevo en unos segundos.")
