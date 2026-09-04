# Deliberately does NOT COPY schemas/ -- this consumer's reader schema is frozen
# in reader-schema-v1.avsc and must stay decoupled from the live contract file.
FROM python:3.12-slim
WORKDIR /app

COPY consumer-legacy/requirements.txt consumer-legacy/requirements.txt
RUN pip install --no-cache-dir -r consumer-legacy/requirements.txt

COPY consumer-legacy/ consumer-legacy/

CMD ["python", "consumer-legacy/consumer_legacy.py"]
