FROM docker.io/python:3.11-slim AS builder

WORKDIR /app

# Install build dependancy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*


COPY ./requirements .

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r production.txt


FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN adduser --disabled-password --gecos '' django
USER django

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000","config.wsgi"]

# Env needed
# ALLOWED_HOSTS