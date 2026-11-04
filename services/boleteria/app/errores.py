class ErrorApi(Exception):
    """Turned into {"error": {"code", "message", ...detalle}} with the given HTTP status."""

    def __init__(self, status, codigo, mensaje, **detalle):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalle = detalle
