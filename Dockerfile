FROM ubuntu:22.04
WORKDIR /app

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright and browsers
RUN pip3 install playwright
RUN playwright install chromium
RUN playwright install-deps

# Copy and install Python requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Run bot
CMD ["python3", "-u", "bot.py"]
