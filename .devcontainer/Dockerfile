FROM python:3.11.5-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pysetup

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --target /opt/pysetup/deps -r requirements.txt

FROM python:3.11.5-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/pysetup/deps /usr/local/lib/python3.11/site-packages

COPY . .

ENV PATH="/usr/local/lib/python3.11/site-packages/bin:${PATH}"

EXPOSE 80
