# Extend official OpenWebUI image
FROM ghcr.io/open-webui/open-webui:main

# Install Python dependencies for Pipe
RUN pip install --no-cache-dir requests pydantic

# Create pipelines folder
RUN mkdir -p /app/backend/pipelines

# Set the custom Peak AI logo
COPY peak-logo.jpg /app/backend/static/favicon.png
COPY peak-logo.jpg /app/backend/static/logo.png
COPY peak-logo.jpg /app/build/favicon.png
COPY peak-logo.jpg /app/build/logo.png
COPY peak-logo.jpg /app/build/favicon.ico



