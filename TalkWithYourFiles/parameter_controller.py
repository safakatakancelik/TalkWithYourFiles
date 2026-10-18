class ParameterController:
    """Holds the dynamic parameters that shape the app's behaviour. The GUI reads & writes them,
    the flow coordinator uses them. Each parameter keeps its type, default, current value, description and limits."""

    def __init__(self):
        self.parameters = {}

    def register_parameter(self, name, type, default, description=None, **kwargs):
        parameter_info = {
            'type': type,
            'default': default,
            'value': default,
            'description': description
        }
        parameter_info.update(kwargs)
        self.parameters[name] = parameter_info

    def get_parameter(self, name):
        return self.parameters.get(name, {})

    def get_value(self, name):
        return self.parameters[name]['value']

    def set_parameter(self, name, value):
        if name not in self.parameters:
            raise KeyError(f"Parameter {name} is not registered.")
        info = self.parameters[name]
        if not isinstance(value, info['type']):
            raise TypeError(f"Parameter {name} expects {info['type'].__name__}, got {type(value).__name__}.")
        if ('min' in info and value < info['min']) or ('max' in info and value > info['max']):
            raise ValueError(f"Parameter {name} must be between {info.get('min')} and {info.get('max')}.")
        info['value'] = value

    def get_all_parameters(self):
        return self.parameters

    def setup_default_parameters(self):
        # QA chain
        self.register_parameter('chunk_size', int, 1000, 'Chunk size (characters) for text splitting', min=200, max=4000)
        self.register_parameter('chunk_overlap', int, 100, 'Chunk overlap (characters) for wider context', min=0, max=1000)
        self.register_parameter('top_related_chunks', int, 4, 'Amount of chunks to retrieve among the most related ones', min=1, max=30)
        self.register_parameter('max_response_tokens', int, 4096, 'Maximum tokens for the model response (incl. reasoning on thinking models)', min=256, max=32000)
        self.register_parameter('context_window', int, 128000, "Model's context window, used to show token usage as a share", min=4000, max=2000000)
        self.register_parameter('max_files', int, 10, 'Maximum number of files per question', min=1, max=50)

        # Chatbot
        self.register_parameter('chat_history_messages', int, 20, 'How many recent chat messages are sent to the model', min=2, max=200)

        # Model (filled in by the GUI from the sidebar selection)
        self.register_parameter('provider', str, 'anthropic', 'LLM provider used by the chatbot & the QA chain')
        self.register_parameter('model_name', str, '', 'Model used by the chatbot & the QA chain')
        self.register_parameter('retrieval', str, 'keyword', 'How related chunks are found: openrouter embeddings, or keyword (BM25)')
