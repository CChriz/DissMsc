FROM python:3.11-slim

WORKDIR /opt/webapp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8080

ENV DB_HOST=localhost
ENV DB_PORT=8080

ARG APP_VERSION
LABEL version="${APP_VERSION}"

CMD ["python", "-m", "app.main"]
