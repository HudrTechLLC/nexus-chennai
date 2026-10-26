FROM python:3.11-slim
WORKDIR /repo
COPY services/api/requirements.txt services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt
COPY services/api services/api
COPY cities cities
COPY data/sample data/sample
COPY run.py run.py
ENV PYTHONPATH=/repo/services/api PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0"]
