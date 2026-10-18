import streamlit as st

from flow_coordinator import FlowError


AVATARS = {"ai": "🧙‍♂️", "human": "👀"}


def main_chat(param_controller, flow_coordinator, has_llm):
    chat_placeholder = st.container()

    with chat_placeholder:
        for role, text in st.session_state.history:
            with st.chat_message(role, avatar=AVATARS[role]):
                st.markdown(text)

    human_prompt = st.chat_input("Chat", key="human_prompt", disabled=not has_llm)
    if human_prompt:
        st.session_state.history.append(("human", human_prompt))
        with chat_placeholder:
            with st.chat_message("human", avatar=AVATARS["human"]):
                st.markdown(human_prompt)
            with st.spinner("Thinking..."):
                try:
                    reply, tokens = flow_coordinator.chat(st.session_state.history)
                except FlowError as e:
                    st.session_state.history.pop()
                    st.error(str(e))
                    return
        st.session_state.history.append(("ai", reply))
        st.session_state.token_count += tokens
        st.rerun()

    if has_llm:
        in_context = min(len(st.session_state.history), param_controller.get_value('chat_history_messages'))
        st.caption(
            f"Used {st.session_state.token_count} tokens · "
            f"{in_context} recent messages are sent to the model with each request"
        )


############# Helper Functions
def integrate_chain_into_chat(user_question, answer):
    """Adds a QA chain result to the chat, so the chatbot can discuss it further."""
    st.session_state.history.append((
        "ai",
        f"Here's the result of your QA Chain usage: \n\n"
        f"**Your question:** {user_question} \n\n"
        f"**Answer:** {answer} \n\n"
        f"I hope this helps you! I'm here to further discuss the topic or for any questions."
    ))
