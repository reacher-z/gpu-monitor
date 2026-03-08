FROM python:3.11-slim

# nvidia-smi must be available from the host via --runtime=nvidia
# or by bind-mounting /usr/bin/nvidia-smi

WORKDIR /app
COPY gpu_monitor.py .

# Health: verify the script compiles (actual GPU requires --runtime=nvidia at docker run time)
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import py_compile; py_compile.compile('gpu_monitor.py', doraise=True)" || exit 1

# All configuration is via environment variables — see .env.example
CMD ["python", "gpu_monitor.py"]
