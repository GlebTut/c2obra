#!/usr/bin/env bash
set -e

echo "=== Step 1: Installing system dependencies ==="
sudo apt install -y python3.12-venv gcc-multilib wget unzip

echo "=== Step 2: Setting up Python environment ==="
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== Step 3: Installing Sikraken ==="
SIKRAKEN_DIR="$HOME/sikraken"
SIKRAKEN_BIN="$SIKRAKEN_DIR/bin/sikraken.sh"

# Remove broken/incomplete installation if bin/sikraken.sh is missing
if [ -d "$SIKRAKEN_DIR" ] && [ ! -f "$SIKRAKEN_BIN" ]; then
    echo "⚠️  Sikraken folder exists but is incomplete — removing and reinstalling..."
    rm -rf "$SIKRAKEN_DIR"
fi

if [ ! -d "$SIKRAKEN_DIR" ]; then
    echo "Downloading Sikraken from Zenodo (record 14014796)..."
    wget -O /tmp/sikraken.zip \
        "https://zenodo.org/records/14014796/files/sikraken.zip?download=1"
    mkdir -p "$SIKRAKEN_DIR"
    unzip /tmp/sikraken.zip -d "$SIKRAKEN_DIR"
    # Handle nested folder if zip extracts into subfolder
    INNER=$(find "$SIKRAKEN_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)
    if [ -n "$INNER" ] && [ ! -f "$SIKRAKEN_BIN" ]; then
        mv "$INNER"/* "$SIKRAKEN_DIR"/
        rmdir "$INNER"
    fi
    find "$SIKRAKEN_DIR/bin" -type f -exec chmod +x {} \;
    find "$SIKRAKEN_DIR/eclipse" -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
    rm /tmp/sikraken.zip
    echo "✓ Sikraken installed at $SIKRAKEN_DIR"
else
    echo "✓ Sikraken already installed — skipping"
fi

# Verify
if [ ! -f "$SIKRAKEN_BIN" ]; then
    echo "❌ ERROR: $SIKRAKEN_BIN still not found after install. Check the zip structure."
    echo "   Contents of $SIKRAKEN_DIR:"
    find "$SIKRAKEN_DIR" -maxdepth 3 | head -30
    exit 1
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
