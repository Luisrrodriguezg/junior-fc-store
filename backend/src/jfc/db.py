"""MySQL connection for the Lambdas.

The connection lives at module level, so a warm Lambda container reuses it across invocations
instead of reconnecting every time (same pattern as the Cloud-spotify project).

RDS is publicly reachable (the OpenShift Sandbox runs outside AWS) and its parameter group sets
require_secure_transport=1, so every connection is TLS. DB_SSL_MODE picks how:
  verify  (default) TLS + check the server certificate against the RDS CA bundle shipped here
  require           TLS without certificate check (local MySQL container, self-signed cert)
  off               plain TCP (never on RDS; it would be refused anyway)
"""

import os

import pymysql

_CA_BUNDLE = os.path.join(os.path.dirname(__file__), "..", "certs", "global-bundle.pem")

_conexion = None


def opciones_ssl():
    modo = os.environ.get("DB_SSL_MODE", "verify")
    if modo == "off":
        return None
    if modo == "require":
        return {"verify_mode": "none"}
    return {"ca": os.environ.get("DB_SSL_CA", _CA_BUNDLE)}


def conectar(usuario=None, password=None, autocommit=True):
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=usuario or os.environ["DB_USER"],
        password=password or os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "jfc"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        ssl=opciones_ssl(),
        autocommit=autocommit,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )


def conexion():
    """The container's shared autocommit connection, reconnecting if RDS dropped it."""
    global _conexion
    if _conexion is not None:
        try:
            # RDS may have closed the idle connection while the container was frozen.
            _conexion.ping(reconnect=False)
        except pymysql.Error:
            _conexion = None
    if _conexion is None:
        _conexion = conectar()
    return _conexion
