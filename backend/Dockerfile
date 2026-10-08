FROM python:3.14-slim

LABEL org.opencontainers.image.description="Bracket backend for the Ctrl-Alt-GG LAN tournament system: FastAPI application with Alembic migrations."

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

# The code stays owned by root, so the app can't modify it. Uploaded logos are its only writes.
COPY alembic.ini cli.py ./
COPY alembic ./alembic
COPY bracket ./bracket
COPY openapi ./openapi
RUN install --directory --owner=10001 --group=10001 uploads

USER 10001:10001
EXPOSE 8400

# uvicorn trusts the `X-Forwarded-For` of the proxies listed in `FORWARDED_ALLOW_IPS`.
CMD ["uvicorn", "bracket.app:app", "--host", "0.0.0.0", "--port", "8400", "--no-server-header"]
