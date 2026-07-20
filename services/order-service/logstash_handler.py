"""Ships Django logs to Logstash as newline-delimited JSON over TCP.

Subclasses SocketHandler purely to reuse its connection/retry/backoff and
non-fatal-on-failure behaviour (a dead Logstash never crashes the app --
SocketHandler.emit already swallows connection errors via handleError).
Only the wire format changes: JSON + "\n" per record instead of pickle,
matching logstash.conf's `tcp { codec => json }` input (line-delimited).
"""
import datetime
import json
import logging
import logging.handlers
import os

_exc_formatter = logging.Formatter()


class LogstashTCPHandler(logging.handlers.SocketHandler):
    def makePickle(self, record):
        payload = {
            "@timestamp": datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "service": os.environ.get("OTEL_SERVICE_NAME", "django-app"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = _exc_formatter.formatException(record.exc_info)
        return (json.dumps(payload) + "\n").encode("utf-8")
