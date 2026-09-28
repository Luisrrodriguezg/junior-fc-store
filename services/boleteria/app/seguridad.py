"""Who is calling, as established by API Gateway.

The OpenShift Route is public, but API Gateway is meant to be the only way in: it adds
x-gateway-secret to every request it forwards, and for signed-in routes it overwrites x-user-sub /
x-user-email with claims from the Cognito token it already verified. A request that skips the
gateway has no valid secret and is refused here, so those user headers can be trusted.
"""

import hmac
from dataclasses import dataclass

from fastapi import Header

from app import config
from app.errores import ErrorApi


@dataclass
class Usuario:
    sub: str
    email: str | None


def exigir_gateway(x_gateway_secret: str | None = Header(default=None)):
    if not config.GATEWAY_SECRET or not hmac.compare_digest(x_gateway_secret or "", config.GATEWAY_SECRET):
        raise ErrorApi(403, "ACCESO_DIRECTO_NO_PERMITIDO", "Este servicio solo atiende solicitudes que llegan por API Gateway.")


def usuario_actual(
    x_user_sub: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> Usuario:
    if not x_user_sub:
        raise ErrorApi(401, "NO_AUTENTICADO", "Inicia sesión para comprar boletas.")
    return Usuario(sub=x_user_sub, email=x_user_email or None)
