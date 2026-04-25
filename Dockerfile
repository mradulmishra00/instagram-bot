FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Create necessary directories
RUN mkdir -p /app/logs /app/cache

# Run bot with unbuffered output
CMD ["python", "-u", "bot.py"]
