FROM ghcr.io/home-assistant/qemuarm-64-homeassistant@sha256:dd1ad589936601cacb1b4797d17e27ce762b5147fb46b0e8e3d5486ab95e56c3
COPY tools /opt/research/tools
ENV PYTHONPATH=/opt/research PYTHONDONTWRITEBYTECODE=1
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 CMD ["python3", "-c", "import socket; socket.create_connection(('127.0.0.1', 8099), 2).close()"]
ENTRYPOINT ["python3", "/opt/research/tools/ha_oauth_companion_lab/wire_app/server.py"]
CMD []
