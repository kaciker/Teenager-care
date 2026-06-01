FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn python-multipart jinja2 

COPY app /app

EXPOSE 8097

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8097"]
