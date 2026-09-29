"""The stadium as data: section layout, per-seat view score, and simulated earlier sales.

Layout (≈46,400 seats, the size of the Estadio Metropolitano):
  Occidental 101–112 and Oriental 201–212: 12 sections × 30 rows × 36 seats (side stands)
  Norte 301–308 and Sur 401–408:            8 sections × 32 rows × 40 seats (behind the goals)
Section 1 of each stand and seat 1 of each row are at the same end, so a seat's position along
the stand is ((orden - 1) * seats + numero) / (sections * seats).
"""

import random

TRIBUNAS = {
    # codigo: (first section, sections, rows, seats per row, side stand?, best possible score)
    "OCCIDENTAL": (101, 12, 30, 36, True, 100),
    "ORIENTAL": (201, 12, 30, 36, True, 92),
    "NORTE": (301, 8, 32, 40, False, 62),
    "SUR": (401, 8, 32, 40, False, 62),
}

# Share of seats already sold per stand before online sales open (season tickets, box office).
# The Sur is where the club's supporters' group stands, so it sells out first.
_OCUPACION_BASE = {"OCCIDENTAL": 0.50, "ORIENTAL": 0.45, "NORTE": 0.55, "SUR": 0.78}
# Demand per match id: 1 is the clásico against Nacional.
_DEMANDA = {1: 1.15, 2: 0.9, 3: 0.7}


def silla_id(seccion, fila, numero):
    return seccion * 10000 + fila * 100 + numero


def puntaje_vista(lateral, maximo, orden, secciones, fila, filas, numero, sillas):
    """0–maximo. Side stands reward being near midfield; goal stands mostly reward height."""
    x = ((orden - 1) * sillas + numero - 0.5) / (secciones * sillas)
    centralidad = 1 - abs(x - 0.5) * 2
    fila_ideal = filas * 0.4
    altura = 1 - abs(fila - fila_ideal) / filas
    puntaje = 0.65 * centralidad + 0.35 * altura if lateral else 0.3 * centralidad + 0.7 * altura
    return round(max(0.0, min(1.0, puntaje)) * maximo)


def secciones():
    """(codigo, tribuna, orden) for every section."""
    for tribuna, (primera, cantidad, *_resto) in TRIBUNAS.items():
        for orden in range(1, cantidad + 1):
            yield primera + orden - 1, tribuna, orden


def sillas():
    """(id, tribuna, seccion, fila, numero, puntaje_vista) for every seat."""
    for tribuna, (primera, cantidad, filas, por_fila, lateral, maximo) in TRIBUNAS.items():
        for orden in range(1, cantidad + 1):
            seccion = primera + orden - 1
            for fila in range(1, filas + 1):
                for numero in range(1, por_fila + 1):
                    yield (
                        silla_id(seccion, fila, numero),
                        tribuna,
                        seccion,
                        fila,
                        numero,
                        puntaje_vista(lateral, maximo, orden, cantidad, fila, filas, numero, por_fila),
                    )


def ventas_previas(partido_id):
    """Seat ids already sold for a match, deterministic per match so re-seeding gives the same map.

    Seats are sold in runs of 1–6 (groups of friends), which leaves realistic gaps in each row —
    exactly the situation the best-block search has to handle.
    """
    rng = random.Random(partido_id * 7919)
    demanda = _DEMANDA.get(partido_id, 0.8)
    vendidas = []
    for tribuna, (primera, cantidad, filas, por_fila, _lateral, _maximo) in TRIBUNAS.items():
        for orden in range(1, cantidad + 1):
            seccion = primera + orden - 1
            centralidad = 1 - abs((orden - 0.5) / cantidad - 0.5) * 2
            ocupacion = _OCUPACION_BASE[tribuna] * demanda + 0.15 * centralidad + rng.uniform(-0.15, 0.15)
            ocupacion = max(0.05, min(0.93, ocupacion))
            for fila in range(1, filas + 1):
                numero = 1
                while numero <= por_fila:
                    tramo = rng.randint(1, 6)
                    if rng.random() < ocupacion:
                        for n in range(numero, min(numero + tramo, por_fila + 1)):
                            vendidas.append(silla_id(seccion, fila, n))
                    numero += tramo
    return vendidas
