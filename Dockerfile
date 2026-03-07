FROM python:3.12-slim

RUN pip install --no-cache-dir \
    flake8 \
    sphinx \
    sshtunnel \
    build \
    twine

WORKDIR /app
