FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install boto3 requests

# Copy sync service
COPY sync_service.py .

# Enable unbuffered Python output for real-time logs
ENV PYTHONUNBUFFERED=1

# Run the service
CMD ["python", "-u", "sync_service.py"]
