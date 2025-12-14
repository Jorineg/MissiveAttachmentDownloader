FROM jorineg/ibhelm-base:latest

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

ENV SERVICE_NAME=missiveattachmentdownloader

CMD ["python", "-m", "src.app"]
