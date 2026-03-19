# Setup and Installation Guide

Complete setup instructions for macOS, Linux, and Windows environments.

## Prerequisites

Before starting, ensure you have:
- Python 3.8 or higher
- 16GB+ RAM recommended (8GB minimum)
- 50GB+ free disk space for data and models
- Git for cloning repositories

## macOS Setup (Detailed)

### Step 1: Install System Dependencies

Install Homebrew if not already installed:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install required packages:
```bash
brew install python@3.11 poppler git
```

**Why Poppler?**
- pdf2image library requires Poppler for PDF rendering
- Provides pdftoppm, pdfinfo, and other utilities

### Step 2: Clone and Setup Project

```bash
cd "/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project"

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (takes 5-10 minutes)
pip install -r requirements.txt
```

### Step 3: Verify Installation

```bash
# Test extraction imports
python3 -c "from src.extraction import extract_native, extract_ocr; print('✓ Extraction imports OK')"

# Test LLM imports
python3 -c "from src.llm import get_client; print('✓ LLM imports OK')"

# Test Neo4j imports
python3 -c "from src.kg import get_client; print('✓ KG imports OK')"
```

### Step 4: Start Neo4j (Required for Knowledge Graph)

```bash
# Start Neo4j container
docker compose up -d

# Verify it's running
docker compose ps

# Check logs
docker compose logs -f neo4j
```

Wait for message: "Started Neo4j" in logs.

### Step 5: Initialize Neo4j Schema

```bash
source venv/bin/activate
python3 -m src.cli kg init
```

Expected output: "✓ Schema initialized successfully"

### Step 6: Test Single PDF Extraction

```bash
# Test with a sample PDF
python3 -m src.cli extract data/batch3/MOZILLA/MOZILLA-XXXXXX-X.pdf \
  --method hybrid \
  --output test_output.json
```

## Linux Setup (Ubuntu/Debian)

### Step 1: Install System Dependencies

```bash
# Update package list
sudo apt-get update

# Install Python, Poppler, and Git
sudo apt-get install -y python3.11 python3.11-venv python3-pip poppler-utils git

# Install pdf2image dependencies
sudo apt-get install -y libxml2-dev libxslt1-dev
```

### Step 2: Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd pdf-ocr-knowledge-graph

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Install Docker (for Neo4j)

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login again for group changes to take effect
```

### Step 4: Start Services

```bash
# Start Neo4j
docker compose up -d

# Initialize schema
python3 -m src.cli kg init
```

## Windows Setup

### Option 1: WSL2 (Recommended)

**Why WSL2?**
- Native Linux environment on Windows
- Better compatibility with Python packages
- Poppler installation is easier

**Setup:**
1. Enable WSL2: `wsl --install`
2. Install Ubuntu from Microsoft Store
3. Follow Linux setup instructions above

### Option 2: Native Windows

**Prerequisites:**
1. Install Python 3.11 from python.org
2. Install Git for Windows
3. Install Poppler for Windows:
   - Download from: https://github.com/oschwartz10612/poppler-windows/releases
   - Extract to `C:\Program Files\poppler`
   - Add to PATH: `C:\Program Files\poppler\bin`

**Setup:**
```powershell
# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Docker for Windows:**
- Install Docker Desktop
- Enable WSL2 backend in settings
- Start Neo4j: `docker compose up -d`

## Cloud Setup (Google Colab / Jupyter)

### Option 1: Google Colab

**Limitations:**
- No persistent storage
- Poppler installation required each session
- Neo4j can't run in background

**Setup:**
```python
# Cell 1: Install dependencies
!apt-get install -y poppler-utils
!pip install -r requirements.txt

# Cell 2: Clone repository
!git clone <repository-url>
%cd pdf-ocr-knowledge-graph

# Cell 3: Connect to external Neo4j
# Use Neo4j Aura (cloud) or run locally with ngrok
```

### Option 2: Jupyter Notebook Server

Setup on cloud VM (AWS/GCP/Azure):

```bash
# SSH into VM
ssh user@your-vm-ip

# Follow Linux setup
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv poppler-utils

# Clone and setup
git clone <repository-url>
cd pdf-ocr-knowledge-graph
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start Jupyter
jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser
```

## Virtual Environment Best Practices

### Activation

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```powershell
venv\Scripts\activate
```

### Deactivation
```bash
deactivate
```

### Managing Dependencies

**After adding new packages:**
```bash
pip freeze > requirements.txt
```

**Updating dependencies:**
```bash
pip install --upgrade -r requirements.txt
```

## Environment Variables

Create `.env` file in project root:

```bash
# LLM API Keys (optional, only if using cloud providers)
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here

# Neo4j (optional, uses defaults if not set)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

**Loading .env:**
```bash
source venv/bin/activate
export $(cat .env | xargs)
```

## Troubleshooting

### Issue: Poppler not found

**Error:** `pdf2image.exceptions.PDFInfoNotInstalledError`

**Solution (macOS):**
```bash
brew install poppler
which pdfinfo  # Should show path
```

**Solution (Linux):**
```bash
sudo apt-get install poppler-utils
```

**Solution (Windows):**
- Ensure `C:\Program Files\poppler\bin` is in PATH
- Restart terminal after adding to PATH

### Issue: Permission denied (Docker)

**Error:** `Cannot connect to the Docker daemon`

**Solution (Linux):**
```bash
sudo usermod -aG docker $USER
# Logout and login again
```

**Solution (macOS):**
- Open Docker Desktop
- Wait for whale icon to appear in menu bar

### Issue: Import errors

**Error:** `ModuleNotFoundError: No module named 'src'`

**Solution:**
```bash
# Ensure you're in project root
cd "/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project"

# Activate venv
source venv/bin/activate

# Install in editable mode (optional)
pip install -e .
```

### Issue: Out of memory during processing

**Solution:**
- Reduce parallel workers: `--workers 1`
- Limit pages: `--max-pages 5`
- Close other applications

### Issue: Neo4j connection refused

**Error:** `Failed to establish connection`

**Solution:**
```bash
# Check if Neo4j is running
docker compose ps

# If not running, start it
docker compose up -d

# Check logs for errors
docker compose logs neo4j | tail -50
```

## Verification Checklist

Before proceeding, verify:

- [ ] Python 3.8+ installed
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Poppler installed and accessible
- [ ] Docker running (for Neo4j)
- [ ] Neo4j container started (`docker compose up -d`)
- [ ] Neo4j schema initialized (`python3 -m src.cli kg init`)
- [ ] Test extraction works (`python3 -m src.cli extract ...`)
- [ ] Training data file exists (`training_data.json`)

## Quick Start Commands

After setup, common workflow:

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Start Neo4j (if not running)
docker compose up -d

# 3. Process PDFs
python3 scripts/process_mixed_batch.py --total 100

# 4. Build knowledge graph
python3 scripts/build_knowledge_graph.py --all --max-pages 15

# 5. Launch annotation tool
streamlit run src/evaluation/ground_truth_tool.py
```

## Next Steps

1. **Read PROJECT_OVERVIEW.md** for system architecture
2. **Try CLI_REFERENCE.md** for available commands
3. **Follow EXTRACTION_PIPELINE.md** for PDF processing
4. **Check TROUBLESHOOTING.md** if issues arise

---

**Setup Time Estimate:**
- macOS: 30-45 minutes
- Linux: 20-30 minutes  
- Windows (WSL2): 45-60 minutes
- Windows (Native): 60-90 minutes

**Support:** Refer to TROUBLESHOOTING.md for detailed error resolution.
