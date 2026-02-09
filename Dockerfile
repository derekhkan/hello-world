FROM python:3.11-slim

# Install Chrome for Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg2 \
    curl \
    unzip \
    cron \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /root/.job-agent/data/resumes \
    /root/.job-agent/data/cover_letters \
    /root/.job-agent/data/exports

ENTRYPOINT ["job-agent"]
CMD ["run", "--dry-run"]
