# Stellenpilot in a container. Your files live in the /data volume.
FROM python:3.12-slim

# PDF export needs LibreOffice (about 400 MB). Build with --build-arg WITH_PDF=false to skip it.
ARG WITH_PDF=true
RUN if [ "$WITH_PDF" = "true" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-crosextra-carlito fonts-dejavu-core && \
      rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY stellenpilot ./stellenpilot
RUN pip install --no-cache-dir ".[gmail]"

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 hunter && mkdir /data && chown hunter /data
USER hunter
ENV HOME=/home/hunter JOBHUNT_HOST=0.0.0.0
WORKDIR /data
VOLUME /data
EXPOSE 8765

ENTRYPOINT ["stellenpilot", "--home", "/data"]
CMD ["serve"]
