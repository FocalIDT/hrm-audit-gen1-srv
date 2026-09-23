FROM python:3.11

WORKDIR /app
COPY . /app
COPY .env /app/

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8016

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8016"]
