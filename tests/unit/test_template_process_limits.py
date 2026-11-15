import asyncio
import os
import resource
import time

import pytest
import pytest_asyncio

from app.services import template_service as templates


@pytest_asyncio.fixture(autouse=True)
async def cleanup_pool():
    yield
    pool = getattr(templates, "_render_pool", None)
    if pool is not None:
        await templates._reset_render_pool(pool)


@pytest.mark.parametrize("rich", [False, True])
async def test_render_runs_in_a_separate_limited_process(rich):
    render = templates.render_rich_template if rich else templates.render_template
    result = await render("{{ pid() }}", {"pid": os.getpid})
    assert int(result) != os.getpid()
    limit = await render("{{ limits(limit)[0] }}", {"limits": resource.getrlimit, "limit": resource.RLIMIT_AS})
    assert int(limit) == 256 * 1024 * 1024


@pytest.mark.parametrize("rich", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        '{{ "x" * 100 * 100 * 100 }}',
        '{{ "x" | center(1000000000000) }}',
        '{{ "x" | indent(1000000000000) }}',
        '{{ "%1000000000000s" | format("x") }}',
        '{{ "x" * 5000 + "y" * 5000 }}',
    ],
)
async def test_expansion_is_refused_without_parent_memory_growth(source, rich):
    render = templates.render_rich_template if rich else templates.render_template
    assert await render("hello {{ name }}", {"name": "world"}) == "hello world"
    memory_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    start = time.monotonic()
    with pytest.raises(ValueError):
        await render(source, {})
    assert time.monotonic() - start < 3
    assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - memory_before < 32 * 1024
    assert await render("{{ 2 * 3 + 1 }}", {}) == "7"


@pytest.mark.parametrize(
    ("source", "context"),
    [
        ("{{ pause(30) }}", {"pause": time.sleep}),
        ("{{ total(numbers) }}", {"total": sum, "numbers": range(1_000_000_000)}),
    ],
)
async def test_timeout_kills_worker_and_next_render_works(monkeypatch, source, context):
    assert await templates.render_template("warm", {}) == "warm"
    pool = templates._render_pool
    workers = list(pool._processes.values())
    monkeypatch.setattr(templates, "_RENDER_TIMEOUT_SECONDS", 0.1)
    start = time.monotonic()
    with pytest.raises(ValueError, match="время рендеринга"):
        await templates.render_template(source, context)
    assert time.monotonic() - start < 3
    assert all(not worker.is_alive() for worker in workers)
    monkeypatch.setattr(templates, "_RENDER_TIMEOUT_SECONDS", 1.0)
    assert await templates.render_template("after {{ 1 + 1 }}", {}) == "after 2"


def _slow_initialize_render_worker(start_barrier):
    time.sleep(1.5)
    templates._initialize_render_worker(start_barrier)


async def test_slow_worker_startup_is_outside_render_timeout(monkeypatch):
    monkeypatch.setattr(templates, "_initialize_render_worker", _slow_initialize_render_worker)
    assert await templates.render_template("first {{ 1 + 1 }}", {}) == "first 2"
    pool = templates._render_pool
    assert len(pool._processes) == templates._RENDER_WORKERS
    await templates._reset_render_pool(pool)
    assert await templates.render_template("after reset", {}) == "after reset"


async def test_pool_reset_does_not_block_the_event_loop(monkeypatch):
    assert await templates.render_template("warm", {}) == "warm"
    pool = templates._render_pool
    shutdown = pool.shutdown

    def slow_shutdown(*args, **kwargs):
        time.sleep(0.3)
        shutdown(*args, **kwargs)

    monkeypatch.setattr(pool, "shutdown", slow_shutdown)
    start = time.monotonic()
    ticks = []

    async def tick():
        await asyncio.sleep(0.05)
        ticks.append(time.monotonic() - start)

    await asyncio.gather(templates._reset_render_pool(pool), tick())
    assert ticks[0] < 0.2


async def test_concurrent_first_renders_share_one_warmed_pool(monkeypatch):
    factory = templates.ProcessPoolExecutor
    created = []

    def create_pool(*args, **kwargs):
        pool = factory(*args, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(templates, "ProcessPoolExecutor", create_pool)
    assert await asyncio.gather(*(templates.render_template("{{ value }}", {"value": i}) for i in range(6))) == [
        str(i) for i in range(6)
    ]
    assert len(created) == 1
    assert len(created[0]._processes) == templates._RENDER_WORKERS
