import httpx
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from src.core.telemetry import setup_telemetry
from src.main import create_app

exporter = InMemorySpanExporter()


async def test_request_produces_connected_trace() -> None:
    application = create_app()
    setup_telemetry(application, exporter=exporter)

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 200

    # Flush pending spans out of the batch processor.
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    provider.force_flush()

    spans = exporter.get_finished_spans()
    http_spans = [s for s in spans if s.name.startswith("GET /health")]
    db_spans = [s for s in spans if s.name.lower().startswith("select")]
    assert http_spans, f"no http span in {[s.name for s in spans]}"
    assert db_spans, "the readiness DB query should be traced"

    # Connected: the DB span belongs to the same trace as the request span.
    http_trace_ids = {s.context.trace_id for s in http_spans}
    assert any(s.context.trace_id in http_trace_ids for s in db_spans)
