import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jfc import estadio, validacion  # noqa: E402
from jfc.respuestas import ErrorApi  # noqa: E402

BLOQUEADAS = ["MIERDA", "PUTA", "NAZI"]


def codigo_de(funcion, *args):
    with pytest.raises(ErrorApi) as info:
        funcion(*args)
    return info.value.codigo


@pytest.mark.parametrize("entrada, esperado", [
    ("  garcía ", "GARCÍA"),
    ("de   la hoz", "DE LA HOZ"),
    ("teo", "TEO"),
    ("muñoz", "MUÑOZ"),
])
def test_normaliza_y_acepta_nombres_validos(entrada, esperado):
    nombre = validacion.normalizar_nombre(entrada)
    assert validacion.validar_nombre(nombre, BLOQUEADAS) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", None, 10])
def test_nombre_vacio_o_no_texto(entrada):
    assert codigo_de(validacion.normalizar_nombre, entrada) == "NOMBRE_INVALIDO"


@pytest.mark.parametrize("nombre", ["GARCIA10", "ABCDEFGHIJKLM", "-GARCIA", "GAR<b>CIA"])
def test_nombre_con_caracteres_o_largo_invalido(nombre):
    assert codigo_de(validacion.validar_nombre, nombre, BLOQUEADAS) == "NOMBRE_INVALIDO"


@pytest.mark.parametrize("nombre", ["MIERDA", "M13RD4", "M.I.E.R.D.A", "MÍERDA", "LA PUTA", "N4Z1"])
def test_palabras_bloqueadas_aunque_esten_disfrazadas(nombre):
    assert codigo_de(validacion.validar_nombre, nombre, BLOQUEADAS) == "PALABRA_BLOQUEADA"


@pytest.mark.parametrize("valor, esperado", [(1, 1), (99, 99), ("10", 10), (" 7 ", 7)])
def test_dorsal_valido(valor, esperado):
    assert validacion.validar_numero(valor) == esperado


@pytest.mark.parametrize("valor", [0, 100, -1, 10.5, "diez", None, True, "1e1"])
def test_dorsal_invalido(valor):
    assert codigo_de(validacion.validar_numero, valor) == "DORSAL_FUERA_DE_RANGO"


def test_estadio_tiene_46400_sillas_con_ids_unicos():
    sillas = list(estadio.sillas())
    assert len(sillas) == 46400
    assert len({s[0] for s in sillas}) == 46400
    assert all(0 <= s[5] <= 100 for s in sillas)


def test_mejor_vista_en_el_centro_de_occidental():
    puntajes = {s[0]: s[5] for s in estadio.sillas()}
    centro = estadio.silla_id(106, 12, 36)   # end of the 6th of 12 sections = midfield, ideal row
    esquina = estadio.silla_id(101, 30, 1)
    tras_arco = estadio.silla_id(304, 12, 40)
    assert puntajes[centro] > puntajes[esquina]
    assert puntajes[centro] > puntajes[tras_arco]


def test_ventas_previas_deterministas_y_sin_llenar_el_estadio():
    a, b = estadio.ventas_previas(1), estadio.ventas_previas(1)
    assert a == b
    assert len(set(a)) == len(a)
    assert 0.3 < len(a) / 46400 < 0.9
