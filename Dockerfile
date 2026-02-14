FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Run the FastAPI server
CMD ["python", "-m", "event_research.api"]
