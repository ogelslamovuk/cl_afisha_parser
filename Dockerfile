FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gh openssh-client util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /home/app/.ssh \
    && chown -R app:app /home/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN chown -R app:app /app

USER app
ENV HOME=/home/app

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
