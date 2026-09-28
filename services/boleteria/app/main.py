"""Junior FC · Boletería — the containerized ticketing service (runs on OpenShift).

Public (through API Gateway, no login):
  GET    /boleteria/partidos
  GET    /boleteria/partidos/{id}/disponibilidad
Signed in (API Gateway verified the Cognito token and set x-user-sub):
  POST   /boleteria/reservas                    best block of seats, held for 10 minutes
  GET    /boleteria/reservas/activa?partido_id=  the user's current hold, if any
  POST   /boleteria/reservas/{id}/confirmar     simulated payment -> tickets with QR
  DELETE /boleteria/reservas/{id}               release a hold
  GET    /boleteria/mis-boletas
Probes (not routed in API Gateway): GET /healthz (alive), GET /readyz (seat map loaded)
"""

import logging
from contextlib import asynccontextmanager

import pymysql
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import config, reservas
from app.errores import ErrorApi
from app.estadio import estadio
from app.expirador import Expirador
from app.seguridad import Usuario, exigir_gateway, usuario_actual

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("boleteria")

expirador = Expirador()


@asynccontextmanager
async def lifespan(_app):
    estadio.cargar_con_reintentos()
    expirador.start()
    log.info("boletería iniciada en el pod %s", config.POD)
    yield
    expirador.detener()


app = FastAPI(title="Junior FC · Boletería", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def servido_por(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Served-By"] = config.POD
    return respuesta


def _error(status, codigo, mensaje, **detalle):
    return JSONResponse(status_code=status, content={"error": {"code": codigo, "message": mensaje, **detalle}})


@app.exception_handler(ErrorApi)
async def _error_api(_request, e: ErrorApi):
    return _error(e.status, e.codigo, e.mensaje, **e.detalle)


@app.exception_handler(RequestValidationError)
async def _datos_invalidos(_request, e: RequestValidationError):
    campos = sorted({str(err["loc"][-1]) for err in e.errors()})
    return _error(400, "DATOS_INVALIDOS", f"Revisa estos datos: {', '.join(campos)}.")


@app.exception_handler(pymysql.Error)
async def _sin_base(_request, e: pymysql.Error):
    log.exception("error de base de datos", exc_info=e)
    return _error(503, "BASE_DE_DATOS_NO_DISPONIBLE", "La boletería no puede consultar la base de datos en este momento.")


@app.get("/healthz")
def healthz():
    return {"ok": True, "pod": config.POD, "lider_expirador": expirador.lider}


@app.get("/readyz")
def readyz():
    if not estadio.cargado:
        return JSONResponse(status_code=503, content={"ok": False, "pod": config.POD})
    return {"ok": True, "pod": config.POD, "sillas_en_memoria": len(estadio.ubicacion)}


class NuevaReserva(BaseModel):
    partido_id: int
    tribuna: str = Field(min_length=1, max_length=12)
    cantidad: int = Field(ge=1, le=config.MAX_BOLETAS_POR_COMPRA)
    precio_max: int | None = Field(default=None, ge=0)


boleteria = APIRouter(prefix="/boleteria", dependencies=[Depends(exigir_gateway)])


@boleteria.get("/partidos")
def listar_partidos():
    return {"data": reservas.partidos()}


@boleteria.get("/partidos/{partido_id}/disponibilidad")
def ver_disponibilidad(partido_id: int):
    return {"data": reservas.disponibilidad(partido_id)}


@boleteria.post("/reservas", status_code=201)
def crear_reserva(datos: NuevaReserva, usuario: Usuario = Depends(usuario_actual)):
    return {"data": reservas.reservar(usuario, datos.partido_id, datos.tribuna, datos.cantidad, datos.precio_max)}


@boleteria.get("/reservas/activa")
def reserva_activa(partido_id: int, usuario: Usuario = Depends(usuario_actual)):
    return {"data": reservas.activa(usuario, partido_id)}


@boleteria.post("/reservas/{reserva_id}/confirmar")
def confirmar_reserva(reserva_id: int, usuario: Usuario = Depends(usuario_actual)):
    return {"data": reservas.confirmar(usuario, reserva_id)}


@boleteria.delete("/reservas/{reserva_id}", status_code=204)
def cancelar_reserva(reserva_id: int, usuario: Usuario = Depends(usuario_actual)):
    reservas.cancelar(usuario, reserva_id)
    return Response(status_code=204)


@boleteria.get("/mis-boletas")
def ver_mis_boletas(usuario: Usuario = Depends(usuario_actual)):
    return {"data": reservas.mis_boletas(usuario)}


app.include_router(boleteria)
