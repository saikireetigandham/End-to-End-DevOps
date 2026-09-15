FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENV PYTHONPATH=/app/src
ENV FLASK_APP=app.py
ENV PORT=5000
EXPOSE 5000
FROM python:3.12-slim AS runner
WORKDIR /app
COPY --from=builder /app /app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]


