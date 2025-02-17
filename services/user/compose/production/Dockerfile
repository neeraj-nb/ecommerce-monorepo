FROM docker.io/python:latest

WORKDIR /app
COPY ./requirements .

RUN pip install -r production.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000","config.wsgi"]

# Env needed
# ALLOWED_HOSTS