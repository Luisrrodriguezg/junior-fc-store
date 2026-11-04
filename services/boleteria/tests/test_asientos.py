import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import qr  # noqa: E402
from app.asientos import PENALIZACION_SUELTA, Silla, mejor_bloque  # noqa: E402


def fila(seccion, numero_fila, puntajes):
    sillas = [Silla(seccion * 10000 + numero_fila * 100 + n, n, p) for n, p in enumerate(puntajes, start=1)]
    return (seccion, numero_fila, sillas)


def ids(seccion, numero_fila, numeros):
    return {seccion * 10000 + numero_fila * 100 + n for n in numeros}


def test_elige_el_bloque_de_mejor_vista():
    # In 106, seats 2–3 have the best view but would strand 1 and 4; 1–2 (avg 85, nothing stranded)
    # beats them (90 − 2 × penalty), and anything in 101 is far worse.
    filas = [fila(101, 1, [10, 10, 10, 10]), fila(106, 1, [80, 90, 90, 80])]
    bloque, _ = mejor_bloque(filas, set(), 2)
    assert (bloque.seccion, [s.numero for s in bloque.sillas]) == (106, [1, 2])


def test_evita_dejar_una_silla_suelta():
    # Row: X X _ _ _ X _ _ X X  (equal view everywhere). Asking for 2:
    # 3–4 strands 5, 4–5 strands 3, 7–8 fills its gap exactly -> 7–8.
    filas = [fila(104, 14, [50] * 10)]
    ocupadas = ids(104, 14, [1, 2, 6, 9, 10])
    bloque, _ = mejor_bloque(filas, ocupadas, 2)
    assert [s.numero for s in bloque.sillas] == [7, 8]
    assert bloque.sillas_sueltas == 0


def test_la_penalizacion_puede_ceder_ante_una_vista_mucho_mejor():
    # Seats 3–4 strand both 2 and 5, but their view is so much better (100 vs 55) that they still
    # win after the two penalties.
    puntajes = [10, 10, 100, 100, 10]
    filas = [fila(101, 1, puntajes)]
    bloque, _ = mejor_bloque(filas, ids(101, 1, [1]), 2)
    assert [s.numero for s in bloque.sillas] == [3, 4]
    assert bloque.sillas_sueltas == 2
    assert bloque.puntaje == 100 - 2 * PENALIZACION_SUELTA


def test_no_une_sillas_separadas_por_una_ocupada():
    filas = [fila(101, 1, [50, 50, 50, 50, 50])]
    bloque, _ = mejor_bloque(filas, ids(101, 1, [3]), 3)
    assert bloque is None


def test_sin_disponibilidad_devuelve_none():
    filas = [fila(101, 1, [50, 50])]
    bloque, evaluados = mejor_bloque(filas, ids(101, 1, [1, 2]), 1)
    assert bloque is None and evaluados == 0


def test_cantidad_mayor_que_cualquier_fila():
    bloque, _ = mejor_bloque([fila(101, 1, [50] * 4)], set(), 6)
    assert bloque is None


def test_cuenta_los_bloques_evaluados():
    # 5 free seats, blocks of 2 -> 4 windows.
    _, evaluados = mejor_bloque([fila(101, 1, [50] * 5)], set(), 2)
    assert evaluados == 4


def test_qr_firmado_y_alterado():
    payload = qr.firmar("ABCDE12345", 1, 1041407, "clave")
    assert qr.verificar(payload, "clave")
    assert not qr.verificar(payload.replace("1041407", "1041408"), "clave")
    assert not qr.verificar(payload, "otra-clave")
    assert qr.svg(payload).startswith("<svg viewBox=")
