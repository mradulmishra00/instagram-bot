FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y wget gnupg
RUN playwright install chromium
RUN playwright install-deps
COPY bot.py .
CMD ["python", "bot.py"]