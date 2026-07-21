# otel_setup.py
import os

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor


# Set up tracing
resource = Resource.create({
    "service.name": os.getenv("OTEL_SERVICE_NAME", "django-app"),
    "service.version": "1.0.0",
    "deployment.environment": os.getenv("ENVIRONMENT", "development"),
})
trace.set_tracer_provider(TracerProvider(resource=resource))

# Leave endpoint unset: the SDK reads OTEL_EXPORTER_OTLP_ENDPOINT itself and
# auto-appends the correct per-signal path (/v1/traces, /v1/metrics). Passing
# endpoint= explicitly (as this used to) bypasses that entirely, so requests
# went to the bare base URL instead and were silently dropped by the collector
# -- BatchSpanProcessor/PeriodicExportingMetricReader swallow export failures.
otlp_trace_exporter = OTLPSpanExporter(timeout=5)

span_processor = BatchSpanProcessor(otlp_trace_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Metrics
otlp_metric_exporter = OTLPMetricExporter(timeout=5)

# 10s: just under Prometheus's 15s scrape_interval (prometheus.yaml), so every
# scrape sees fresh data without exporting faster than anything downstream
# reads (the default 60s otherwise leaves dashboards looking stale for a while
# after traffic happens).
metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=10000)

metrics.set_meter_provider(
    MeterProvider(
        metric_readers=[metric_reader],
        resource=resource,
    )
)

# Instrument Django and other libs
DjangoInstrumentor().instrument()
Psycopg2Instrumentor().instrument()
RequestsInstrumentor().instrument()
