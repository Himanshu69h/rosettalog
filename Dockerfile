FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROSETTALOG_DATA_DIR=/data \
    ROSETTALOG_PARSER_DIR=/app/parsers \
    ROSETTALOG_PARSER_SCHEMA=/app/schemas/parser.schema.json \
    ROSETTALOG_ENVELOPE_SCHEMA=/app/schemas/envelope.schema.json

COPY wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels "rosettalog[api,ui]==0.1.0" && \
    groupadd --system rosetta && \
    useradd --system --gid rosetta --create-home rosetta

COPY README.md pyproject.toml /app/
COPY parsers /app/parsers
COPY schemas /app/schemas
COPY src /app/src
RUN mkdir -p /data && chown -R rosetta:rosetta /app /data
USER rosetta

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "rosettalog", "--help"]
