FROM python:3.12-slim
WORKDIR /app

COPY scripts/requirements.txt scripts/requirements.txt
RUN pip install --no-cache-dir -r scripts/requirements.txt

COPY scripts/ scripts/
COPY schemas/ schemas/

CMD ["python", "scripts/register_schema.py", "--help"]
