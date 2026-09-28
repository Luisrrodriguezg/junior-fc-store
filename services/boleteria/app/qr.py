"""Signed ticket payloads and their QR codes.

Payload: JFC1|<ticket code>|<match id>|<seat id>|<signature>
The signature is an HMAC-SHA256 of the rest with a key only the service knows, so a QR that was
edited (another seat, another match) or invented from scratch fails verify().
"""

import base64
import hashlib
import hmac

import segno

_VERSION = "JFC1"


def _firma(base, clave):
    digest = hmac.new(clave.encode(), base.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)[:22].decode()


def firmar(codigo, partido_id, silla_id, clave):
    base = f"{_VERSION}|{codigo}|{partido_id}|{silla_id}"
    return f"{base}|{_firma(base, clave)}"


def verificar(payload, clave):
    base, _, firma = payload.rpartition("|")
    return base.startswith(_VERSION + "|") and hmac.compare_digest(firma, _firma(base, clave))


def svg(payload):
    """Inline SVG (viewBox, no fixed size) so the page can scale it with CSS."""
    return segno.make(payload, error="m").svg_inline(scale=1, omitsize=True, border=2, dark="#11161c")
