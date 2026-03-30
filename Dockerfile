FROM python:3.12-slim

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml .
RUN pip install --no-cache-dir --no-deps .

COPY pw_router/ pw_router/
COPY plugins/ plugins/

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8100

CMD ["uvicorn", "pw_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
