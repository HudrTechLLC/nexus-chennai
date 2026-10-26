# Judge entry point: docker build -t oah-submission . && docker run --rm -p 8000:8000 --env-file .env oah-submission
# SAMPLE_MODE=true runs with no Zetaris, Nightshift or credentials.
FROM python:3.11-slim
WORKDIR /repo
COPY services/api/requirements.txt services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt
COPY services/api services/api
COPY cities cities
COPY data/sample data/sample
COPY run.py run.py
RUN mkdir -p /repo/logs
ENV PYTHONPATH=/repo/services/api PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0"]
