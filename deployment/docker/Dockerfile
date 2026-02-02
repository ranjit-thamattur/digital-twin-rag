# Extend official OpenWebUI image
FROM ghcr.io/open-webui/open-webui:main

# Install Python dependencies for Pipe
RUN pip install --no-cache-dir requests pydantic

# Create pipelines folder
RUN mkdir -p /app/backend/pipelines

# Set the custom Peak AI logo
COPY peak_logo.png /app/backend/static/favicon.png
COPY peak_logo.png /app/backend/static/logo.png
COPY peak_logo.png /app/backend/static/peak_logo.png
COPY peak_logo.png /app/build/favicon.png
COPY peak_logo.png /app/build/logo.png
COPY peak_logo.png /app/build/favicon.ico

# Force image rebuild
RUN echo "Peak Branding v3.1-genuine-png" > /app/branding_version.txt



