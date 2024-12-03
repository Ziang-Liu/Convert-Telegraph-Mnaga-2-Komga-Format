FROM python:3.12-alpine AS builder

WORKDIR /app

ENV PATH=$PATH:/app
ENV PYTHONPATH /app

COPY requirements.txt requirements.txt
COPY bot /app/bot
COPY src /app/src

RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del --purge .build-deps

VOLUME /neko

CMD ["python3", "/app/bot/main.py"]