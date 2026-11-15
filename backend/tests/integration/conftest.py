from collections.abc import AsyncIterator

import httpx
import pytest

from tests.integration.helpers import Env, Gate
from twyf.config import Settings
from twyf.files.jobs import InlineJobs
from twyf.http.app import build_app
from twyf.runtime.fake import FakeRuntime


@pytest.fixture
def env(client: httpx.AsyncClient, fake: FakeRuntime, settings: Settings) -> Env:
    return Env(client, fake, settings)


@pytest.fixture
async def gated(settings: Settings) -> AsyncIterator[tuple[Gate, Env]]:
    """An app whose work turns wait until `gate.release` is set."""
    gate = Gate(FakeRuntime([]))
    app = build_app(settings, runtime=gate, jobs=InlineJobs())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c,
    ):
        yield gate, Env(c, gate.inner, settings)
