FROM docker.io/library/python@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
WORKDIR /app
COPY config.yaml Dockerfile requirements.txt README.md run.py policy.py application.py keys.py store.py provider.py tls.py server.py SHA256SUMS /verified/
RUN cd /verified && sha256sum -c SHA256SUMS && python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt && mkdir /app/symphonia_native_oauth_trial && cp run.py policy.py application.py keys.py store.py provider.py tls.py server.py /app/symphonia_native_oauth_trial/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "symphonia_native_oauth_trial.run"]
