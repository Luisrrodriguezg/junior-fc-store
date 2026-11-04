"""Creates .secrets/jfc.env with random passwords/keys (only if it doesn't exist). Prints nothing secret.

Alphanumeric only: RDS rejects / @ " and spaces, and it keeps the values shell- and YAML-safe.
"""

import os
import secrets
import string

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, ".secrets", "jfc.env")
ALFABETO = string.ascii_letters + string.digits


def aleatorio(n=32):
    return "".join(secrets.choice(ALFABETO) for _ in range(n))


if os.path.exists(DESTINO):
    print(f"{DESTINO} ya existe; no se modifica.")
else:
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(os.open(DESTINO, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
        f.write(f"DB_MASTER_PASSWORD={aleatorio()}\n")
        f.write(f"APP_DB_PASSWORD={aleatorio()}\n")
        f.write(f"GATEWAY_SECRET={aleatorio(40)}\n")
        f.write(f"QR_HMAC_KEY={aleatorio(48)}\n")
    print(f"Secretos creados en {DESTINO} (permisos 600).")
