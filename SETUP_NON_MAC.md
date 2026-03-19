# Setup Guide for Linux, Windows, and Cloud

This guide covers setting up the PDF/OCR Pipeline on non-macOS platforms.

## Platform Overview

| Platform | Recommended Method | GPU Support | Difficulty |
|----------|-------------------|-------------|------------|
| **Linux** | vLLM or SGLang | CUDA (NVIDIA) | Medium |
| **Windows** | WSL2 + Linux setup | CUDA via WSL2 | Medium |
| **Windows (Native)** | Ollama | Any (CPU/GPU) | Easy |
| **Any OS** | Docker | Host GPU | Easy |
| **Any OS** | Zhipu MaaS API | Cloud GPU | Easiest |

---

## Option 1: Zhipu MaaS API (Easiest - Any Platform)

Use the hosted cloud API instead of running locally. **No GPU required.**

### Setup

1. **Get API Key**: Sign up at https://open.bigmodel.cn and get an API key

2. **Configure the Pipeline**: Edit `config/extraction.yaml`

```yaml
pipeline:
  maas:
    enabled: true
    api_key: "your-api-key-here"  # Or set via ANTHROPIC_API_KEY env var
```

3. **Install Dependencies** (no mlx-vlm needed):
```bash
python3 -m pip install -r requirements.txt
# Skip: No poppler, no mlx-vlm, no conda needed
```

4. **Run Extraction**:
```bash
python3 -m src.cli extract data/batch3/MOZILLA/bug.pdf --method ocr
```

### Pros & Cons
- ✅ **Easiest setup** - Just an API key
- ✅ **Works on any platform** - Windows, Linux, macOS
- ✅ **No local GPU needed** - Uses cloud infrastructure
- ✅ **Scalable** - No performance limits
- ❌ **Costs money** - Per-page pricing (~$0.001-0.01 per page)
- ❌ **Requires internet** - Can't work offline
- ❌ **Data privacy** - PDFs sent to cloud

---

## Option 2: Docker (Universal - Any Platform with Docker)

Run everything in containers. Works on Linux, Windows, macOS.

### Prerequisites
- Install Docker: https://docs.docker.com/get-docker/
- Install Docker Compose

### Setup

1. **Create Docker Compose file** (`docker-compose.yml`):

```yaml
version: '3.8'

services:
  # GLM-OCR Server
  glm-ocr:
    image: vllm/vllm-openai:latest
    ports:
      - "8080:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    command: >
      serve zai-org/GLM-OCR
      --port 8000
      --served-model-name glm-ocr
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    # For CPU-only, remove the deploy section above

  # Neo4j Database
  neo4j:
    image: neo4j:latest
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data

  # Pipeline Runner
  pipeline:
    build: .
    volumes:
      - ./data:/app/data
      - ./src:/app/src
      - ./config:/app/config
    depends_on:
      - glm-ocr
      - neo4j
    environment:
      - OCR_API_HOST=glm-ocr
      - OCR_API_PORT=8000
      - NEO4J_URI=bolt://neo4j:7687

volumes:
  neo4j_data:
```

2. **Create Dockerfile** (`Dockerfile`):

```dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set working directory
WORKDIR /app

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Default command
CMD ["python3", "-m", "src.cli"]
```

3. **Start Services**:

```bash
# Start GLM-OCR server and Neo4j
docker-compose up -d glm-ocr neo4j

# Wait for model download (first time only, ~5-10 min)
docker-compose logs -f glm-ocr

# Run pipeline
docker-compose run pipeline python3 -m src.cli extract-batch data/batch3/MOZILLA --limit 10
```

### Pros & Cons
- ✅ **Universal** - Same setup on all platforms
- ✅ **Isolated** - No conflicts with system packages
- ✅ **Reproducible** - Same environment everywhere
- ✅ **Easy deployment** - Single command to start everything
- ❌ **Requires Docker knowledge**
- ❌ **GPU setup can be tricky** on some platforms
- ❌ **More resource overhead**

---

## Option 3: Linux (Native with vLLM)

For Linux users with NVIDIA GPUs.

### Prerequisites
- NVIDIA GPU with CUDA support (GTX 1060 6GB+ or better)
- CUDA Toolkit 11.8 or 12.1
- Python 3.10+

### Setup

1. **Install CUDA** (if not already installed):
```bash
# Ubuntu/Debian
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-1

# Verify
nvidia-smi
nvcc --version
```

2. **Install vLLM**:
```bash
# Create environment
python3 -m venv venv
source venv/bin/activate

# Install vLLM with CUDA support
pip install vllm

# Verify GPU is detected
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python3 -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

3. **Download Model & Start Server**:
```bash
# The model will download automatically on first run (~2GB)
vllm serve zai-org/GLM-OCR \
  --port 8080 \
  --served-model-name glm-ocr \
  --max-model-len 8192

# For GPUs with limited VRAM (4-6GB), add quantization:
vllm serve zai-org/GLM-OCR \
  --port 8080 \
  --served-model-name glm-ocr \
  --quantization awq \
  --max-model-len 4096
```

4. **Install Pipeline Dependencies**:
```bash
# In a separate terminal (project directory)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install poppler (Ubuntu/Debian)
sudo apt-get install poppler-utils

# Install poppler (Fedora/RHEL)
sudo dnf install poppler-utils

# Install poppler (Arch)
sudo pacman -S poppler
```

5. **Verify & Run**:
```bash
# Test server
curl http://localhost:8080/v1/models

# Run extraction
python3 -m src.cli extract data/batch3/MOZILLA/bug.pdf --method ocr
```

### GPU Memory Requirements

| GPU VRAM | Command | Speed |
|----------|---------|-------|
| 4-6 GB | Add `--quantization awq` | ~30s/page |
| 8 GB | Default | ~15s/page |
| 12+ GB | Default | ~10s/page |
| 24+ GB | Add `--tensor-parallel-size 2` | ~5s/page |

### Troubleshooting Linux

**"CUDA out of memory"**:
```bash
# Reduce batch size and context
vllm serve zai-org/GLM-OCR \
  --port 8080 \
  --max-num-seqs 1 \
  --max-model-len 2048
```

**"No module named 'vllm'"**:
```bash
# Reinstall with CUDA support
pip uninstall vllm
pip install vllm --no-cache-dir
```

**Slow performance**:
- Check GPU utilization: `watch -n 1 nvidia-smi`
- If GPU not used, reinstall CUDA drivers
- Try SGLang instead: `pip install sglang && sglang serve zai-org/GLM-OCR`

---

## Option 4: Windows with WSL2 (Recommended for Windows)

Run Linux environment within Windows.

### Prerequisites
- Windows 10/11 with WSL2 enabled
- NVIDIA GPU with WSL2 CUDA support

### Setup

1. **Enable WSL2**:
```powershell
# Run in PowerShell as Administrator
wsl --install
wsl --set-default-version 2

# Restart computer, then install Ubuntu
wsl --install -d Ubuntu-22.04
```

2. **Install NVIDIA CUDA in WSL2**:
```powershell
# Download and install: https://developer.nvidia.com/cuda-downloads?target_os=Linux&target_arch=x86_64&distribution=WSL-Ubuntu&version=2.0
# Or follow: https://docs.nvidia.com/cuda/wsl-user-guide/index.html
```

3. **Setup in WSL2 Ubuntu**:
```bash
# Open WSL2 terminal
wsl

# Follow "Option 3: Linux" instructions above
# All commands work exactly the same in WSL2

# Install poppler
sudo apt-get update
sudo apt-get install poppler-utils

# Setup vLLM and run...
```

4. **Access from Windows**:
```powershell
# In Windows PowerShell, you can access WSL2 files
# WSL2 runs on localhost just like macOS

# Test connection
curl http://localhost:8080/v1/models

# Run pipeline (from Windows, accessing WSL2 server)
python3 -m src.cli extract data/batch3/MOZILLA/bug.pdf --method ocr
```

### File Access Between Windows and WSL2

```powershell
# Access WSL2 files from Windows
notepad "\\wsl$\Ubuntu-22.04\home\username\project\config\extraction.yaml"

# Or from WSL2, access Windows files
cd /mnt/c/Users/YourName/Desktop/project
```

### Pros & Cons
- ✅ **Full Linux environment** on Windows
- ✅ **GPU passthrough works** with WSL2
- ✅ **Same performance** as native Linux
- ✅ **Best of both worlds** - Linux tools, Windows desktop
- ❌ **Slightly more complex** setup
- ❌ **WSL2 uses memory** even when idle

---

## Option 5: Windows Native with Ollama

Simplest native Windows option, but CPU-only or limited GPU support.

### Prerequisites
- Windows 10/11
- No strict GPU requirements (CPU mode works)

### Setup

1. **Install Ollama**: https://ollama.com/download/windows

2. **Download GLM-OCR Model**:
```powershell
# In PowerShell or CMD
ollama pull zai-org/glm-ocr

# This downloads the model (~2GB)
```

3. **Start Server**:
```powershell
# Keep this running in a window
ollama serve

# By default runs on port 11434
```

4. **Install Project Dependencies**:
```powershell
# Install Python packages
python3 -m pip install -r requirements.txt

# Install poppler (use chocolatey)
choco install poppler

# Or download from: https://github.com/oschwartz10612/poppler-windows/releases/
# Then add to PATH
```

5. **Configure for Ollama**: Edit `config/extraction.yaml`

```yaml
pipeline:
  ocr_api:
    api_host: localhost
    api_port: 11434
    api_path: /api/generate  # Ollama API path
    model: zai-org/glm-ocr
```

6. **Modify OCR Client for Ollama**:

Create `src/extraction/ocr_ollama.py`:

```python
import requests
import base64

def extract_ocr_ollama(image_path: str) -> str:
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "zai-org/glm-ocr",
            "prompt": "Extract all text from this image",
            "images": [img_b64],
            "stream": False
        }
    )
    return response.json()["response"]
```

### Pros & Cons
- ✅ **Easiest Windows setup**
- ✅ **Native Windows app** - no virtualization
- ✅ **CPU mode works** - no GPU required
- ❌ **Slower** - 2-5x slower than GPU
- ❌ **Limited GPU support** - Not as optimized as vLLM
- ❌ **Requires code changes** - Different API than mlx-vlm

---

## Performance Comparison

| Platform | Setup | Speed (per page) | GPU Memory |
|----------|-------|------------------|------------|
| macOS + mlx-vlm | Easy | 60-120s | 3-4 GB |
| Linux + vLLM | Medium | 10-15s | 6-8 GB |
| Windows WSL2 + vLLM | Medium | 10-15s | 6-8 GB |
| Docker + vLLM | Easy | 10-15s | 6-8 GB |
| Cloud API | Easiest | 2-5s | N/A (cloud) |
| Windows + Ollama | Easy | 120-300s | 0 (CPU) |

---

## Quick Decision Guide

**"I want the easiest setup"**
→ Use **Zhipu MaaS API** (Option 1)

**"I have a Mac"**
→ Use **mlx-vlm** (Original README)

**"I have a Windows PC with NVIDIA GPU"**
→ Use **WSL2 + vLLM** (Option 4)

**"I have a Linux workstation with NVIDIA GPU"**
→ Use **Native vLLM** (Option 3)

**"I want consistent setup across team"**
→ Use **Docker** (Option 2)

**"I have no GPU or weak GPU"**
→ Use **Cloud API** or **Ollama in CPU mode**

---

## Common Configuration

Regardless of platform, create `config/platform.yaml`:

```yaml
# Choose your platform
platform: "auto"  # auto, macos, linux, windows, docker, cloud

# Auto-detect and configure
auto_detect:
  prefer_cloud: false  # Set true to always use cloud API
  max_local_vram_gb: 8  # Auto-switch to cloud if VRAM < 8GB

# Platform-specific overrides
platforms:
  macos:
    server_type: "mlx_vlm"
    default_port: 8080
  
  linux:
    server_type: "vllm"
    default_port: 8080
    gpu_backend: "cuda"
  
  windows_wsl2:
    server_type: "vllm"
    default_port: 8080
    use_wsl2: true
  
  windows_ollama:
    server_type: "ollama"
    default_port: 11434
  
  docker:
    server_type: "vllm"
    compose_file: "docker-compose.yml"
  
  cloud:
    provider: "zhipu"
    api_endpoint: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
```

---

## Need Help?

- **macOS issues**: See `mlx_vlm_README.md`
- **Linux GPU issues**: Check [vLLM docs](https://docs.vllm.ai/en/latest/)
- **Windows WSL2 issues**: See [NVIDIA WSL2 Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- **Docker issues**: Run `docker-compose logs` to see errors
- **Cloud API issues**: Check [Zhipu docs](https://open.bigmodel.cn/)

---

**Recommendation for Teams**: Use **Docker** for consistent environments across all platforms.
