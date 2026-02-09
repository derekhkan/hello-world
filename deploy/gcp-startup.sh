#!/bin/bash
# GCP VM startup script - installs and configures the job agent
# Used as --metadata-from-file startup-script=deploy/gcp-startup.sh

set -e

echo "=== Job Agent VM Setup ==="

# Install system dependencies
apt-get update
apt-get install -y python3 python3-pip python3-venv git wget gnupg2 cron

# Install Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable

# Set up app directory
APP_DIR=/opt/job-agent
mkdir -p $APP_DIR
cd $APP_DIR

# Clone the repo (or pull latest)
if [ -d ".git" ]; then
    git pull origin claude/job-application-agent-BacCD
else
    git clone https://github.com/derekhkan/hello-world.git .
    git checkout claude/job-application-agent-BacCD
fi

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .

# Create config directory
mkdir -p /root/.job-agent/data/resumes
mkdir -p /root/.job-agent/data/cover_letters
mkdir -p /root/.job-agent/data/exports

# Load config from GCP metadata if available
CONFIG_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes/job-agent-config"
if curl -sf -H "Metadata-Flavor: Google" "$CONFIG_URL" > /dev/null 2>&1; then
    echo "Loading config from instance metadata..."
    curl -sf -H "Metadata-Flavor: Google" "$CONFIG_URL" > /root/.job-agent/config.yaml
fi

# Load env vars from GCP metadata
ENV_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes/job-agent-env"
if curl -sf -H "Metadata-Flavor: Google" "$ENV_URL" > /dev/null 2>&1; then
    echo "Loading environment variables from metadata..."
    curl -sf -H "Metadata-Flavor: Google" "$ENV_URL" > /opt/job-agent/.env
fi

# Set up cron job - runs pipeline twice daily at 8am and 6pm UTC
CRON_SCRIPT=/opt/job-agent/deploy/run-agent.sh
chmod +x $CRON_SCRIPT

# Write cron entries
cat > /etc/cron.d/job-agent << 'CRON'
# Run job search + apply pipeline twice daily
0 8 * * * root /opt/job-agent/deploy/run-agent.sh >> /var/log/job-agent.log 2>&1
0 18 * * * root /opt/job-agent/deploy/run-agent.sh >> /var/log/job-agent.log 2>&1

# Send daily summary at 9pm UTC
0 21 * * * root /opt/job-agent/deploy/run-agent.sh summary >> /var/log/job-agent.log 2>&1
CRON

chmod 644 /etc/cron.d/job-agent

# Start cron
service cron start

# Create log file
touch /var/log/job-agent.log

echo "=== Job Agent Setup Complete ==="
echo "Cron jobs scheduled: 8:00 UTC and 18:00 UTC daily"
echo "Logs: /var/log/job-agent.log"
