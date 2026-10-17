import streamlit as st

from flow_coordinator import FlowCoordinator
from parameter_controller import ParameterController
from streamlit_modules.streamlit_chat import main_chat
from streamlit_modules.streamlit_components import (
    setup_header_area,
    setup_page_configurations,
    setup_sidebar,
    tab1_qa_chain_files,
    tab2_active_params,
)
from streamlit_modules.streamlit_helper_functions import initialize_session_state, sync_parameters_from_widgets


def main():
    # Page configurations
    setup_page_configurations()
    initialize_session_state()

    ## Instantiating a ParameterController instance & registering default parameters.
    param_controller = ParameterController()
    param_controller.setup_default_parameters()
    sync_parameters_from_widgets(param_controller)

    ### Streamlit Interface

    # Header
    setup_header_area()

    # Sidebar (returns the API keys that can be used)
    api_keys = setup_sidebar(param_controller)
    has_llm = bool(api_keys)

    ## Instantiating the Flow Coordinator
    flow_coordinator = FlowCoordinator(param_controller, api_keys, cache=st.session_state.qa_cache)

    # Setting up each tab for the GUI
    tab0, tab1, tab2 = st.tabs(["Chat Bot", "QA Chain", "Active Params"])

    with tab0:
        main_chat(param_controller, flow_coordinator, has_llm)
    with tab1:
        # Tab 1 QA Chain Over Files
        tab1_qa_chain_files(param_controller, flow_coordinator, has_llm)
    with tab2:
        tab2_active_params(param_controller)


if __name__ == '__main__':
    main()
