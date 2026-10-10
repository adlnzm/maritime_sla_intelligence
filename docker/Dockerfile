FROM python:3.11-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --no-dev --extra azure
COPY tests/data ./samples
COPY scripts/container_smoke.py ./scripts/container_smoke.py
RUN useradd --create-home --uid 10001 maritime && mkdir -p /app/data && chown maritime:maritime /app/data
USER maritime
ENV PATH="/app/.venv/bin:$PATH" MARITIME_DATA_DIR=/app/data
ARG BUILD_COMMIT=UNAVAILABLE
ENV BUILD_COMMIT=$BUILD_COMMIT
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["maritime", "serve", "--host", "0.0.0.0"]
