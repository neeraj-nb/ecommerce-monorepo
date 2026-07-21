"""Custom OTel metrics for the Kafka consumer: events processed, processing
duration, and consumer lag (how far behind the latest offset this consumer
group is sitting -- the standard "is this consumer keeping up" signal, and
the one thing DjangoInstrumentor's auto metrics never cover since a consumer
never handles an HTTP request).

Lag is computed INLINE in the consumer's own poll loop (not via an OTel
observable/async gauge, whose callback the SDK would invoke on its own export
thread) because kafka-python's KafkaConsumer is not thread-safe -- calling
assignment()/end_offsets()/position() concurrently with poll() from a
different thread risks corrupting the client's internal state.
"""
import logging
import time

from opentelemetry import metrics

logger = logging.getLogger(__name__)

meter = metrics.get_meter(__name__)

events_processed = meter.create_counter(
    "consumer_events_processed_total",
    unit="1",
    description="Kafka events processed by this consumer, by event_type and outcome",
)

event_processing_duration = meter.create_histogram(
    "consumer_event_processing_duration_ms",
    unit="ms",
    description="Time to process a single Kafka event, by event_type",
)

consumer_lag = meter.create_gauge(
    "consumer_lag",
    unit="1",
    description="Messages behind the latest offset for this consumer group, by topic/partition",
)

# Matches otel_setup.py's metric export interval -- no point recomputing lag
# (extra broker round trips for end_offsets()/position()) faster than
# anything downstream actually reads it.
_LAG_CHECK_INTERVAL_S = 10
_last_lag_check = 0.0


def record_event(event_type, outcome, duration_ms):
    """Record one processed event's outcome (success/duplicate/error/malformed) and duration."""
    events_processed.add(1, {"event_type": event_type, "outcome": outcome})
    event_processing_duration.record(duration_ms, {"event_type": event_type})


def maybe_record_lag(consumer):
    """Recompute and record consumer lag, throttled to roughly once per
    _LAG_CHECK_INTERVAL_S. Call this from the SAME thread that calls
    consumer.poll() (see module docstring on thread-safety).
    """
    global _last_lag_check
    now = time.monotonic()
    if now - _last_lag_check < _LAG_CHECK_INTERVAL_S:
        return
    _last_lag_check = now

    try:
        assignment = consumer.assignment()
        if not assignment:
            return
        end_offsets = consumer.end_offsets(assignment)
        for tp in assignment:
            position = consumer.position(tp)
            end = end_offsets.get(tp, position)
            consumer_lag.set(max(0, end - position), {"topic": tp.topic, "partition": str(tp.partition)})
    except Exception:  # noqa: BLE001 -- lag reporting must never crash the consumer
        logger.exception("failed computing consumer lag")
