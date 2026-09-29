"""API Gateway (HTTP API, payload 2.0) responses: {"data": ...} or {"error": {code, message}}.

CORS headers are not set here: the HTTP API's CorsConfiguration adds them to every response.
"""

import datetime
import decimal
import json


class ErrorApi(Exception):
    def __init__(self, status, codigo, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje


def _json_default(valor):
    if isinstance(valor, datetime.datetime):
        # Stored in UTC; the "Z" tells the browser so, which formats it for Barranquilla.
        return valor.replace(microsecond=0).isoformat() + "Z"
    if isinstance(valor, decimal.Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    raise TypeError(f"not JSON serializable: {type(valor).__name__}")


def _respuesta(status, cuerpo):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff"},
        "body": json.dumps(cuerpo, default=_json_default, ensure_ascii=False),
    }


def ok(datos, status=200):
    return _respuesta(status, {"data": datos})


def error(status, codigo, mensaje):
    return _respuesta(status, {"error": {"code": codigo, "message": mensaje}})
