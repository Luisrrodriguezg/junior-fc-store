"""The "your seats are about to be released" notice. Pure helpers: no AWS, no database.

Flow (all asynchronous, nothing here runs inside the buyer's request):
  EventBridge, every minute → jfc-avisos-escaner finds holds in their last two minutes
  → one SQS message per hold → jfc-avisos-notificador → email (SES) and the class group (webhook)
"""

import datetime

_ZONA = datetime.timezone(datetime.timedelta(hours=-5))  # Barranquilla


def enmascarar_email(email):
    """lu***@gmail.com — the group chat sees that the notice went out, not whose address it is."""
    if not email or "@" not in email:
        return None
    usuario, dominio = email.rsplit("@", 1)
    return f"{usuario[:2]}***@{dominio}"


def moneda(valor):
    return "$" + f"{int(valor):,}".replace(",", ".")


def hora_local(iso_utc):
    fecha = datetime.datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(_ZONA)
    return fecha.strftime("%H:%M")


def minutos_restantes(segundos):
    return max(1, round(segundos / 60))


def mensaje(aviso, segundos):
    """(asunto, texto) for a hold that has `segundos` left."""
    minutos = minutos_restantes(segundos)
    plural = "minuto" if minutos == 1 else "minutos"
    sillas = f"{aviso['cantidad']} boleta{'s' if aviso['cantidad'] != 1 else ''}"
    asunto = f"Tu reserva vence en {minutos} {plural} · Junior vs {aviso['rival']}"
    texto = (
        f"Tus {sillas} para Junior vs {aviso['rival']} ({aviso['tribuna'].title()}, {moneda(aviso['total'])}) "
        f"se liberan a las {hora_local(aviso['expira_en'])} (hora de Barranquilla), en unos {minutos} {plural}.\n"
        f"Confirma tu compra en la tienda antes de que otra persona se quede con esas sillas.\n"
        f"Reserva {aviso['codigo']}."
    )
    return asunto, texto


def mensaje_grupo(aviso, segundos):
    """Same notice for the group chat: no address, no price."""
    minutos = minutos_restantes(segundos)
    destino = enmascarar_email(aviso.get("email")) or "un hincha"
    return (
        f"⏰ La reserva {aviso['codigo']} de {destino} (Junior vs {aviso['rival']}, "
        f"{aviso['cantidad']} boleta{'s' if aviso['cantidad'] != 1 else ''}) vence en ~{minutos} min."
    )
