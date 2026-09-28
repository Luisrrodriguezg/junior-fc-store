"""Runs the jfc-db-migrate Lambda handler against the local docker-compose MySQL.

  .venv/bin/python scripts/migrate_local.py [migrar|estado|reiniciar_ventas]
"""

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "backend", "src"))

os.environ.update({
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "3307",
    "DB_NAME": "jfc",
    "DB_USER": "root",
    "DB_PASSWORD": "localroot",
    "APP_DB_USER": "jfc_app",
    "APP_DB_PASSWORD": "localapp",
    "DB_SSL_MODE": "require",
})

import migrate  # noqa: E402  (needs the environment above)

accion = sys.argv[1] if len(sys.argv) > 1 else "migrar"
print(json.dumps(migrate.handler({"accion": accion}, None), indent=2, ensure_ascii=False))
