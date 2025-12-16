FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
# gcc and libpq-dev are required for psycopg2
# ffmpeg is often required for zou previews
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
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

# Install gunicorn for production serving
RUN pip install --no-cache-dir gunicorn sendria

# Create directory for previews if it doesn't exist (can be mounted)
RUN mkdir -p /opt/zou/previews

# Expose the API port
EXPOSE 5000

# Default command
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "--timeout", "600", "zou.app:app"]
