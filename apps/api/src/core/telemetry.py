import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

from src.core.config import get_settings
from src.core.db import get_engine

logger = structlog.get_logger(__name__)

_initialized = False


def setup_telemetry(app: FastAPI | None = None, exporter: SpanExporter | None = None) -> None:
    """Tracing for the API and the worker.

    Disabled unless OTEL_ENABLED=true. Spans go to the OTLP endpoint when
    OTEL_EXPORTER_OTLP_ENDPOINT is set (Cloud Trace via collector, Grafana,
    Honeycomb, ...), to the console otherwise.
    """
    global _initialized
    settings = get_settings()
    if not settings.otel_enabled and exporter is None:
        return
    if not _initialized:
        if exporter is None:
            exporter = (
                OTLPSpanExporter()
                if settings.otel_exporter_otlp_endpoint
                else ConsoleSpanExporter()
            )
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        SQLAlchemyInstrumentor().instrument(engine=get_engine().sync_engine)
        HTTPXClientInstrumentor().instrument()
        _initialized = True
        logger.info("telemetry.enabled", service=settings.otel_service_name)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("saas-genai-starter")
