import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import avisos_escaner  # noqa: E402
import avisos_notificador  # noqa: E402
from jfc import avisos  # noqa: E402

AVISO = {
    "reserva_id": 7, "codigo": "ABCD1234", "email": "luis.alejo@gmail.com", "rival": "Nacional",
    "tribuna": "OCCIDENTAL", "cantidad": 2, "total": 240000, "expira_en": "2026-11-14T23:02:00Z",
}


# ─────────────────────────────────────────────── pure helpers

def test_enmascara_el_correo_para_el_grupo():
    assert avisos.enmascarar_email("luis.alejo@gmail.com") == "lu***@gmail.com"
    assert avisos.enmascarar_email(None) is None
    assert avisos.enmascarar_email("sin-arroba") is None


def test_moneda_con_puntos():
    assert avisos.moneda(240000) == "$240.000"
    assert avisos.moneda(0) == "$0"


def test_hora_local_de_barranquilla():
    assert avisos.hora_local("2026-11-14T23:02:00Z") == "18:02"


@pytest.mark.parametrize("segundos, esperado", [(119, 2), (90, 2), (45, 1), (5, 1), (0, 1)])
def test_minutos_restantes_nunca_baja_de_uno(segundos, esperado):
    assert avisos.minutos_restantes(segundos) == esperado


def test_mensaje_para_el_comprador():
    asunto, texto = avisos.mensaje(AVISO, 100)
    assert asunto == "Tu reserva vence en 2 minutos · Junior vs Nacional"
    assert "$240.000" in texto and "18:02" in texto and "ABCD1234" in texto
    assert "2 boletas" in texto


def test_mensaje_singular():
    asunto, texto = avisos.mensaje({**AVISO, "cantidad": 1}, 40)
    assert "1 minuto ·" in asunto and "1 boleta " in texto


def test_el_mensaje_del_grupo_no_expone_correo_ni_precio():
    texto = avisos.mensaje_grupo(AVISO, 100)
    assert "lu***@gmail.com" in texto
    assert "luis.alejo" not in texto and "240" not in texto


# ─────────────────────────────────────────────── scanner

class CursorFalso:
    """Replays the scanner's queries: a list of pending holds, and INSERT IGNORE results per id."""

    def __init__(self, pendientes, ya_reclamadas=()):
        self.pendientes, self.ya = pendientes, set(ya_reclamadas)
        self.rowcount = 0
        self.ejecutadas = []
        self._ultima = None

    def execute(self, sql, params=None):
        self.ejecutadas.append((" ".join(sql.split()), params))
        if sql.lstrip().startswith("INSERT IGNORE"):
            self.rowcount = 0 if params[0] in self.ya else 1
            self.ya.add(params[0])
        elif sql.lstrip().startswith("DELETE"):
            self.ya.discard(params[0])
        self._ultima = sql

    def fetchall(self):
        return self.pendientes


def reserva(id_, **extra):
    base = {"id": id_, "codigo": f"COD{id_}", "email": "a@b.co", "tribuna": "SUR", "cantidad": 2, "total": 100,
            "expira_en": datetime.datetime(2026, 11, 14, 23, 2, 0, 123), "rival": "Nacional"}
    return {**base, **extra}


class ColaFalsa:
    def __init__(self, falla=False):
        self.mensajes, self.falla = [], falla

    def send_message(self, **kwargs):
        if self.falla:
            raise RuntimeError("SQS caído")
        self.mensajes.append(kwargs)


def test_el_escaner_encola_un_mensaje_por_reserva():
    cola = ColaFalsa()
    n = avisos_escaner.escanear(CursorFalso([reserva(1), reserva(2)]), cola, "https://sqs/q", 120)
    assert n == 2
    cuerpo = json.loads(cola.mensajes[0]["MessageBody"])
    assert cuerpo["reserva_id"] == 1 and cuerpo["expira_en"] == "2026-11-14T23:02:00Z"
    assert cola.mensajes[0]["QueueUrl"] == "https://sqs/q"


def test_el_escaner_no_encola_dos_veces_la_misma_reserva():
    cola = ColaFalsa()
    n = avisos_escaner.escanear(CursorFalso([reserva(1), reserva(2)], ya_reclamadas={1}), cola, "q", 120)
    assert n == 1
    assert json.loads(cola.mensajes[0]["MessageBody"])["reserva_id"] == 2


def test_si_sqs_falla_se_libera_la_reclamacion_para_reintentar():
    cur = CursorFalso([reserva(1)])
    with pytest.raises(RuntimeError):
        avisos_escaner.escanear(cur, ColaFalsa(falla=True), "q", 120)
    assert 1 not in cur.ya  # un-claimed: the next run sees it again, still inside the window
    assert any(sql.startswith("DELETE FROM aviso_reserva") for sql, _ in cur.ejecutadas)


def test_la_consulta_solo_mira_reservas_retenidas_y_vigentes():
    cur = CursorFalso([])
    avisos_escaner.escanear(cur, ColaFalsa(), "q", 120)
    sql, params = cur.ejecutadas[0]
    assert "estado = 'RETENIDA'" in sql and "expira_en > UTC_TIMESTAMP()" in sql
    assert "a.reserva_id IS NULL" in sql
    assert params == (120,)


# ─────────────────────────────────────────────── notifier

class CursorNotificador:
    def __init__(self, segundos):
        self.segundos = segundos

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return None if self.segundos is None else {"seg": self.segundos}


@pytest.fixture
def canales(monkeypatch):
    enviados = {"correo": [], "grupo": []}
    monkeypatch.setattr(avisos_notificador, "enviar_correo", lambda aviso, asunto, texto: enviados["correo"].append((asunto, texto)) or True)
    monkeypatch.setattr(avisos_notificador, "enviar_grupo", lambda texto: enviados["grupo"].append(texto) or True)
    return enviados


def test_el_notificador_envia_por_los_dos_canales(canales):
    assert avisos_notificador.procesar(AVISO, CursorNotificador(95)) == "enviado"
    assert "vence en 2 minutos" in canales["correo"][0][0]
    assert "lu***@gmail.com" in canales["grupo"][0]


def test_el_notificador_descarta_reservas_ya_pagadas_o_liberadas(canales):
    assert avisos_notificador.procesar(AVISO, CursorNotificador(None)) == "descartado"
    assert canales == {"correo": [], "grupo": []}


def test_enviar_sin_configurar_no_hace_nada(monkeypatch):
    monkeypatch.setenv("AVISOS_REMITENTE", "none")
    monkeypatch.setenv("AVISOS_WEBHOOK", "none")
    assert avisos_notificador.enviar_correo(AVISO, "a", "b") is False
    assert avisos_notificador.enviar_grupo("hola") is False


class ErrorSes(Exception):
    def __init__(self, codigo):
        self.response = {"Error": {"Code": codigo}}


class SesFalso:
    def __init__(self, error=None):
        self.error, self.enviados = error, []

    def send_email(self, **kwargs):
        if self.error:
            raise self.error
        self.enviados.append(kwargs)


def test_un_rechazo_de_ses_no_se_reintenta(monkeypatch):
    monkeypatch.setenv("AVISOS_REMITENTE", "club@junior.co")
    monkeypatch.setattr(avisos_notificador, "_correo", lambda: SesFalso(ErrorSes("MessageRejected")))
    assert avisos_notificador.enviar_correo(AVISO, "a", "b") is False


def test_un_fallo_transitorio_de_ses_se_reintenta(monkeypatch):
    monkeypatch.setenv("AVISOS_REMITENTE", "club@junior.co")
    monkeypatch.setattr(avisos_notificador, "_correo", lambda: SesFalso(ErrorSes("Throttling")))
    with pytest.raises(ErrorSes):
        avisos_notificador.enviar_correo(AVISO, "a", "b")


def test_el_correo_sale_al_comprador_desde_el_remitente_verificado(monkeypatch):
    ses = SesFalso()
    monkeypatch.setenv("AVISOS_REMITENTE", "club@junior.co")
    monkeypatch.setattr(avisos_notificador, "_correo", lambda: ses)
    assert avisos_notificador.enviar_correo(AVISO, "Asunto", "Cuerpo") is True
    envio = ses.enviados[0]
    assert envio["FromEmailAddress"] == "club@junior.co"
    assert envio["Destination"] == {"ToAddresses": ["luis.alejo@gmail.com"]}


def test_el_handler_reporta_solo_los_mensajes_que_fallaron(monkeypatch):
    class Conexion:
        def cursor(self):
            return self

        def __enter__(self):
            return CursorNotificador(100)

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(avisos_notificador.db, "conexion", lambda: Conexion())

    def procesar(aviso, cur):
        if aviso["reserva_id"] == 2:
            raise RuntimeError("webhook caído")
        return "enviado"

    monkeypatch.setattr(avisos_notificador, "procesar", procesar)
    evento = {"Records": [
        {"messageId": "m1", "body": json.dumps({**AVISO, "reserva_id": 1})},
        {"messageId": "m2", "body": json.dumps({**AVISO, "reserva_id": 2})},
    ]}
    assert avisos_notificador.handler(evento, None) == {"batchItemFailures": [{"itemIdentifier": "m2"}]}
