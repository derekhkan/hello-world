#!/bin/bash
# DadStrong Instagram Agent — Google Cloud VM Setup Script
# Run this after SSH'ing into your new e2-micro VM
#
# Usage:
#   curl -sL <raw-github-url>/deploy.sh | bash
#   — or —
#   git clone <your-repo> && cd hello-world && bash deploy.sh

set -e

echo "=== DadStrong Agent — Cloud Deployment ==="
echo ""

# 1. System packages
echo "[1/5] Installing system packages..."
sudo apt update -qq
sudo apt install -y python3 python3-venv python3-pip git ffmpeg

# 2. Clone repo (if not already in it)
REPO_DIR="$HOME/hello-world"
if [ ! -f "$REPO_DIR/main.py" ]; then
    echo "[2/5] Cloning repository..."
    git clone https://github.com/derekhkan/hello-world.git "$REPO_DIR"
else
    echo "[2/5] Repository already exists, pulling latest..."
    cd "$REPO_DIR" && git pull origin main
fi

cd "$REPO_DIR"

# 3. Python virtual environment + deps
echo "[3/5] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. Check for config.yaml
if [ ! -f "$REPO_DIR/config.yaml" ]; then
    echo ""
    echo "============================================"
    echo "  config.yaml not found!"
    echo "  You need to create it before starting."
    echo ""
    echo "  Option A — paste it directly:"
    echo "    nano $REPO_DIR/config.yaml"
    echo ""
    echo "  Option B — copy from your Mac:"
    echo "    scp config.yaml USER@VM_IP:~/hello-world/"
    echo "============================================"
    echo ""
fi

# 5. Create systemd service
echo "[4/5] Creating systemd service..."
sudo tee /etc/systemd/system/dadstrong.service > /dev/null << EOF
[Unit]
Description=DadStrong Instagram Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/venv/bin/python3 main.py run --config config.yaml
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dadstrong

echo "[5/5] Setup complete!"
echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Create your config.yaml (if you haven't):"
echo "   nano $REPO_DIR/config.yaml"
echo ""
echo "2. Start the agent:"
echo "   sudo systemctl start dadstrong"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status dadstrong"
echo ""
echo "4. View live logs:"
echo "   sudo journalctl -u dadstrong -f"
echo ""
echo "5. Stop the agent:"
echo "   sudo systemctl stop dadstrong"
echo ""
echo "The agent will auto-start on VM reboot."
echo "==================================="
