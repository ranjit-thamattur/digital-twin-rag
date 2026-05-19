FROM python:3.11-slim

WORKDIR /app

# System libraries required by python-pptx (lxml) and pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt-dev \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Local ML model removed (Now using Amazon Titan API)

COPY . .

# Environment variables with defaults
ENV QDRANT_HOST=qdrant
ENV QDRANT_PORT=6334
ENV QDRANT_COLLECTION=digital_twin_knowledge
ENV AWS_DEFAULT_REGION=us-east-1
ENV MCP_TRANSPORT=sse
ENV PORT=3000

EXPOSE 3000

CMD ["python", "main.py"]
