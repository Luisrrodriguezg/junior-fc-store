"""Rules for a jersey personalization. Pure functions: no database, so they are unit-tested directly.

The data-driven checks (is the product personalizable, is the number reserved, which words are
blocked) live in RDS; this module only receives the blocked-word list as an argument.
"""

import re
import unicodedata

from jfc.respuestas import ErrorApi

NOMBRE_MAX = 12
NUMERO_MIN, NUMERO_MAX = 1, 99

# Letters (with Spanish accents), inner spaces, dots, apostrophes and hyphens: "DE LA HOZ", "O'NEIL".
NOMBRE_RE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ .'-]{0,%d}$" % (NOMBRE_MAX - 1))

# Characters people use to sneak a blocked word past a filter ("M13RD4").
_LEET = str.maketrans({"4": "A", "@": "A", "3": "E", "1": "I", "!": "I", "0": "O", "5": "S", "$": "S", "7": "T"})


def normalizar_nombre(valor):
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorApi(400, "NOMBRE_INVALIDO", "Escribe el nombre que irá en la espalda.")
    return " ".join(valor.split()).upper()


def forma_canonica(texto):
    """Uppercase A–Z only: leetspeak undone, accents removed, everything else dropped."""
    sin_leet = texto.upper().translate(_LEET)
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", sin_leet) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z]", "", sin_tildes)


def validar_nombre(nombre, palabras_bloqueadas):
    # Blocked words are checked before the character rules so that "M13RD4" is reported as what it
    # is, not as a generic "letters only" error.
    canonico = forma_canonica(nombre)
    for palabra in palabras_bloqueadas:
        if palabra and forma_canonica(palabra) in canonico:
            raise ErrorApi(400, "PALABRA_BLOQUEADA", "Ese nombre no está permitido en una camiseta oficial.")
    if len(nombre) > NOMBRE_MAX or not NOMBRE_RE.match(nombre):
        raise ErrorApi(
            400,
            "NOMBRE_INVALIDO",
            f"El nombre debe tener entre 1 y {NOMBRE_MAX} caracteres y solo letras, espacios, puntos o guiones.",
        )
    return nombre


def validar_numero(valor):
    if isinstance(valor, str) and valor.strip().isdigit():
        valor = int(valor.strip())
    # bool is a subclass of int in Python; true/false is not a jersey number.
    if isinstance(valor, bool) or not isinstance(valor, int) or not NUMERO_MIN <= valor <= NUMERO_MAX:
        raise ErrorApi(400, "DORSAL_FUERA_DE_RANGO", f"El dorsal debe ser un número entre {NUMERO_MIN} y {NUMERO_MAX}.")
    return valor
