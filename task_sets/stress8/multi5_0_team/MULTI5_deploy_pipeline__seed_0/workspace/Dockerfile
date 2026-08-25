FROM python:3.11-slim

WORKDIR /opt/webapp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# BUG: copies from src/ but the actual code is in app/
COPY src/ ./app/

EXPOSE 8080

ENV DB_HOST=localhost
ENV DB_PORT=8080

# BUG: references APP_VERSION but no ARG defined
LABEL version="${APP_VERSION}"

CMD ["python", "-m", "app.main"]
