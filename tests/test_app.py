import os

from streamlit.testing.v1 import AppTest

from backend_utils import providers

APP = os.path.join(os.path.dirname(__file__), "..", "TalkWithYourFiles", "streamlit_interface.py")


def test_app_renders_without_keys(monkeypatch):
    for provider in providers.PROVIDERS.values():
        for var in provider.env_vars:
            monkeypatch.delenv(var, raising=False)
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Chat Bot", "QA Chain", "Active Params"]
    assert any("Add an API key" in info.value for info in app.info)


def test_chat_with_env_key(monkeypatch):
    from test_backend import fake_llm

    for provider in providers.PROVIDERS.values():
        for var in provider.env_vars:
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(providers, "get_chat_model", lambda *args: fake_llm("Hello from the wizard!"))

    app = AppTest.from_file(APP, default_timeout=30).run()
    assert any("key loaded from environment" in s.value for s in app.sidebar.success)
    app.chat_input[0].set_value("hi").run()
    assert not app.exception
    assert any("Hello from the wizard!" in m.markdown[0].value for m in app.chat_message)
