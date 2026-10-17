import io

import pytest
from docx import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from backend_utils import providers
from backend_utils.file_handlers import FileHandlerFactory
from backend_utils.qa_chain import run_qa_chain
from backend_utils.text_processor import KeywordIndex, SemanticIndex, split_text
from flow_coordinator import FlowCoordinator, FlowError
from parameter_controller import ParameterController


def fake_llm(text="The answer.", input_tokens=100, output_tokens=10):
    message = AIMessage(text, usage_metadata={
        "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens})
    return GenericFakeChatModel(messages=iter([message]))


def docx_bytes(text):
    doc = Document()
    doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_file_handlers():
    assert FileHandlerFactory.get_file_handler("a.TXT").read_file("héllo".encode()) == "héllo"
    assert "1,2" in FileHandlerFactory.get_file_handler("a.csv").read_file(b"a,b\n1,2")
    assert FileHandlerFactory.get_file_handler("a.docx").read_file(docx_bytes("from word")) == "from word"
    with pytest.raises(ValueError):
        FileHandlerFactory.get_file_handler("a.exe")


def test_split_and_indexes():
    chunks = split_text("cats purr. " * 50 + "dogs bark loudly. " * 50, chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 3
    assert "dogs" in KeywordIndex(chunks).search("why do dogs bark", k=1)[0]
    assert len(SemanticIndex(chunks, DeterministicFakeEmbedding(size=16)).search("dogs", k=2)) == 2


def test_qa_chain_usage_breakdown():
    result = run_qa_chain(fake_llm(), ["some context " * 20], "a question?")
    assert result.answer == "The answer."
    assert result.usage.context_tokens + result.usage.question_tokens == 100
    assert result.usage.context_tokens > result.usage.question_tokens
    assert result.usage.completion_tokens == 10


def test_parameter_validation():
    params = ParameterController()
    params.setup_default_parameters()
    params.set_parameter("chunk_size", 500)
    assert params.get_value("chunk_size") == 500
    with pytest.raises(ValueError):
        params.set_parameter("chunk_size", 10)
    with pytest.raises(TypeError):
        params.set_parameter("chunk_size", "big")
    with pytest.raises(KeyError):
        params.set_parameter("nope", 1)


def test_pick_retrieval_provider():
    assert providers.pick_retrieval_provider({"anthropic": "k"}) == providers.KEYWORD_RETRIEVAL
    assert providers.pick_retrieval_provider({"anthropic": "k", "openrouter": "k"}) == "openrouter"


def test_flow_coordinator_runs_and_caches_index(monkeypatch):
    monkeypatch.setattr(providers, "get_chat_model", lambda *args: fake_llm("Dogs bark."))
    params = ParameterController()
    params.setup_default_parameters()
    params.set_parameter("provider", "anthropic")
    params.set_parameter("model_name", "any")
    cache = {}
    coordinator = FlowCoordinator(params, {"anthropic": "k"}, cache=cache)
    files = [("pets.txt", b"cats purr. " * 100 + b"dogs bark. " * 100)]

    result = coordinator.run(files, "what do dogs do?")
    assert result.answer == "Dogs bark."
    first_index = cache["index"]
    coordinator.run(files, "and cats?")
    assert cache["index"] is first_index  # same files & settings -> not rebuilt

    with pytest.raises(FlowError):
        coordinator.run([], "question without files")
    with pytest.raises(FlowError):
        coordinator.run([("empty.txt", b"   ")], "q")


def test_missing_key_gives_friendly_error():
    params = ParameterController()
    params.setup_default_parameters()
    params.set_parameter("provider", "openrouter")
    with pytest.raises(FlowError, match="OpenRouter API key"):
        FlowCoordinator(params, {}).chat([("human", "hi")])


def test_missing_usage_is_flagged():
    llm = GenericFakeChatModel(messages=iter([AIMessage("No usage here.")]))
    result = run_qa_chain(llm, ["context"], "q?")
    assert result.answer == "No usage here."
    assert not result.usage.reported and result.usage.total == 0
