FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
# gcc and libpq-dev are required for psycopg2
# ffmpeg is required for zou previews
# xmlsec1 is required for SAML authentication
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    xmlsec1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# We expect the zou source code to be mounted or copied here.
# For this build, we are installing from the context which is the zou repo root.
COPY . .

# Install dependencies and zou itself
# We use --no-cache-dir to keep image small
# We assume setup.py or pyproject.toml is present in the root
RUN pip install --no-cache-dir .

# Install gunicorn and required workers for production serving
# gevent: for async worker in main API
# gevent-websocket: for websocket support in event stream
# flask-socketio: for socketio support
RUN pip install --no-cache-dir \
    gunicorn \
    gevent \
    gevent-websocket \
    flask-socketio \
    python-socketio \
    sendria

# Create required directories
RUN mkdir -p /opt/zou/previews /opt/zou/tmp /opt/zou/logs

# Expose the API ports
# 5000: Main API
# 5001: Event Stream (websocket)
EXPOSE 5000 5001

# Default command (main API with gevent worker)
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "3", "--worker-class", "gevent", "--access-logfile", "-", "--error-logfile", "-", "--timeout", "600", "zou.app:app"]
