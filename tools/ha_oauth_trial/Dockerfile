FROM cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39 AS tunnel
FROM python@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY --from=tunnel /usr/local/bin/cloudflared /usr/local/bin/cloudflared
WORKDIR /app
COPY server.py /app/server.py
RUN groupadd --gid 10001 trial && useradd --uid 10001 --gid 10001 --no-create-home trial
# Supervisor writes options.json as root:0600. Read only that bounded file,
# then irreversibly drop UID/GID/groups before any listener or child starts.
USER root
EXPOSE 8099
ENTRYPOINT ["python", "/app/server.py"]
