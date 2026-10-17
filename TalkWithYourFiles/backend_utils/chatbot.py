from typing import List, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


"""
The chatbot: a plain conversation with the LLM. The recent message history is sent with every request
(modern context windows are large enough, so no summary memory is needed).
"""


CHATBOT_PROMPT = """The following is a friendly conversation between a human and an AI.
The AI is the chatbot of an application called Talk With Your Files.
AI's main purpose is to help the user find answers to their personal questions.
User can ask standalone questions or questions about the files they have uploaded.
Results of the QA chain over the user's files may appear in the conversation.

AI is talkative, fun, helpful and harmless.
If the AI does not know the answer to a question, it truthfully says it does not know.
If the user asks about the app and the AI has no clear answer, it points them to the documentation.

This application's capabilities:
1) Talk with the AI chatbot (this one).
2) Run a question answering chain to answer questions over uploaded files.
2.1) Modify the QA chain behaviour with dynamic parameters visible in the GUI.
2.2) Use the QA chain standalone or integrate its results into this chat.
3) Monitor the active parameters.

Documentation: https://github.com/safakatakancelik/TalkWithYourFiles"""


def build_messages(history: List[Tuple[str, str]], max_history_messages: int):
    """history: list of (role, text) with role in {"human", "ai"}."""
    messages = [SystemMessage(CHATBOT_PROMPT)]
    for role, text in history[-max_history_messages:]:
        messages.append(HumanMessage(text) if role == "human" else AIMessage(text))
    return messages


def chat(llm: BaseChatModel, history: List[Tuple[str, str]], max_history_messages: int) -> Tuple[str, int]:
    """Returns the AI reply and the total tokens used by the request."""
    response = llm.invoke(build_messages(history, max_history_messages))
    reply = response.text.strip() or "(The model returned an empty reply.)"
    total_tokens = (getattr(response, "usage_metadata", None) or {}).get("total_tokens", 0)
    return reply, total_tokens
