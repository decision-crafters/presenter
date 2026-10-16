from llama_index.core.tools import FunctionTool

from providers import build_llm, force_tool_required


def _fake_tool():
    return FunctionTool.from_defaults(fn=lambda x: x, name="f", description="d")


def test_force_tool_required_env(monkeypatch):
    monkeypatch.delenv("PRESENTER_TOOL_REQUIRED", raising=False)
    assert force_tool_required() is True
    for value in ("0", "false", "no", "off", "FALSE"):
        monkeypatch.setenv("PRESENTER_TOOL_REQUIRED", value)
        assert force_tool_required() is False, value
    monkeypatch.setenv("PRESENTER_TOOL_REQUIRED", "1")
    assert force_tool_required() is True


def test_ollama_cloud_forces_tool_required(monkeypatch):
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    monkeypatch.delenv("PRESENTER_TOOL_REQUIRED", raising=False)
    llm = build_llm("ollama-cloud")
    kwargs = llm._prepare_chat_with_tools([_fake_tool()], tool_required=False)
    assert kwargs["tool_choice"] == "required"


def test_ollama_cloud_can_opt_out(monkeypatch):
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    monkeypatch.setenv("PRESENTER_TOOL_REQUIRED", "0")
    llm = build_llm("ollama-cloud")
    kwargs = llm._prepare_chat_with_tools([_fake_tool()], tool_required=False)
    assert kwargs["tool_choice"] == "auto"
