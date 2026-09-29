"""MySQL connections: a small pool shared by the request threads.

Connections run with autocommit off, and every checkout ends with a rollback: under REPEATABLE
READ an open transaction would keep reading an old snapshot, and the live map must see fresh data.
Writes call conn.commit() themselves before the connection is returned.
"""

import contextlib
import queue

import pymysql

from app import config


def _ssl():
    if config.DB_SSL_MODE == "off":
        return None
    if config.DB_SSL_MODE == "require":
        return {"verify_mode": "none"}
    return {"ca": config.DB_SSL_CA}


def conectar(autocommit=False):
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        ssl=_ssl(),
        autocommit=autocommit,
        connect_timeout=5,
        read_timeout=15,
        write_timeout=15,
    )


class Pool:
    def __init__(self, tamano=8):
        self._libres = queue.LifoQueue()
        self._tamano = tamano

    @contextlib.contextmanager
    def conexion(self):
        try:
            conn = self._libres.get_nowait()
            conn.ping(reconnect=True)
        except queue.Empty:
            conn = conectar()
        except pymysql.Error:
            conn = conectar()
        try:
            yield conn
        finally:
            try:
                conn.rollback()
                if self._libres.qsize() < self._tamano:
                    self._libres.put(conn)
                    conn = None
            except pymysql.Error:
                pass
            if conn is not None:
                conn.close()


pool = Pool()
