import os
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jfc import conversacion, ia, moderacion  # noqa: E402


@pytest.fixture(autouse=True)
def sin_cliente_guardado(monkeypatch):
    monkeypatch.setattr(ia, "_cliente", None)
    moderacion._cache.clear()


def test_el_id_de_un_perfil_de_bedrock_se_convierte_al_de_la_api_de_claude():
    assert ia.id_de_modelo("us.anthropic.claude-haiku-5-5") == "claude-haiku-5-5"
    assert ia.id_de_modelo("anthropic.claude-sonnet-5-5") == "claude-sonnet-5-5"
    assert ia.id_de_modelo("claude-sonnet-5-5") == "claude-sonnet-5-5"


def test_el_proveedor_se_elige_por_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("IA_PROVEEDOR", "anthropic")
    assert isinstance(ia.cliente(), ia.ClienteClaude)


def test_la_peticion_traduce_mensajes_herramientas_y_resultados():
    args = ia.peticion_claude(
        modelId="us.anthropic.claude-sonnet-5-5",
        system=[{"text": "Eres Juni."}],
        messages=[
            {"role": "user", "content": [{"text": "hola"}]},
            {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "listar_partidos", "input": {}}}]},
            {"role": "user", "content": [
                {"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"json": {"partidos": [{"rival": "Nacional"}]}}]}},
            ]},
            {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t2", "name": "liberar_reserva", "input": {"reserva_id": 3}}}]},
            {"role": "user", "content": [
                {"toolResult": {"toolUseId": "t2", "status": "error", "content": [{"json": {"error": "NO_ENCONTRADA"}}]}},
            ]},
        ],
        toolConfig={"tools": [{"toolSpec": {"name": "listar_partidos", "description": "d", "inputSchema": {"json": {"type": "object", "properties": {}}}}}]},
        inferenceConfig={"maxTokens": 512},
    )
    assert args["model"] == "claude-sonnet-5-5" and args["max_tokens"] == 512 and args["system"] == "Eres Juni."
    assert args["messages"][0] == {"role": "user", "content": [{"type": "text", "text": "hola"}]}
    assert args["messages"][1]["content"] == [{"type": "tool_use", "id": "t1", "name": "listar_partidos", "input": {}}]
    ok, error = args["messages"][2]["content"][0], args["messages"][4]["content"][0]
    assert ok == {"type": "tool_result", "tool_use_id": "t1", "content": '{"partidos": [{"rival": "Nacional"}]}'}
    assert error["is_error"] is True and "NO_ENCONTRADA" in error["content"]
    assert args["tools"] == [{"name": "listar_partidos", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    assert "tool_choice" not in args


def test_sonnet_apaga_el_razonamiento_con_between_tools():
    args = ia.peticion_claude("claude-sonnet-5-5", [{"role": "user", "content": [{"text": "x"}]}])
    assert args["thinking"] == {"type": "between_tools"}
    assert args["output_config"] == {"effort": "medium"}


def test_haiku_no_manda_thinking_y_usa_poco_esfuerzo():
    args = ia.peticion_claude("claude-haiku-5-5", [{"role": "user", "content": [{"text": "x"}]}])
    assert "thinking" not in args and args["output_config"] == {"effort": "low"}


def test_una_herramienta_forzada_se_traduce_a_tool_choice():
    herramienta = {"toolSpec": {"name": "veredicto", "inputSchema": {"json": {"type": "object"}}}}
    args = ia.peticion_claude(
        "claude-haiku-5-5", [{"role": "user", "content": [{"text": "x"}]}],
        toolConfig={"tools": [herramienta], "toolChoice": {"tool": {"name": "veredicto"}}},
    )
    assert args["tool_choice"] == {"type": "tool", "name": "veredicto"}


def test_un_bloque_desconocido_se_rechaza():
    with pytest.raises(ValueError):
        ia.peticion_claude("claude-haiku-5-5", [{"role": "user", "content": [{"image": {}}]}])


def mensaje(contenido, stop_reason):
    return NS(content=contenido, stop_reason=stop_reason, stop_details=None)


def test_la_respuesta_vuelve_en_formato_converse_sin_el_razonamiento():
    resp = ia.respuesta_converse(mensaje([
        NS(type="thinking", thinking="nota"),
        NS(type="text", text="Voy a buscar."),
        NS(type="tool_use", id="t1", name="listar_partidos", input={}),
    ], "tool_use"))
    assert resp["stopReason"] == "tool_use"
    assert resp["output"]["message"] == {"role": "assistant", "content": [
        {"text": "Voy a buscar."},
        {"toolUse": {"toolUseId": "t1", "name": "listar_partidos", "input": {}}},
    ]}


@pytest.mark.parametrize("motivo", ["end_turn", "max_tokens", "refusal"])
def test_cualquier_otro_fin_de_turno_no_pide_herramientas(motivo):
    assert ia.respuesta_converse(mensaje([NS(type="text", text="listo")], motivo))["stopReason"] == "end_turn"


class SdkFalso:
    def __init__(self, respuesta):
        self.llamadas = []
        self.messages = NS(create=self._crear)
        self.respuesta = respuesta

    def _crear(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuesta


def test_el_cliente_traduce_la_llamada_y_la_respuesta():
    sdk = SdkFalso(mensaje([NS(type="text", text="Hola")], "end_turn"))
    resp = ia.ClienteClaude(sdk).converse(
        modelId="us.anthropic.claude-haiku-5-5", system=[{"text": "s"}], messages=[{"role": "user", "content": [{"text": "hola"}]}],
    )
    assert sdk.llamadas[0]["model"] == "claude-haiku-5-5"
    assert resp["output"]["message"]["content"] == [{"text": "Hola"}]


# The two features end to end through the translation layer, with a scripted Claude API.

def test_la_moderacion_funciona_a_traves_del_cliente_de_claude():
    uso = NS(type="tool_use", id="t1", name="veredicto", input={"categoria": "CLUB_RIVAL", "motivo": "otro club"})
    sdk = SdkFalso(mensaje([uso], "tool_use"))
    assert moderacion.clasificar("MILLONARIOS", ia.ClienteClaude(sdk), "claude-haiku-5-5")[0] == "CLUB_RIVAL"
    assert sdk.llamadas[0]["tool_choice"] == {"type": "tool", "name": "veredicto"}
    assert "<nombre>MILLONARIOS</nombre>" in sdk.llamadas[0]["messages"][0]["content"][0]["text"]


def test_el_agente_responde_a_traves_del_cliente_de_claude():
    sdk = SdkFalso(mensaje([NS(type="text", text="¡Hola! ¿A qué partido quieres ir?")], "end_turn"))
    respuesta, historial, acciones = conversacion.conversar(
        "hola", [], servicios=None, modelo="claude-sonnet-5-5", cliente=ia.ClienteClaude(sdk),
    )
    assert respuesta == "¡Hola! ¿A qué partido quieres ir?" and acciones == []
    assert historial[-1] == {"role": "assistant", "content": [{"text": "¡Hola! ¿A qué partido quieres ir?"}]}
