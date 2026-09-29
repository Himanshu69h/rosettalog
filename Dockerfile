FROM python:3.11-slim AS build
WORKDIR /app

COPY requirements.txt ./
COPY Makefile ./
COPY pyproject.toml ./
RUN python -m pip install --upgrade pip && python -m pip install --no-cache-dir build

FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
COPY wheels /wheels
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-index --find-links=/wheels -r requirements.txt && \
    groupadd --system rosetta && useradd --system --gid rosetta --create-home rosetta

COPY . .
RUN chown -R rosetta:rosetta /app
USER rosetta

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["python", "-m", "rosettalog.cli", "--help"]
