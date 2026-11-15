from twyf.config import Settings
from twyf.runtime.base import AgentRuntime
from twyf.runtime.fake import FakeRuntime


def get_runtime(settings: Settings) -> AgentRuntime:
    if settings.runtime == "fake":
        return FakeRuntime([])
    # The queue runtime is task B31 and the command runtime task B32.
    raise ValueError(f"runtime {settings.runtime!r} is not available yet")
