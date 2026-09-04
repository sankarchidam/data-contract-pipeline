FROM python:3.12-slim
WORKDIR /app

COPY consumer/requirements.txt consumer/requirements.txt
RUN pip install --no-cache-dir -r consumer/requirements.txt

COPY schemas/ schemas/
COPY consumer/ consumer/

CMD ["python", "consumer/consumer.py"]
