FROM python:3.11-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends --no-install-suggests \
  && pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
COPY entrypoint /entrypoint
RUN chmod +x /entrypoint

COPY start.dev.sh /start.dev.sh
RUN chmod +x /start.dev.sh

COPY start.prod.sh /start.prod.sh
RUN chmod +x /start.prod.sh

# CMD ["gunicorn", "user_service.wsgi:application", "--bind", "0.0.0.0:8000"]
ENTRYPOINT [ "/entrypoint" ]
