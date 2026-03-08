FROM python:3.11-slim

# nvidia-smi must be available from the host via --runtime=nvidia
# or by bind-mounting /usr/bin/nvidia-smi

WORKDIR /app
COPY gpu_monitor.py .

# All configuration is via environment variables — see .env.example
CMD ["python", "gpu_monitor.py"]
