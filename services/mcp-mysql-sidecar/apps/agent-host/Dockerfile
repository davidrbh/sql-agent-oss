FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy configuration
COPY pyproject.toml ./

# Install dependencies
# We create a dummy file to allow install if src doesn't exist yet
RUN touch README.md

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy source code
COPY src ./src

# Expose port
EXPOSE 8000

# Run FastAPI
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
