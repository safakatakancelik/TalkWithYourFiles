import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from backend_utils import providers
from backend_utils.chatbot import chat
from backend_utils.file_handlers import FileHandlerFactory
from backend_utils.qa_chain import QAResult, run_qa_chain
from backend_utils.text_processor import build_index, split_text
from parameter_controller import ParameterController


"""
Flow_coordinator.py serves as the central orchestration module of the application. It acts as a bridge between
the user interface & the underlying functionalities of the backend_utils modules.
It doesn't depend on any GUI framework: as long as you pass files as (name, bytes) pairs and a question,
run() will serve its purpose. Streamlit is just one possible front end.

## Backend Utils
- providers.py: creates chat & embeddings models for Anthropic / OpenRouter.
- file_handlers.py: extracts text from PDF, DOCX, TXT, CSV.
- text_processor.py: splits the text into chunks & builds a searchable index (embeddings or keyword).
- qa_chain.py: answers the question from the most related chunks & reports token usage.
- chatbot.py: the conversation with the LLM.

## Param Controller
An instance of ParameterController is passed to the flow coordinator to control the behaviour of the application.

## run() Function
Validate input > read files > split into chunks > build index (cached) > retrieve related chunks > run the QA chain.
If a step fails, a FlowError with a user friendly message is raised.
"""


class FlowError(Exception):
    """An error with a message that can be shown to the user as is."""


class FlowCoordinator:
    def __init__(self, param_controller: ParameterController, api_keys: Dict[str, str], cache: Optional[dict] = None) -> None:
        """
        Args:
            param_controller: the app parameters.
            api_keys: provider id -> API key, only for the providers the user has keys for.
            cache: a dict that survives between runs (e.g. Streamlit's session state), used to avoid
                   re-embedding the same files for every question.
        """
        self.param_controller = param_controller
        self.api_keys = api_keys
        self.cache = cache if cache is not None else {}

    def get_llm(self):
        provider_id = self.param_controller.get_value('provider')
        if not self.api_keys.get(provider_id):
            raise FlowError(f"Please add a {providers.PROVIDERS[provider_id].label} API key in the sidebar.")
        return providers.get_chat_model(
            provider_id,
            self.param_controller.get_value('model_name'),
            self.api_keys[provider_id],
            self.param_controller.get_value('max_response_tokens'),
        )

    def run(self, files: List[Tuple[str, bytes]], user_question: str) -> QAResult:
        """Main function to process uploaded files and the user's question, and run the QA chain."""
        self.validate_input(files, user_question)
        index = self.get_index(files)
        chunks = index.search(user_question, self.param_controller.get_value('top_related_chunks'))
        if not chunks:
            raise FlowError("Couldn't find any relevant chunks for your question. Please try asking a different question.")
        try:
            return run_qa_chain(self.get_llm(), chunks, user_question)
        except FlowError:
            raise
        except Exception as e:
            logging.exception("QA chain failed")
            raise FlowError(f"The model call failed: {e}") from e

    def chat(self, history: List[Tuple[str, str]]) -> Tuple[str, int]:
        try:
            return chat(self.get_llm(), history, self.param_controller.get_value('chat_history_messages'))
        except FlowError:
            raise
        except Exception as e:
            logging.exception("Chat failed")
            raise FlowError(f"The model call failed: {e}") from e

    def validate_input(self, files: List[Tuple[str, bytes]], user_question: str) -> None:
        if not user_question or not files:
            raise FlowError("Both files and a question are required.")
        max_files = self.param_controller.get_value('max_files')
        if len(files) > max_files:
            raise FlowError(f"Please upload a maximum of {max_files} files.")

    def read_files(self, files: List[Tuple[str, bytes]]) -> str:
        texts = []
        for name, data in files:
            try:
                text = FileHandlerFactory.get_file_handler(name).read_file(data)
            except Exception as e:
                logging.exception("Reading %s failed", name)
                raise FlowError(f"Couldn't read {name}: {e}") from e
            if not text.strip():
                raise FlowError(f"No text could be extracted from {name}. Please ensure the file is not encrypted, scanned or corrupted.")
            texts.append(f"[{name}]\n{text}")
        return "\n\n".join(texts)

    def get_index(self, files: List[Tuple[str, bytes]]):
        """Builds the search index for the files, or reuses it if files & settings haven't changed."""
        chunk_size = self.param_controller.get_value('chunk_size')
        chunk_overlap = self.param_controller.get_value('chunk_overlap')
        retrieval = self.param_controller.get_value('retrieval')

        fingerprint = hashlib.sha256()
        for name, data in files:
            fingerprint.update(name.encode())
            fingerprint.update(hashlib.sha256(data).digest())
        fingerprint.update(f"{chunk_size}|{chunk_overlap}|{retrieval}".encode())
        key = fingerprint.hexdigest()

        if self.cache.get('index_key') == key:
            return self.cache['index']

        chunks = split_text(self.read_files(files), chunk_size, chunk_overlap)
        if not chunks:
            raise FlowError("Couldn't split the text into chunks. Please try again with different files.")

        embeddings = None
        if retrieval != providers.KEYWORD_RETRIEVAL:
            embeddings = providers.get_embeddings(retrieval, self.api_keys[retrieval])
        try:
            index = build_index(chunks, embeddings)
        except Exception as e:
            logging.exception("Building the index failed")
            raise FlowError(f"Couldn't create embeddings from the text: {e}") from e

        self.cache['index_key'] = key
        self.cache['index'] = index
        return index
