"""OpenTelemetry tracing — the Article Audit Trail's distributed twin.

The audit trail is the *editorial* record: append-only, durable, and the only
thing the Editor Gate reads. Tracing is the *operational* record: one span tree
per submission, tied to article and claim IDs, exported to Cloud Trace for the
waterfall that shows desks running concurrently, one desk timing out, and the
gate evaluating afterwards.

The distinction matters for the invariant: telemetry loss alerts, but it can
never grant approval. Nothing in `domain/` or `desks/` imports this module's
backend — callers use `span()`, which is a no-op when tracing is off, so the
fleet runs identically with zero observability dependencies installed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from newsroom_fleet.config import (
    TRACING_CLOUD,
    TRACING_CONSOLE,
    TRACING_OFF,
    Settings,
)

log = logging.getLogger(__name__)

INSTRUMENTATION_NAME = "newsroom-fleet"

_tracer: Any | None = None
_mode: str = TRACING_OFF


class _NullSpan:
    """Stand-in span so call sites need no `if tracing enabled` branches."""

    def set_attribute(self, key: str, value: object) -> None: ...
    def add_event(self, name: str, attributes: dict | None = None) -> None: ...
    def record_exception(self, exc: BaseException) -> None: ...
    def set_status(self, *args: object, **kwargs: object) -> None: ...


def configure_tracing(settings: Settings) -> str:
    """Install the tracer provider. Returns the mode actually configured."""
    global _tracer, _mode

    if settings.tracing == TRACING_OFF:
        _tracer, _mode = None, TRACING_OFF
        return _mode

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        log.warning("tracing requested but the OpenTelemetry SDK is missing (%s)", exc)
        _tracer, _mode = None, TRACING_OFF
        return _mode

    resource = Resource.create(
        {
            "service.name": INSTRUMENTATION_NAME,
            "service.namespace": "newsroom",
            "newsroom.mode": settings.mode,
            "newsroom.repository": settings.repository,
        }
    )
    provider = TracerProvider(resource=resource)

    exporter = None
    if settings.tracing == TRACING_CLOUD:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter(project_id=settings.gcp_project)
            _mode = TRACING_CLOUD
        except Exception as exc:  # noqa: BLE001
            log.warning("Cloud Trace exporter unavailable (%s); tracing to console", exc)

    if exporter is None:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        exporter = ConsoleSpanExporter()
        _mode = TRACING_CONSOLE

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(INSTRUMENTATION_NAME)
    log.info("tracing configured: %s", _mode)
    return _mode


def instrument_app(app: object) -> None:
    """Attach FastAPI request spans so the trace starts at the gateway."""
    if _tracer is None:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        log.warning("FastAPI instrumentation unavailable (%s)", exc)


@contextmanager
def span(name: str, **attributes: object) -> Iterator[Any]:
    """Start a span, or yield a null span when tracing is off.

    Attribute keys are namespaced by the caller (`newsroom.article_id`,
    `newsroom.claim_id`, `newsroom.desk`) so Cloud Trace can filter a waterfall
    down to a single claim.
    """
    if _tracer is None:
        yield _NullSpan()
        return
    with _tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def current_trace_id() -> str | None:
    """Hex trace id of the active span, recorded on audit events so an editorial
    record can be joined to its operational trace."""
    if _tracer is None:
        return None
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if not ctx.is_valid:
            return None
        return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001
        return None
