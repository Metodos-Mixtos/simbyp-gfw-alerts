FROM python:3.13-slim

# Install system dependencies for GDAL, geospatial libraries, and Spanish locale
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    g++ \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Generate Spanish locale
RUN sed -i '/es_ES.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen es_ES.UTF-8

# Set locale environment variables
ENV LANG=es_ES.UTF-8
ENV LANGUAGE=es_ES:es
ENV LC_ALL=es_ES.UTF-8

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (NOT .env or keys!)
COPY gfw_alerts/ ./gfw_alerts/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the weekly report (no parameters needed)
CMD ["python", "gfw_alerts/main.py"]