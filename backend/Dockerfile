FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create static directory and switch to non-root user
RUN mkdir -p static/covers data/content && \
    useradd -m -u 1000 novel && chown -R novel:novel /app
USER novel

# Expose port
EXPOSE 8000

# Run with gunicorn (production) — no --reload
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "gunicorn.conf.py", "app.main:app"]
