"""Best-block seat search. Pure function: the in-memory seat map and the set of taken seats in,
the best block out — no database, so it is unit-tested directly.

For every row of every section in the stand, it walks the runs of free seats that are next to
each other and slides a window of `cantidad` seats along each run. Each window scores
    average view score of its seats − PENALIZACION_SUELTA × (lone seats it would leave behind)
A lone seat is a single free seat stranded between the block and a taken seat or the aisle: it is
very hard to sell (people buy together), so cinemas and airlines avoid creating them, and so do we.
"""

from dataclasses import dataclass

PENALIZACION_SUELTA = 12


@dataclass(frozen=True)
class Silla:
    id: int
    numero: int
    puntaje: int


@dataclass
class Bloque:
    seccion: int
    fila: int
    sillas: list
    puntaje_vista: float
    sillas_sueltas: int
    puntaje: float


def mejor_bloque(filas, ocupadas, cantidad):
    """filas: [(seccion, fila, [Silla, ...] sorted by numero)]; ocupadas: set of seat ids.

    Returns (Bloque or None, number of candidate blocks evaluated).
    """
    mejor = None
    evaluados = 0
    for seccion, fila, sillas in filas:
        n = len(sillas)
        i = 0
        while i < n:
            if sillas[i].id in ocupadas:
                i += 1
                continue
            j = i
            while j < n and sillas[j].id not in ocupadas:
                j += 1
            # sillas[i:j] is a run of free, adjacent seats (sections are separated by aisles).
            if j - i >= cantidad:
                suma = sum(s.puntaje for s in sillas[i : i + cantidad])
                for inicio in range(i, j - cantidad + 1):
                    if inicio > i:
                        suma += sillas[inicio + cantidad - 1].puntaje - sillas[inicio - 1].puntaje
                    evaluados += 1
                    sueltas = (inicio - i == 1) + (j - (inicio + cantidad) == 1)
                    promedio = suma / cantidad
                    puntaje = promedio - PENALIZACION_SUELTA * sueltas
                    if mejor is None or puntaje > mejor.puntaje:
                        mejor = Bloque(seccion, fila, sillas[inicio : inicio + cantidad], promedio, sueltas, puntaje)
            i = j
    return mejor, evaluados
