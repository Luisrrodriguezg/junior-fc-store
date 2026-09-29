"""Settings from environment variables (an OpenShift Secret in the cluster, docker-compose locally)."""

import os
import socket

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "jfc")
DB_USER = os.environ.get("DB_USER", "jfc_app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
# verify (RDS, checks the certificate) | require (TLS, no check: local container) | off
DB_SSL_MODE = os.environ.get("DB_SSL_MODE", "verify")
DB_SSL_CA = os.environ.get("DB_SSL_CA", os.path.join(os.path.dirname(__file__), "..", "certs", "global-bundle.pem"))

GATEWAY_SECRET = os.environ.get("GATEWAY_SECRET", "")
QR_HMAC_KEY = os.environ.get("QR_HMAC_KEY", "")

RESERVA_TTL_SEGUNDOS = int(os.environ.get("RESERVA_TTL_SEGUNDOS", "600"))
EXPIRADOR_INTERVALO_SEGUNDOS = int(os.environ.get("EXPIRADOR_INTERVALO_SEGUNDOS", "30"))
MAX_BOLETAS_POR_COMPRA = 6

# Pod name in OpenShift (HOSTNAME), container id locally. Sent back as X-Served-By.
POD = os.environ.get("HOSTNAME") or socket.gethostname()
