from __future__ import annotations

import asyncio

import pytest

from planaudit.catalog import Endpoint
from planaudit.fake import Behaviour, make_app
from planaudit.runner import collect
from planaudit.serve import background


@pytest.fixture
def fake_endpoint():
    """Factory: start a fake server with a Behaviour, return an Endpoint for it."""
    stack = []

    def make(slug: str = "fake", **behaviour) -> Endpoint:
        cm = background(make_app(Behaviour(**behaviour)))
        url = cm.__enter__()
        stack.append(cm)
        return Endpoint(
            slug=slug,
            role="lab",
            base_url=url,
            api_model="fake-model",
            logprobs=True,
            thinking_off={},
            max_concurrency=16,
            min_interval_s=0,
        )

    yield make
    for cm in reversed(stack):
        cm.__exit__(None, None, None)


def run_probe(probe, *endpoints):
    return asyncio.run(collect(probe, list(endpoints), quiet=True, seed=0))
