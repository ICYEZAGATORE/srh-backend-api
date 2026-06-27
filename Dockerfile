FROM python:3.11-slim

# Avoid .pyc files and buffered stdout/stderr in containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Normalize line endings (in case of a CRLF checkout) and make the script runnable.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Migrate then serve. Render's $PORT is honoured by the script (defaults to 8000).
CMD ["sh", "/app/entrypoint.sh"]
