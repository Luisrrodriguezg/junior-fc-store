"""The stadium layout, loaded from RDS once per pod and kept in memory.

~46,400 seats never change during a sale, so each pod reads them at startup and every request only
has to ask RDS which seats are taken for its match. This warm, long-lived index (plus the expiry
worker) is why the service runs as a container rather than as a Lambda.
"""

import logging
import threading
import time

from app.asientos import Silla
from app.db import conectar

log = logging.getLogger("boleteria.estadio")


class Estadio:
    def __init__(self):
        self.cargado = False
        self.filas_por_tribuna = {}   # tribuna -> [(seccion, fila, [Silla, ...]), ...]
        self.secciones = []           # [{codigo, tribuna, orden, total}]
        self.total_por_tribuna = {}
        self.ubicacion = {}           # silla id -> (tribuna, seccion, fila, numero)

    def cargar(self):
        conn = conectar(autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo, tribuna, orden FROM seccion ORDER BY tribuna, orden")
                secciones = cur.fetchall()
                cur.execute("SELECT id, tribuna, seccion, fila, numero, puntaje_vista FROM silla ORDER BY seccion, fila, numero")
                sillas = cur.fetchall()
        finally:
            conn.close()

        filas, ubicacion, total_seccion = {}, {}, {}
        for s in sillas:
            clave = (s["tribuna"], s["seccion"], s["fila"])
            filas.setdefault(clave, []).append(Silla(s["id"], s["numero"], s["puntaje_vista"]))
            ubicacion[s["id"]] = (s["tribuna"], s["seccion"], s["fila"], s["numero"])
            total_seccion[s["seccion"]] = total_seccion.get(s["seccion"], 0) + 1

        por_tribuna = {}
        for (tribuna, seccion, fila), fila_sillas in filas.items():
            por_tribuna.setdefault(tribuna, []).append((seccion, fila, fila_sillas))

        self.filas_por_tribuna = por_tribuna
        self.ubicacion = ubicacion
        self.secciones = [dict(s, total=total_seccion.get(s["codigo"], 0)) for s in secciones]
        self.total_por_tribuna = {}
        for s in self.secciones:
            self.total_por_tribuna[s["tribuna"]] = self.total_por_tribuna.get(s["tribuna"], 0) + s["total"]
        self.cargado = bool(sillas)
        log.info("estadio cargado: %d sillas en %d secciones", len(sillas), len(secciones))

    def cargar_con_reintentos(self):
        """Keeps trying in the background (RDS may still be starting); /readyz stays 503 until it works."""
        def intentar():
            espera = 2
            while not self.cargado:
                try:
                    self.cargar()
                except Exception as e:  # noqa: BLE001 - any failure just means "try again later"
                    log.warning("no se pudo cargar el estadio (%s); reintento en %ds", e, espera)
                    time.sleep(espera)
                    espera = min(espera * 2, 30)

        threading.Thread(target=intentar, name="carga-estadio", daemon=True).start()


estadio = Estadio()
