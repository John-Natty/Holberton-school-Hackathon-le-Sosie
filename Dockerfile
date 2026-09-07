FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 5000
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000", "--no-debugger", "--no-reload"]
