# AI-MAP Ethiopia; one image, two roles.
#
# The collection server and the Telegram bot run from the SAME image because
# they run from the same code and must share one database. Building them
# separately would let their dependency sets drift, and a bot scoring responses
# with a different version of the reference implementation than the server is
# exactly the divergence this project spends so much effort preventing.
#
# Which role a container plays is decided by `command:` in docker-compose.yml,
# not by a build argument, so both roles are always the same bytes.

FROM python:3.12-slim AS runtime

# tini reaps zombies and forwards signals, so `docker compose stop` actually
# stops uvicorn and the bot rather than waiting out the 10-second kill timer.
# sqlite3 is here for backups: `.backup` is safe against a live writer, `cp` is not.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini sqlite3 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes,
# so editing a question in the schema does not reinstall FastAPI.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the two processes actually need at runtime. The paper, the sources
# and the dev scripts stay out -- see .dockerignore.
COPY tools/ ./tools/

# Run as a non-root user that owns the data directory. The database lives on a
# volume mounted here, so the uid must match between image and volume; creating
# the directory in the image gives the volume the right ownership on first run.
RUN useradd --system --create-home --uid 10001 aimap \
 && mkdir -p /data \
 && chown -R aimap:aimap /data /app
USER aimap

# Both roles read this. Compose sets it identically for both services; it is
# repeated here so that a plain `docker run` cannot accidentally get it wrong.
ENV AIMAP_DB=/data/aimap.db \
    AIMAP_LIVENESS=/tmp/aimap-bot-alive

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default role is the server. The bot service overrides this.
CMD ["python", "-m", "uvicorn", "--app-dir", "tools/server", "app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
