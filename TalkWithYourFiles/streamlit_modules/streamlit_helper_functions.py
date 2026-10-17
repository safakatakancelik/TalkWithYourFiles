import copy
import hashlib

import streamlit as st

from backend_utils import providers


##########################################################
### SESSION STATE
##########################################################

WELCOME_MESSAGE = (
    "Hi there! I'm your AI assistant while using the app Talk With Your Files! \n\n"
    "To start, add an API key on the sidebar on the left."
)


def initialize_session_state():
    st.session_state.setdefault("entered_api_keys", {})   # provider id -> key typed in the sidebar
    st.session_state.setdefault("key_validation", {})     # provider id -> (key hash, is valid)
    st.session_state.setdefault("history", [("ai", WELCOME_MESSAGE)])
    st.session_state.setdefault("token_count", 0)
    st.session_state.setdefault("qa_cache", {})
    st.session_state.setdefault("last_qa_result", None)


def sync_parameters_from_widgets(param_controller):
    """Widgets keep their values in session state between reruns. Load them into the param controller
    up front, so every tab sees the same values regardless of the order the widgets are drawn in."""
    for name in param_controller.get_all_parameters():
        key = f"param_{name}"
        if key in st.session_state:
            param_controller.set_parameter(name, st.session_state[key])


##########################################################
### AUTHORIZATION
##########################################################

def api_key_input(provider_id):
    """Shows the key status / input for one provider. Returns the usable key or None."""
    provider = providers.PROVIDERS[provider_id]

    env_key = providers.env_api_key(provider_id)
    if env_key:
        st.sidebar.success(f"{provider.label}: key loaded from environment")
        return env_key

    key = st.sidebar.text_input(
        f"{provider.label} API key",
        type="password",
        key=f"api_key_{provider_id}",
        help=f"Get one at {provider.key_help_url}",
    ).strip()
    if not key:
        return None

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    cached = st.session_state.key_validation.get(provider_id)
    if not cached or cached[0] != key_hash:
        with st.sidebar:
            with st.spinner(f"Validating {provider.label} key..."):
                cached = (key_hash, providers.validate_key(provider_id, key))
        st.session_state.key_validation[provider_id] = cached

    if cached[1]:
        st.sidebar.success(f"{provider.label}: validated")
        return key
    st.sidebar.error(f"{provider.label}: not validated")
    return None


##########################################################
### QA CHAIN
##########################################################

def create_slider_with_param_controller(param_controller, param_name, slider_title):
    param_dict = param_controller.get_parameter(param_name)
    value = st.slider(
        slider_title,
        min_value=param_dict['min'],
        max_value=param_dict['max'],
        value=param_dict['value'],
        help=param_dict['description'],
        key=f"param_{param_name}",
    )
    param_controller.set_parameter(param_name, value)
    return value


def create_number_input_with_param_controller(param_controller, param_name, title):
    param_dict = param_controller.get_parameter(param_name)
    value = st.number_input(
        title,
        min_value=param_dict['min'],
        max_value=param_dict['max'],
        value=param_dict['value'],
        step=1000 if param_dict['max'] > 10000 else 1,
        help=param_dict['description'],
        key=f"param_{param_name}",
    )
    param_controller.set_parameter(param_name, int(value))
    return value


def advanced_parameters_section(param_controller):
    #### TOP ROW TO SHOW AND ALLOW DYNAMIC PARAMETERS
    column_chunk_size, column_chunk_overlap, column_top_related_chunks, column_max_tokens = st.columns(4)

    with column_chunk_size:
        create_slider_with_param_controller(param_controller, "chunk_size", "Chunk Size")
    with column_chunk_overlap:
        create_slider_with_param_controller(param_controller, "chunk_overlap", "Chunk Overlap")
    with column_top_related_chunks:
        create_slider_with_param_controller(param_controller, "top_related_chunks", "Top Related Chunks to Retrieve")
    with column_max_tokens:
        create_slider_with_param_controller(param_controller, "max_response_tokens", "Max Response Tokens")

    ##### SECOND ROW: CONTEXT WINDOW, EXPLANATION, TOKEN USAGE OF THE LAST RUN
    column_limits, column_details, column_token_usage = st.columns(3)

    with column_limits:
        create_number_input_with_param_controller(param_controller, "context_window", "Model Context Window (tokens)")
        create_number_input_with_param_controller(param_controller, "max_files", "Max Files per Question")

    with column_details:
        st.write(f"Model: {param_controller.get_value('model_name') or '-'}")
        st.write(f"Retrieval: {retrieval_label(param_controller.get_value('retrieval'))}")
        st.write("Total tokens = Prompt tokens + Completion tokens")
        st.write("Prompt tokens = Context tokens + Question tokens")
        st.caption("Chunk size & overlap are in characters (roughly 4 characters per token).")

    with column_token_usage:
        result = st.session_state.last_qa_result
        if result is None:
            st.write("Token usage of your last run will show up here.")
        else:
            token_usage_bars(result.usage, param_controller.get_value('context_window'))


def token_usage_bars(usage, context_window):
    if not usage.reported:
        st.write("The provider didn't report token usage for the last run.")
        return
    st.write(f"Last run used {usage.total} tokens")
    create_progress_bar("Context Tokens", usage.context_tokens, context_window)
    create_progress_bar("Question Tokens", usage.question_tokens, context_window)
    create_progress_bar("Completion Tokens", usage.completion_tokens, context_window)


def create_progress_bar(title, unit_tokens, context_window):
    share = unit_tokens / context_window if context_window else 0
    if share > 1:
        st.progress(1.0, f"{title}: {unit_tokens} tokens :red[(over the context window!)]")
    else:
        st.progress(share, f"{title}: {unit_tokens} tokens ({share:.1%})")


def retrieval_label(retrieval):
    if retrieval == providers.KEYWORD_RETRIEVAL:
        return "keyword search (BM25)"
    return f"{providers.PROVIDERS[retrieval].label} embeddings ({providers.PROVIDERS[retrieval].default_embedding_model})"


##########################################################
### ACTIVE PARAMS
##########################################################

CHAT_BOT_PARAMS = ["provider", "model_name", "max_response_tokens", "chat_history_messages"]
QA_CHAIN_PARAMS = ["provider", "model_name", "retrieval", "chunk_size", "chunk_overlap",
                   "top_related_chunks", "max_response_tokens", "context_window", "max_files"]


def get_params_info_dict(param_controller, names):
    data_copy = copy.deepcopy(param_controller.get_all_parameters())
    return {
        name: {k: (v.__name__ if isinstance(v, type) else v) for k, v in data_copy[name].items()}
        for name in names
    }
