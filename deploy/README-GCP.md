# Deploying Job Agent to GCP VM

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed (`gcloud` CLI)
- A GCP project with billing enabled
- Your `config.yaml` and `.env` ready with credentials

## Step 1: Set up gcloud

```bash
# Login and set project
gcloud auth login
gcloud config set project job-application-agent-486905
```

## Step 2: Prepare your config

Edit your `config.yaml` with your profile, search preferences, and API keys.
You can use `config/sample_config.yaml` as a starting point:

```bash
cp config/sample_config.yaml my-config.yaml
# Edit my-config.yaml with your details
```

Create your `.env` file:

```bash
cp .env.example my-env
# Fill in your API keys and job board credentials
```

## Step 3: Create the VM

```bash
# Create an e2-small VM (cheapest option, ~$15/month)
gcloud compute instances create job-agent-vm \
    --zone=us-central1-a \
    --machine-type=e2-small \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --boot-disk-size=20GB \
    --metadata-from-file \
        startup-script=deploy/gcp-startup.sh,\
        job-agent-config=my-config.yaml,\
        job-agent-env=my-env \
    --tags=job-agent
```

## Step 4: Verify it's running

```bash
# SSH into the VM
gcloud compute ssh job-agent-vm --zone=us-central1-a

# Check the agent is installed
source /opt/job-agent/venv/bin/activate
job-agent status

# Check cron is scheduled
cat /etc/cron.d/job-agent

# View logs
tail -f /var/log/job-agent.log

# Run a manual test (dry run)
/opt/job-agent/deploy/run-agent.sh dry-run
```

## Schedule

By default, the VM runs:

| Time (UTC) | What |
|------------|------|
| 8:00 AM | Full pipeline (search + apply) |
| 6:00 PM | Full pipeline (search + apply) |
| 9:00 PM | Daily summary email |

To change the schedule, edit `/etc/cron.d/job-agent` on the VM:

```bash
gcloud compute ssh job-agent-vm --zone=us-central1-a
sudo nano /etc/cron.d/job-agent
```

## Updating Configuration

### Update config.yaml

```bash
# From your local machine
gcloud compute scp my-config.yaml job-agent-vm:/root/.job-agent/config.yaml --zone=us-central1-a
```

### Update .env

```bash
gcloud compute scp my-env job-agent-vm:/opt/job-agent/.env --zone=us-central1-a
```

### Update the agent code

```bash
gcloud compute ssh job-agent-vm --zone=us-central1-a
cd /opt/job-agent
git pull origin claude/job-application-agent-BacCD
source venv/bin/activate
pip install -e .
```

## Viewing Results

```bash
# SSH in and check dashboard
gcloud compute ssh job-agent-vm --zone=us-central1-a
source /opt/job-agent/venv/bin/activate
job-agent status

# Export applications to CSV and download
job-agent export --format csv -o /tmp/applications.csv
exit
gcloud compute scp job-agent-vm:/tmp/applications.csv ~/Downloads/ --zone=us-central1-a
```

## Cost Management

### Stop the VM when not needed

```bash
gcloud compute instances stop job-agent-vm --zone=us-central1-a
```

### Start it again

```bash
gcloud compute instances start job-agent-vm --zone=us-central1-a
```

### Delete the VM entirely

```bash
gcloud compute instances delete job-agent-vm --zone=us-central1-a
```

### Cost estimate

- **e2-small** (2 vCPU, 2GB RAM): ~$15/month running 24/7
- **e2-micro** (shared vCPU, 1GB RAM): ~$8/month (free tier eligible)
- If you only need it a few hours/day, use start/stop scheduling to save more

### Auto start/stop schedule (optional)

```bash
# Stop VM at midnight UTC, start at 7am UTC (saves ~70% cost)
gcloud compute resource-policies create instance-schedule job-agent-schedule \
    --region=us-central1 \
    --vm-start-schedule="0 7 * * *" \
    --vm-stop-schedule="0 0 * * *" \
    --timezone=UTC

gcloud compute instances add-resource-policies job-agent-vm \
    --resource-policies=job-agent-schedule \
    --zone=us-central1-a
```
