FROM python:3.12-slim

WORKDIR /app

COPY colombina/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY colombina/. .
COPY shared ./shared

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import sys; sys.exit(0)"
