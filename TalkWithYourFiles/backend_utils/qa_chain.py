from dataclasses import dataclass
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate


"""
In this file the question answering (QA) chain is implemented: the retrieved chunks are "stuffed" into a prompt
together with the user's question and sent to the LLM.

It also returns a token usage breakdown, so the GUI can show what the context window was spent on.
Token totals come from the provider itself (usage_metadata), so they're accurate for every provider.
The split of the input between "context" and "question + instructions" is estimated by character share.
"""


QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You answer questions about the user's files. Use only the pieces of context below. "
     "If the answer isn't in the context, say you don't know rather than making something up.\n\n"
     "Context:\n{context}"),
    ("human", "{question}"),
])


@dataclass
class TokenUsage:
    context_tokens: int = 0
    question_tokens: int = 0     # question + prompt instructions
    completion_tokens: int = 0
    reported: bool = True        # False if the provider didn't return token usage

    @property
    def total(self) -> int:
        return self.context_tokens + self.question_tokens + self.completion_tokens


@dataclass
class QAResult:
    answer: str
    chunks: List[str]
    usage: TokenUsage


def run_qa_chain(llm: BaseChatModel, chunks: List[str], question: str) -> QAResult:
    context = "\n\n---\n\n".join(chunks)
    messages = QA_PROMPT.format_messages(context=context, question=question)
    response = llm.invoke(messages)

    answer = response.text.strip()
    if not answer:
        answer = "The model returned an empty answer (it may have declined or run out of tokens)."

    return QAResult(answer=answer, chunks=chunks, usage=_usage_breakdown(response, messages, context))


def _usage_breakdown(response, messages, context: str) -> TokenUsage:
    metadata = getattr(response, "usage_metadata", None)
    if not metadata:
        return TokenUsage(reported=False)
    input_tokens = metadata.get("input_tokens", 0)
    output_tokens = metadata.get("output_tokens", 0)

    prompt_chars = sum(len(m.text) for m in messages) or 1
    context_tokens = round(input_tokens * len(context) / prompt_chars)
    return TokenUsage(
        context_tokens=context_tokens,
        question_tokens=input_tokens - context_tokens,
        completion_tokens=output_tokens,
    )
