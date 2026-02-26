#!/usr/bin/env bash
set -e

echo "=== Step 1: Installing system dependencies ==="
sudo apt install -y python3.12-venv gcc-multilib wget unzip

echo "=== Step 2: Setting up Python environment ==="
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== Step 3: Installing Sikraken ==="
if [ ! -d "$HOME/sikraken" ]; then
    echo "Downloading Sikraken from Zenodo..."
    wget -O /tmp/sikraken.zip https://zenodo.org/records/18062402/files/sikraken.zip
    unzip /tmp/sikraken.zip -d "$HOME/sikraken"
    chmod -R +x "$HOME/sikraken/bin/"
    chmod -R +x "$HOME/sikraken/eclipse/"
    echo "✓ Sikraken installed at ~/sikraken/"
else
    echo "✓ Sikraken already installed — skipping"
fi

echo "=== Step 4: Patching run_pipeline.sh to auto-activate venv ==="
if ! grep -q "venv/bin/activate" run_pipeline.sh; then
    sed -i 's|^set -e$|set -e\nsource "$(dirname "$0")/venv/bin/activate"|' run_pipeline.sh
    echo "✓ venv auto-activation added to run_pipeline.sh"
else
    echo "✓ run_pipeline.sh already patched — skipping"
fi

echo ""
echo "=== Installation Complete! ==="
echo "Run: bash run_pipeline.sh filePATH/fileNAME"
