FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY nova ./nova
RUN pip install .

RUN useradd --create-home --uid 10001 nova \
    && mkdir -p /data/artifacts \
    && chown -R nova:nova /app /data
USER nova

EXPOSE 8788
CMD ["uvicorn", "nova.main:app", "--host", "0.0.0.0", "--port", "8788"]
