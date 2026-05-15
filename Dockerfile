FROM python:3.12-slim

ARG PG_MAJOR=18

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SAVH_BACKUP_CONFIG=/app/config/config.toml \
    TZ=America/Santiago

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates gnupg tzdata wget && \
    install -d /usr/share/postgresql-common/pgdg && \
    wget -qO /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    . /etc/os-release && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install .

VOLUME ["/data"]

CMD ["python", "-m", "savh_backup", "scheduler"]

