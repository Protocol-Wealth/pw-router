FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY pw_router/ pw_router/
COPY plugins/ plugins/

EXPOSE 8100

CMD ["uvicorn", "pw_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
