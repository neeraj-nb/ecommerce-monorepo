FROM docker.io/python:latest

WORKDIR /app
COPY ./requirements .

RUN pip install -r local.txt

COPY . .

EXPOSE 8000
ENV DJANGO_DEBUG=TRUE

CMD [ "python", "manage.py", "runserver", "0.0.0.0:8000" ]