FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && python -m pip install --no-cache-dir uv==0.11.32

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt \
    && uv pip install --system --require-hashes --no-cache \
        --python /usr/local/bin/python --requirement /tmp/requirements.txt \
    && python -m pip uninstall --yes uv \
    && rm -rf /root/.cache /tmp/requirements.txt

COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 cli.py ./
COPY --chown=10001:10001 alembic ./alembic
COPY --chown=10001:10001 bracket ./bracket
COPY --chown=10001:10001 openapi ./openapi
COPY --chown=10001:10001 static ./static

USER 10001:10001
EXPOSE 8400

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bracket.app:app", "--bind", "0.0.0.0:8400", "--workers", "1"]
