#!/bin/bash
# Wrapper script that activates the venv and runs the agent
# Called by cron on the GCP VM

set -e

APP_DIR=/opt/job-agent
LOG_PREFIX="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')]"

cd $APP_DIR

# Load environment variables
if [ -f "$APP_DIR/.env" ]; then
    set -a
    source "$APP_DIR/.env"
    set +a
fi

# Activate virtual environment
source venv/bin/activate

echo "$LOG_PREFIX Starting job agent..."

# Determine which command to run
COMMAND="${1:-run}"

case "$COMMAND" in
    run)
        echo "$LOG_PREFIX Running full pipeline with auto-apply..."
        job-agent run --auto-apply 2>&1
        ;;
    search)
        echo "$LOG_PREFIX Running search only..."
        job-agent search 2>&1
        ;;
    dry-run)
        echo "$LOG_PREFIX Running dry-run..."
        job-agent run --dry-run 2>&1
        ;;
    summary)
        echo "$LOG_PREFIX Sending daily summary..."
        job-agent summary 2>&1
        ;;
    *)
        echo "$LOG_PREFIX Unknown command: $COMMAND"
        exit 1
        ;;
esac

EXIT_CODE=$?
echo "$LOG_PREFIX Agent finished with exit code: $EXIT_CODE"
exit $EXIT_CODE
