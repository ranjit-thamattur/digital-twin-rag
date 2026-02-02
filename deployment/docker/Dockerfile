# Extend official OpenWebUI image
FROM ghcr.io/open-webui/open-webui:main

# Install Python dependencies for Pipe
RUN pip install --no-cache-dir requests pydantic

# Create pipelines folder
RUN mkdir -p /app/backend/pipelines

# Set the custom Peak AI logo
COPY peak_logo.png /app/peak_logo.png

# Overwrite ALL standard logos found in the image
RUN find /app -name "favicon.png" -exec cp /app/peak_logo.png {} \;
RUN find /app -name "logo.png" -exec cp /app/peak_logo.png {} \;
RUN find /app -name "favicon.ico" -exec cp /app/peak_logo.png {} \;

# Ensure static folders exist and contain the logo
RUN mkdir -p /app/backend/static /app/build/static
RUN cp /app/peak_logo.png /app/backend/static/peak_logo.png
RUN cp /app/peak_logo.png /app/backend/static/favicon.png
RUN cp /app/peak_logo.png /app/backend/static/logo.png

# Force image rebuild
RUN echo "Peak Branding v4.0-nuclear" > /app/branding_version.txt



