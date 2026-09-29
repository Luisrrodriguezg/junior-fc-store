"""Background worker that releases holds whose 10 minutes ran out, so those seats go back on sale.

Every replica runs this thread, but only one does the work: the one holding the MySQL named lock
`jfc-expirador`. GET_LOCK is tied to the connection, so the leader keeps it for as long as its
connection lives; if that pod dies or loses RDS, the lock is freed and another replica takes over
on its next round. That is leader election between distributed processes using the shared database.
"""

import logging
import threading

import pymysql

from app import config
from app.db import conectar

log = logging.getLogger("boleteria.expirador")

_LOCK = "jfc-expirador"


class Expirador(threading.Thread):
    def __init__(self):
        super().__init__(name="expirador", daemon=True)
        self.lider = False
        self._conn = None
        self._parar = threading.Event()

    def run(self):
        while not self._parar.is_set():
            try:
                self._ronda()
            except pymysql.Error as e:
                log.warning("expirador sin base de datos (%s); pierdo el liderazgo si lo tenía", e)
                self._soltar()
            self._parar.wait(config.EXPIRADOR_INTERVALO_SEGUNDOS)

    def detener(self):
        self._parar.set()
        self._soltar()

    def _ronda(self):
        if self._conn is None:
            self._conn = conectar(autocommit=True)
        with self._conn.cursor() as cur:
            if not self.lider:
                cur.execute("SELECT GET_LOCK(%s, 0) AS obtenido", (_LOCK,))
                self.lider = cur.fetchone()["obtenido"] == 1
                if self.lider:
                    log.info("pod %s es ahora el líder del expirador", config.POD)
            if not self.lider:
                return
            cur.execute(
                "UPDATE reserva SET estado = 'EXPIRADA' WHERE estado = 'RETENIDA' AND expira_en <= UTC_TIMESTAMP()"
            )
            reservas = cur.rowcount
            cur.execute(
                "DELETE FROM silla_partido WHERE estado = 'RETENIDA' AND expira_en <= UTC_TIMESTAMP()"
            )
            sillas = cur.rowcount
        if reservas or sillas:
            log.info("expirador (%s): %d reservas vencidas, %d sillas liberadas", config.POD, reservas, sillas)

    def _soltar(self):
        self.lider = False
        if self._conn is not None:
            try:
                self._conn.close()
            except pymysql.Error:
                pass
            self._conn = None
