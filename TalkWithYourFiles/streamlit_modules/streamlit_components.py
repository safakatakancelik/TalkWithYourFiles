import streamlit as st

from backend_utils import providers
from backend_utils.file_handlers import FileHandlerFactory
from flow_coordinator import FlowError
from .streamlit_chat import integrate_chain_into_chat
from .streamlit_helper_functions import (
    CHAT_BOT_PARAMS,
    QA_CHAIN_PARAMS,
    advanced_parameters_section,
    api_key_input,
    get_params_info_dict,
    retrieval_label,
)


REPO_URL = "https://github.com/safakatakancelik/TalkWithYourFiles"


def setup_page_configurations():
    ##### PAGE CONFIGURATIONS
    st.set_page_config(
        page_title="Talk With Your Files",
        page_icon="🧙‍♂️",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': REPO_URL,
            'Report a bug': f"{REPO_URL}/issues",
            'About': "Open source LLM GUI app allowing interactions with files!"
        }
    )


def setup_header_area():
    ##### HEADER
    st.title("Talk With Your Files 🪄 ")


def setup_sidebar(param_controller):
    """Draws the sidebar and returns the usable API keys (provider id -> key)."""
    ##### SIDEBAR
    st.sidebar.markdown("# Talk With Your Files 🪄")
    st.sidebar.write("Hello! Here's an open-source tool for you. Query your files, modify the QA chain behaviour, "
                     "monitor active parameters, feed the results into the chatbot if you prefer. Hope you love it! ❤️")
    st.sidebar.markdown(f'Documentation & codebase: [github.com/safakatakancelik/TalkWithYourFiles]({REPO_URL})')

    st.sidebar.markdown("### Authorization")
    st.sidebar.write("Add a key for at least one provider. Keys in a `.env` file are picked up automatically.")
    api_keys = {}
    for provider_id in providers.PROVIDERS:
        key = api_key_input(provider_id)
        if key:
            api_keys[provider_id] = key
    st.sidebar.caption("API keys typed here are not stored, and their use is limited to your present browser session.")

    st.sidebar.markdown("### Model")
    if api_keys:
        provider_id = st.sidebar.selectbox(
            "Provider",
            options=list(api_keys),
            format_func=lambda p: providers.PROVIDERS[p].label,
            key="param_provider",
        )
        model_name = st.sidebar.text_input(
            "Model",
            value=providers.default_model(provider_id),
            key=f"model_{provider_id}",
            help="Any model name the provider supports.",
        ).strip() or providers.default_model(provider_id)
        param_controller.set_parameter('provider', provider_id)
        param_controller.set_parameter('model_name', model_name)
    else:
        st.sidebar.info("Add an API key above to choose a model.")

    retrieval = providers.pick_retrieval_provider(api_keys)
    param_controller.set_parameter('retrieval', retrieval)
    if api_keys:
        st.sidebar.caption(f"Finding related chunks with: {retrieval_label(retrieval)}")

    st.sidebar.markdown("Using these APIs costs a small amount based on your usage, billed by the provider.")
    return api_keys


def tab1_qa_chain_files(param_controller, flow_coordinator, has_llm):
    """
    The QA chain over files. Streamlit only renders the GUI & handles uploads;
    the work is done by flow_coordinator.run(files, user_question), which any other GUI could call too.
    """
    ##### FILE UPLOADS
    files = st.file_uploader(
        "Upload files",
        type=FileHandlerFactory.supported_extensions(),
        accept_multiple_files=True,
    )

    ##### ADVANCED PARAMETERS SECTION
    with st.expander("Show Advanced Parameters?"):
        advanced_parameters_section(param_controller)

    ##### USER QUESTION INPUT
    user_question = st.text_input("Please ask question(s) about the files you've uploaded: ")

    ###### To run the chain & shape the behaviour
    run_button_col, integration_button_col = st.columns([3, 1])
    with run_button_col:
        run_button_clicked = st.button("Run", width="stretch", type="primary", disabled=not has_llm)
    with integration_button_col:
        transfer_to_chat_bot = st.selectbox(
            label="QA chain behaviour",
            label_visibility="collapsed",
            options=["Standalone", "Integrated into the chatbot"],
        )

    if not has_llm:
        st.info("Add an API key on the sidebar to start.")

    ##### START QA CHAIN
    if run_button_clicked:
        try:
            with st.spinner("Reading your files & asking the model..."):
                result = flow_coordinator.run([(f.name, f.getvalue()) for f in files or []], user_question)
        except FlowError as e:
            st.error(str(e))
            return
        st.session_state.last_qa_result = result
        st.session_state.last_qa_question = user_question
        if transfer_to_chat_bot != "Standalone":
            integrate_chain_into_chat(user_question, result.answer)
            st.toast("Added to the chat in the Chat Bot tab.")
        st.rerun()  # redraw so the token usage in the advanced section is up to date

    result = st.session_state.last_qa_result
    if result is not None:
        st.markdown(f"**{st.session_state.last_qa_question}**")
        st.write(result.answer)
        if result.usage.reported:
            st.caption(f"{result.usage.total} tokens used · details under Show Advanced Parameters")
        with st.expander(f"Retrieved chunks ({len(result.chunks)})"):
            for i, chunk in enumerate(result.chunks, 1):
                st.markdown(f"**Chunk {i}**")
                st.text(chunk)


def tab2_active_params(param_controller):
    ## To see the params in the UI as we change them.
    column_chat_bot_params, column_qa_chain_params = st.columns(2)

    with column_chat_bot_params:
        st.write("Chat Bot")
        st.write(get_params_info_dict(param_controller, CHAT_BOT_PARAMS))
    with column_qa_chain_params:
        st.write("QA Chain")
        st.write(get_params_info_dict(param_controller, QA_CHAIN_PARAMS))
