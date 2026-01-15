FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy configuration
COPY pyproject.toml ./

# Create dummy readme to satisfy poetry
RUN touch README.md

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy source code
COPY src ./src

# Expose port
EXPOSE 8000

# Add src to PYTHONPATH so 'sql_agent' can be imported
ENV PYTHONPATH=/app/src

# Run FastAPI
# Note: src.api.server must exist. I verified it exists.
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
