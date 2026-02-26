#!/usr/bin/env bash
set -e
echo "=== Installing system dependencies ==="
sudo apt install -y python3.12-venv gcc-multilib

echo "=== Setting up Python environment ==="
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== Done! Run: bash run_pipeline.sh filePATH/fileNAME ==="
