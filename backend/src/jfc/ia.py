"""Model access shared by the AI features (name moderation and the ticketing agent).

Both features are written against the Bedrock Converse request/response shape, so the callers
(`moderacion.py`, `conversacion.py`) don't know which provider answers. `cliente()` returns an object
with a `converse(**kwargs)` method and picks the provider from `IA_PROVEEDOR`:

- "bedrock":   the bedrock-runtime client itself (needs model access and quota in the AWS account).
- "anthropic": `ClienteClaude`, which translates the same call to the Claude API (needs an API key).

Clients are created lazily and kept at module level: importing this module costs nothing in tests
and a warm Lambda container reuses the connection.
"""

import json
import logging
import os

log = logging.getLogger()

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        if os.environ.get("IA_PROVEEDOR", "bedrock") == "anthropic":
            _cliente = ClienteClaude()
        else:
            import boto3
            from botocore.config import Config

            # The HTTP API cuts an integration off at 30 s, so a slow model call must fail before that.
            _cliente = boto3.client(
                "bedrock-runtime",
                config=Config(connect_timeout=3, read_timeout=20, retries={"max_attempts": 2, "mode": "standard"}),
            )
    return _cliente


def id_de_modelo(modelo):
    """Claude API id for a model id that may be a Bedrock inference profile ("us.anthropic.claude-x")."""
    return modelo.rsplit("anthropic.", 1)[-1]


# ─────────────────────────────────────────────── Converse → Messages API

def _contenido_resultado(contenido):
    """Converse tool-result content ([{"json": …} | {"text": …}]) → the text the Claude API takes."""
    partes = []
    for bloque in contenido or []:
        if "json" in bloque:
            partes.append(json.dumps(bloque["json"], ensure_ascii=False))
        elif "text" in bloque:
            partes.append(bloque["text"])
    return "\n".join(partes) or "{}"


def _bloque(bloque):
    if "text" in bloque:
        return {"type": "text", "text": bloque["text"]}
    if "toolUse" in bloque:
        uso = bloque["toolUse"]
        return {"type": "tool_use", "id": uso["toolUseId"], "name": uso["name"], "input": uso.get("input") or {}}
    if "toolResult" in bloque:
        res = bloque["toolResult"]
        salida = {"type": "tool_result", "tool_use_id": res["toolUseId"], "content": _contenido_resultado(res.get("content"))}
        if res.get("status") == "error":
            salida["is_error"] = True
        return salida
    raise ValueError("bloque de mensaje no soportado")


def _herramienta(herramienta):
    spec = herramienta["toolSpec"]
    return {"name": spec["name"], "description": spec.get("description", ""), "input_schema": spec["inputSchema"]["json"]}


def peticion_claude(modelId, messages, system=None, toolConfig=None, inferenceConfig=None):
    """Keyword arguments for `anthropic.Anthropic().messages.create` equivalent to a Converse call."""
    modelo = id_de_modelo(modelId)
    args = {
        "model": modelo,
        "max_tokens": (inferenceConfig or {}).get("maxTokens", 1024),
        "messages": [{"role": m["role"], "content": [_bloque(b) for b in m["content"]]} for m in messages],
    }
    if system:
        args["system"] = "\n\n".join(s["text"] for s in system)
    if toolConfig:
        args["tools"] = [_herramienta(h) for h in toolConfig["tools"]]
        forzada = (toolConfig.get("toolChoice") or {}).get("tool")
        if forzada:
            args["tool_choice"] = {"type": "tool", "name": forzada["name"]}
    # Sonnet 5.5 thinks by default and rejects thinking "disabled"; "between_tools" is its lowest
    # setting, which keeps a chat turn fast. Its reasoning notes aren't part of the reply.
    if modelo.startswith("claude-sonnet-5-5"):
        args["thinking"] = {"type": "between_tools"}
        args["output_config"] = {"effort": "medium"}
    else:
        args["output_config"] = {"effort": "low"}
    return args


def respuesta_converse(mensaje):
    """A Claude API message → the Converse response shape the callers read."""
    contenido = []
    for bloque in mensaje.content:
        if bloque.type == "text":
            contenido.append({"text": bloque.text})
        elif bloque.type == "tool_use":
            contenido.append({"toolUse": {"toolUseId": bloque.id, "name": bloque.name, "input": bloque.input}})
        # thinking blocks are dropped: only text and tool calls travel in the history
    if mensaje.stop_reason == "refusal":
        log.warning("el modelo rechazó la solicitud: %s", getattr(mensaje, "stop_details", None))
    return {
        "output": {"message": {"role": "assistant", "content": contenido}},
        "stopReason": "tool_use" if mensaje.stop_reason == "tool_use" else "end_turn",
    }


class ClienteClaude:
    """Speaks the Claude API through the same `converse` call the Bedrock client has."""

    def __init__(self, sdk=None):
        self._sdk = sdk

    @property
    def sdk(self):
        if self._sdk is None:
            import anthropic

            # Reads ANTHROPIC_API_KEY. Same budget as the Bedrock client: fail before API Gateway's 30 s.
            self._sdk = anthropic.Anthropic(timeout=anthropic.Timeout(20.0, connect=3.0), max_retries=1)
        return self._sdk

    def converse(self, **kwargs):
        return respuesta_converse(self.sdk.messages.create(**peticion_claude(**kwargs)))
