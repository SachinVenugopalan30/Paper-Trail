#!/bin/bash
# Setup script for PDF/OCR Pipeline

set -e

echo "🚀 Setting up PDF/OCR Extraction Pipeline..."
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if [[ ! "$python_version" =~ ^3\.(10|11|12) ]]; then
    echo "⚠️  Warning: Python 3.10+ recommended. Current: $python_version"
    echo ""
fi


source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo "📚 Installing Python packages..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""

# Check for poppler
echo "🔍 Checking system dependencies..."

if command -v brew &> /dev/null; then
    if ! brew list poppler &> /dev/null; then
        echo "⚠️  Poppler not found. Install with: brew install poppler"
    else
        echo "✅ Poppler found (macOS)"
    fi
elif command -v apt-get &> /dev/null; then
    if ! dpkg -l | grep -q poppler-utils; then
        echo "⚠️  Poppler not found. Install with: sudo apt-get install poppler-utils"
    else
        echo "✅ Poppler found (Linux)"
    fi
elif command -v conda &> /dev/null; then
    echo "ℹ️  Conda detected. You may need to install poppler: conda install -c conda-forge poppler"
else
    echo "⚠️  Could not detect package manager. Please install poppler manually."
fi

echo ""
echo "🎯 Next steps:"
echo ""
echo "1. Activate the environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Setup GLM-OCR server (macOS):"
echo "   conda create -n mlx-env python=3.12 -y"
echo "   conda activate mlx-env"
echo "   pip install git+https://github.com/Blaizzy/mlx-vlm.git"
echo "   mlx_vlm.server --trust-remote-code"
echo ""
echo "3. Configure LLM provider in config/llm.yaml"
echo ""
echo "4. Run extraction:"
echo "   python -m src.cli extract <pdf_path> --method hybrid"
echo ""
echo "📖 See README.md for full documentation"
