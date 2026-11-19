# Backend tier. Small image, fixed base version, pinned dependencies, and a non-root user.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# A numeric user ID, so Kubernetes can check "runAsNonRoot" without reading /etc/passwd.
USER 10001:10001
COPY --chown=10001:10001 server.py .

ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080

# No shell form: the process is PID 1 and receives SIGTERM directly when the pod stops.
ENTRYPOINT ["python", "server.py"]
