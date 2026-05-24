# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and README.md to install dependencies
COPY pyproject.toml README.md ./

# Install python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy source folders
COPY chatbot/ ./chatbot/
COPY pipeline/ ./pipeline/

# Expose port
EXPOSE 8080

# Start FastAPI server
CMD ["sh", "-c", "uvicorn chatbot.server:app --host 0.0.0.0 --port ${PORT}"]
