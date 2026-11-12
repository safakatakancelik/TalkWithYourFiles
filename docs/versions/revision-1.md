# Talk With Your Files: revision 1

This page records the app as it was before revision 2, at commit `174f49e` on `main`.
Revision 2 started by removing all of this code. To see it, check out that commit:

```
git checkout 174f49e
```

## Lineage

- **2023, tag `v1.0.0`**: the original app, built before ChatGPT could take file uploads. It used LangChain, Streamlit and OpenAI.
- **2026-10, PR #9 "v2"**: a rewrite that kept the original layout on a current stack: Anthropic and OpenRouter as LLM providers, LangChain 1.x and Streamlit 1.66. This page describes this version.

## What it is

Talk With Your Files is an open source web app (MIT license) for asking questions about your own documents.
You upload PDF, DOCX, TXT or CSV files, ask a question, and an LLM answers using only the most relevant parts of those files.
The app runs locally or in Docker. You bring your own API key.

## What it does for the user

The interface has three tabs:

1. **Chat Bot**: a plain conversation with the LLM. The system prompt describes the app, and the most recent N messages are sent with each request.
2. **QA Chain**: upload files, ask a question, then press Run. The answer appears with the chunks that were retrieved and the number of tokens used. Two options:
   - **Standalone**: the answer appears in this tab only.
   - **Integrated into the chatbot**: the answer is also posted to the chat so you can keep discussing it.
3. **Active Params**: a read-only view of every current parameter.

From the sidebar you add API keys, pick a provider and type a model name.
An "Advanced Parameters" panel sets chunk size, chunk overlap, the number of top chunks, max response tokens, the context window and max files. It also shows bars for how much of the context window the last run used on context, the question and the completion.

## How it works

It is a simple RAG pipeline that runs once per question. There are no agents and no tools.

```
files (name, bytes)
  -> FileHandlerFactory      extract text (pypdf, python-docx, utf-8)
  -> split_text              RecursiveCharacterTextSplitter (size/overlap in characters)
  -> build_index             SemanticIndex (embeddings + InMemoryVectorStore)
                             or KeywordIndex (BM25Plus)
                             cached in the session, keyed by a hash of the files and settings
  -> index.search(q, k)      top-k chunks
  -> run_qa_chain            puts the chunks into one prompt; answers only from that context
  -> QAResult                answer, chunks, token usage breakdown
```

- **Retrieval choice**: Anthropic has no embeddings API. With an OpenRouter key, retrieval uses `openai/text-embedding-3-small` embeddings through OpenRouter. With only an Anthropic key, it falls back to BM25 keyword search.
- **Token usage**: the totals come from the provider's `usage_metadata`. The split between context and question is estimated from each part's share of the characters.
- **Storage**: everything stays in memory for the browser session. Nothing is saved, and the index is rebuilt whenever the files or settings change.
- **API keys**: keys come from `.env` or the environment first, otherwise from the sidebar. Keys typed in the sidebar are checked with a cheap API call and are never written to `os.environ` or to disk.

## Code layout

| Path | Role |
|---|---|
| `TalkWithYourFiles/streamlit_interface.py` | Entry point. Builds the page and tabs and wires the parts together. |
| `TalkWithYourFiles/flow_coordinator.py` | Runs the pipeline independently of the GUI. `run(files, question)`, `chat(history)` and `FlowError` for messages shown to the user. |
| `TalkWithYourFiles/parameter_controller.py` | A registry of typed parameters with defaults and min/max limits. |
| `backend_utils/providers.py` | The only module that knows the providers: chat model through `init_chat_model`, OpenRouter embeddings, key validation. |
| `backend_utils/file_handlers.py` | A factory with one handler per file extension. |
| `backend_utils/text_processor.py` | Splitting, plus the semantic and keyword indexes behind one `search()` interface. |
| `backend_utils/qa_chain.py` | The prompt, the LLM call and the token breakdown. |
| `backend_utils/chatbot.py` | The chat system prompt and the history window. |
| `streamlit_modules/*` | Sidebar, tabs, chat, sliders and session state. |
| `tests/` | pytest with a fake LLM: backend, providers, and the Streamlit `AppTest` smoke tests. |
| `Dockerfile`, `.github/workflows/tests.yml` | Python 3.12 image on port 8501. CI runs on push and every week. |

Stack: Python 3.10+, Streamlit, LangChain (core, text-splitters, anthropic, openrouter), rank-bm25, pypdf, python-docx and python-dotenv.

## Limits of this version, which revision 2 replaces

- Retrieval runs once per question, with no agent, planning or tool use.
- The chat and the QA chain are separate flows. They are joined only by pasting a QA answer into the chat.
- Answers don't say which file a chunk came from.
- Nothing persists: files are re-read and the index is rebuilt in every session.
- The UI is Streamlit and is tied to its rerun model.
- Answers are not streamed.

Ideas from the old `TODO.md`: stream responses token by token, support local models through Ollama, show which file each chunk came from, and estimate the cost of each run.
