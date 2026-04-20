FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi uvicorn httpx jinja2

COPY . .

EXPOSE 3000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]
