FROM python:3.10-slim

WORKDIR /app

# Set environment variables to reduce Python memory usage
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # Remove pip cache
    rm -rf /root/.cache/pip/* && \
    # Remove unnecessary files
    find /opt/venv -type d -name "__pycache__" -exec rm -r {} + && \
    find /opt/venv -type d -name "*.pyc" -exec rm -f {} +

# Copy only necessary files
COPY main.py models.py schemas.py database.py ./

# Run with minimal worker processes
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "20"] 