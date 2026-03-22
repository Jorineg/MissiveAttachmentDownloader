FROM jorineg/ibhelm-base:latest

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY caddy-root-ca.crt /tmp/caddy-root-ca.crt
RUN cat /tmp/caddy-root-ca.crt >> $(python -c "import certifi; print(certifi.where())") \
    && rm /tmp/caddy-root-ca.crt

ENV SERVICE_NAME=missiveattachmentdownloader

CMD ["python", "-m", "src.app"]
