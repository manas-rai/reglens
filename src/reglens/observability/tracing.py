"""OpenTelemetry SDK setup.

In development (no OTEL_EXPORTER_ENDPOINT set) traces go to the console.
In production they go to an OTLP gRPC collector endpoint.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)

_tracer_provider: TracerProvider | None = None


def configure_tracing(service_name: str, otlp_endpoint: str | None = None) -> None:
    global _tracer_provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter: SpanExporter
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def get_tracer(name: str = "reglens") -> trace.Tracer:
    return trace.get_tracer(name)
