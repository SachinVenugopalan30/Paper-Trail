# Configuration Guide

Complete reference for configuring the PDF Extraction and Knowledge Graph system.

## Table of Contents

1. [Configuration Overview](#1-configuration-overview)
2. [extraction.yaml](#2-extractionyaml)
3. [llm.yaml](#3-llmyaml)
4. [neo4j.yaml](#4-neo4jyaml)
5. [Environment Variables](#5-environment-variables)
6. [Configuration Loading](#6-configuration-loading)
7. [Best Practices](#7-best-practices)
8. [Troubleshooting Config Issues](#8-troubleshooting-config-issues)

---

## 1. Configuration Overview

The system uses three main configuration files to control extraction, LLM processing, and database connectivity.

### Three Main Config Files

| File | Purpose |
|------|---------|
| `extraction.yaml` | PDF processing and OCR settings |
| `llm.yaml` | LLM provider configurations and entity extraction |
| `neo4j.yaml` | Neo4j database connection and schema |

### YAML Format

All configuration files use **YAML** (YAML Ain't Markup Language) format with the following characteristics:
- Human-readable structured data
- Indentation-based (2 spaces recommended)
- Supports comments with `#`
- Environment variable substitution with `${VAR}` or `${VAR:-default}`

### Environment Variable Substitution

Environment variables can be embedded in YAML files:

```yaml
# Basic substitution
api_key: ${OPENAI_API_KEY}

# With default value (uses 'localhost' if NEO4J_HOST not set)
host: ${NEO4J_HOST:-localhost}
```

### Location: config/ Directory

```
project/
├── config/
│   ├── extraction.yaml
│   ├── llm.yaml
│   └── neo4j.yaml
├── .env
└── src/
```

---

## 2. extraction.yaml

Controls PDF processing parameters, OCR settings, and document extraction behavior.

### Complete File Structure

```yaml
pdf_dpi: 200
native_threshold: 0.8
api_host: localhost:8080
model: mlx-community/GLM-OCR-bf16
max_tokens: 4096
timeout: 300
parallel_workers: 4

# OCR-specific settings
ocr:
  dpi: 200
  timeout: 300
  
# Batch processing
batch:
  max_documents: 10
  concurrent_limit: 2
```

### Setting Reference

| Setting | Default | Description | Tuning Recommendation |
|---------|---------|-------------|----------------------|
| `pdf_dpi` | 200 | DPI for PDF to image conversion | Higher = better quality but slower (150-300) |
| `native_threshold` | 0.8 | Confidence threshold for native text extraction | Increase for cleaner documents, decrease for scanned PDFs |
| `api_host` | localhost:8080 | OCR/LLM API endpoint | Set to your inference server |
| `model` | mlx-community/GLM-OCR-bf16 | OCR model identifier | Choose based on language/script requirements |
| `max_tokens` | 4096 | Maximum tokens per extraction request | Increase for complex layouts, decrease for faster processing |
| `timeout` | 300 | Request timeout in seconds | Increase for large documents or slow networks |
| `parallel_workers` | 4 | Number of concurrent extraction workers | Set to number of CPU cores - 1 |
| `ocr.dpi` | 200 | OCR-specific DPI setting | Match `pdf_dpi` for consistency |
| `ocr.timeout` | 300 | OCR-specific timeout | Set higher than main timeout for safety |

### Purpose of Each Setting

#### pdf_dpi / ocr.dpi
Controls the resolution when converting PDF pages to images for OCR processing:
- **150 DPI**: Fast, suitable for clean text
- **200 DPI**: Balanced quality and speed (recommended)
- **300 DPI**: High quality, slower processing
- **400+ DPI**: Only for fine-detail documents

#### native_threshold
Determines when to use native PDF text vs OCR:
- **0.8-1.0**: Prefer native text (faster, more accurate for digital PDFs)
- **0.5-0.7**: Balanced approach
- **0.1-0.4**: Prefer OCR (better for scanned documents)

#### api_host / model
Configure the local LLM/OCR inference server:
- Supports Ollama, vLLM, and custom endpoints
- Model names must match server-side model registry
- bf16/quantized models reduce memory usage

#### max_tokens
Controls LLM response length:
- Increase for tables, multi-column layouts
- Decrease for simple single-column text
- Must not exceed model's context window

#### parallel_workers
Controls extraction concurrency:
- Set based on available CPU/GPU resources
- More workers = faster but more memory usage
- Consider I/O bottlenecks on spinning disks

### Tuning Recommendations

**High-Quality Scanned Documents:**
```yaml
pdf_dpi: 300
native_threshold: 0.3
ocr:
  dpi: 300
parallel_workers: 2  # Reduce to prevent memory issues
```

**Fast Processing for Digital PDFs:**
```yaml
pdf_dpi: 150
native_threshold: 0.9
max_tokens: 2048
parallel_workers: 8
```

**Server Deployment:**
```yaml
pdf_dpi: 200
native_threshold: 0.8
api_host: 192.168.1.100:8080  # Remote GPU server
model: mlx-community/GLM-OCR-q4  # Quantized for efficiency
parallel_workers: 16
```

---

## 3. llm.yaml

Configures LLM providers for entity extraction and text processing.

### Complete File Structure

```yaml
# Default provider selection
default_provider: ollama

# Provider configurations
providers:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    max_tokens: 4096
    temperature: 0.1
    
  claude:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-opus-20240229
    max_tokens: 4096
    temperature: 0.1
    
  gemini:
    enabled: false
    api_key: ${GOOGLE_API_KEY}
    model: gemini-1.5-pro-latest
    max_tokens: 8192
    temperature: 0.1
    
  ollama:
    enabled: true
    base_url: http://localhost:11434
    model: llama3.1:70b
    max_tokens: 4096
    temperature: 0.1

# Extraction settings
extraction:
  chunk_size: 2000
  chunk_overlap: 200
  
# Entity and relation definitions
schema:
  entity_types:
    - Person
    - Organization
    - Location
    - Date
    - Product
    - Technology
    - Concept
    - Event
    
  relation_types:
    - WORKS_FOR
    - LOCATED_IN
    - CREATED
    - PART_OF
    - MENTIONS
    - RELATED_TO
    - DEVELOPED_BY
```

### Provider Configurations

#### OpenAI

```yaml
providers:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}      # Required
    model: gpt-4                    # Options: gpt-4, gpt-4-turbo, gpt-3.5-turbo
    max_tokens: 4096                # Max: 8192 for GPT-4, 4096 for GPT-3.5
    temperature: 0.1                # 0.0-2.0, lower = more deterministic
```

**Environment Variable:**
```bash
export OPENAI_API_KEY="sk-..."
```

#### Claude (Anthropic)

```yaml
providers:
  claude:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}   # Required
    model: claude-3-opus-20240229   # Options: claude-3-opus, claude-3-sonnet, claude-3-haiku
    max_tokens: 4096                # Max: 4096 for API
    temperature: 0.1                # 0.0-1.0
```

**Environment Variable:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

#### Gemini (Google)

```yaml
providers:
  gemini:
    enabled: false                  # Enable when needed
    api_key: ${GOOGLE_API_KEY}      # Required
    model: gemini-1.5-pro-latest    # Options: gemini-1.5-pro, gemini-1.5-flash, gemini-1.0-pro
    max_tokens: 8192                # Up to 1M tokens with Gemini 1.5
    temperature: 0.1                # 0.0-2.0
```

**Environment Variable:**
```bash
export GOOGLE_API_KEY="AIza..."
```

#### Ollama (Local)

```yaml
providers:
  ollama:
    enabled: true
    base_url: http://localhost:11434  # Ollama server URL
    model: llama3.1:70b              # Must be pulled locally
    max_tokens: 4096
    temperature: 0.1
```

**Setup:**
```bash
# Install and run Ollama
ollama pull llama3.1:70b
ollama serve
```

### default_provider: ollama

Sets the primary LLM for extraction operations. Must match a key in the `providers` section.

### Extraction Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `chunk_size` | 2000 | Characters per text chunk for processing |
| `chunk_overlap` | 200 | Overlap between chunks to maintain context |

**Chunk Size Guidelines:**
- **1000-2000**: Good for standard entity extraction
- **2000-4000**: Better for complex relationships
- **Max model context / 2**: Never exceed half the model's context window

### Entity Types and Relation Types

Define the knowledge graph schema for extraction:

```yaml
schema:
  entity_types:
    - Person          # Individual people
    - Organization    # Companies, institutions
    - Location        # Cities, countries, addresses
    - Date            # Time references
    - Product         # Physical or digital products
    - Technology      # Technical systems, platforms
    - Concept         # Abstract ideas, theories
    - Event           # Conferences, meetings, incidents
    
  relation_types:
    - WORKS_FOR       # Person → Organization
    - LOCATED_IN      # Entity → Location
    - CREATED         # Person/Org → Entity
    - PART_OF         # Entity → Larger Entity
    - MENTIONS        # General reference
    - RELATED_TO      # Generic relationship
    - DEVELOPED_BY    # Product/Technology → Creator
```

### Environment Variable Substitution

All sensitive values support environment variables:

```yaml
providers:
  claude:
    api_key: ${ANTHROPIC_API_KEY}
  openai:
    api_key: ${OPENAI_API_KEY:-default_key}  # With default
```

**Loading .env:**
```python
from dotenv import load_dotenv
load_dotenv(".env")  # Must be called before config loading
```

### Switching Providers

Change `default_provider` to switch LLMs:

```yaml
# Use OpenAI
default_provider: openai

# Use local Ollama
default_provider: ollama

# Use Claude for complex extractions
default_provider: claude
```

**Runtime switching** (Python API):
```python
from src.config import Config

config = Config()
config.llm.default_provider = "claude"
```

---

## 4. neo4j.yaml

Configures Neo4j database connection, schema constraints, and connection pooling.

### Complete File Structure

```yaml
connection:
  uri: bolt://localhost:7687
  username: neo4j
  password: ${NEO4J_PASSWORD:-password}
  database: neo4j
  
  # Memory and performance settings
  max_connection_pool_size: 50
  connection_timeout: 30
  max_transaction_retry_time: 30

schema:
  # Constraints ensure uniqueness and data integrity
  constraints:
    - CREATE CONSTRAINT entity_id IF NOT EXISTS
      FOR (e:Entity) REQUIRE e.id IS UNIQUE
      
    - CREATE CONSTRAINT document_id IF NOT EXISTS
      FOR (d:Document) REQUIRE d.id IS UNIQUE
      
    - CREATE CONSTRAINT chunk_id IF NOT EXISTS
      FOR (c:Chunk) REQUIRE c.id IS UNIQUE
  
  # Indexes improve query performance
  indexes:
    - CREATE INDEX entity_type_index IF NOT EXISTS
      FOR (e:Entity) ON (e.type)
      
    - CREATE INDEX entity_name_index IF NOT EXISTS
      FOR (e:Entity) ON (e.name)
      
    - CREATE INDEX document_path_index IF NOT EXISTS
      FOR (d:Document) ON (d.file_path)
      
    - CREATE INDEX chunk_document_index IF NOT EXISTS
      FOR (c:Chunk) ON (c.document_id)

# Performance tuning
performance:
  batch_size: 1000
  unwind_batch_size: 100
```

### Connection Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `uri` | bolt://localhost:7687 | Neo4j Bolt protocol endpoint |
| `username` | neo4j | Database username |
| `password` | ${NEO4J_PASSWORD:-password} | Database password (use env var!) |
| `database` | neo4j | Target database name |
| `max_connection_pool_size` | 50 | Max concurrent connections |
| `connection_timeout` | 30 | Seconds to wait for connection |
| `max_transaction_retry_time` | 30 | Auto-retry failed transactions |

**URI Formats:**
```yaml
# Local single instance
uri: bolt://localhost:7687

# Remote server
uri: bolt://192.168.1.100:7687

# With encryption
uri: bolt+s://server.example.com:7687

# Neo4j Aura (cloud)
uri: neo4j+s://xxxx.databases.neo4j.io:7687
```

### Schema Section

#### Constraints

Constraints enforce data rules at the database level:

```yaml
constraints:
  # Entity uniqueness
  - CREATE CONSTRAINT entity_id IF NOT EXISTS
    FOR (e:Entity) REQUIRE e.id IS UNIQUE
    
  # Document uniqueness
  - CREATE CONSTRAINT document_id IF NOT EXISTS
    FOR (d:Document) REQUIRE d.id IS UNIQUE
    
  # Relationship uniqueness (optional)
  - CREATE CONSTRAINT relationship_unique IF NOT EXISTS
    FOR ()-[r:RELATES_TO]-() REQUIRE r.id IS UNIQUE
```

**Constraint Types:**
- `IS UNIQUE`: No duplicate values allowed
- `IS NOT NULL`: Value must be present
- `IS :: TYPE`: Data type enforcement (Neo4j 5+)

#### Indexes

Indexes speed up queries on frequently accessed properties:

```yaml
indexes:
  # Lookup by entity type
  - CREATE INDEX entity_type_index IF NOT EXISTS
    FOR (e:Entity) ON (e.type)
    
  # Text search on names
  - CREATE INDEX entity_name_index IF NOT EXISTS
    FOR (e:Entity) ON (e.name)
    
  # Document lookups
  - CREATE INDEX document_path_index IF NOT EXISTS
    FOR (d:Document) ON (d.file_path)
    
  # Full-text search (advanced)
  - CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
    FOR (e:Entity) ON EACH [e.name, e.description]
```

### Memory Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `max_connection_pool_size` | 50 | Prevent connection exhaustion |
| `connection_timeout` | 30 | Fail fast on network issues |
| `max_transaction_retry_time` | 30 | Handle concurrent write conflicts |

**Tuning for Scale:**
```yaml
# High-throughput configuration
connection:
  max_connection_pool_size: 200
  connection_timeout: 60
  max_transaction_retry_time: 60

performance:
  batch_size: 5000
  unwind_batch_size: 500
```

---

## 5. Environment Variables

Secure management of sensitive configuration values.

### .env File Format

Create a `.env` file in the project root:

```bash
# API Keys (Cloud Providers)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
GOOGLE_API_KEY=AIzaxxxxxxxxxxxxxxxx

# Database
NEO4J_PASSWORD=your-secure-password-here

# Optional: Custom endpoints
NEO4J_URI=bolt://localhost:7687
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Feature flags
DEBUG_MODE=false
LOG_LEVEL=INFO
```

**Format Rules:**
- One `KEY=value` pair per line
- No quotes needed (unless value contains spaces)
- Comments start with `#`
- No spaces around `=`

### Required vs Optional

| Variable | Required | File | Purpose |
|----------|----------|------|---------|
| `OPENAI_API_KEY` | If using OpenAI | llm.yaml | OpenAI API access |
| `ANTHROPIC_API_KEY` | If using Claude | llm.yaml | Anthropic API access |
| `GOOGLE_API_KEY` | If using Gemini | llm.yaml | Google AI API access |
| `NEO4J_PASSWORD` | Always | neo4j.yaml | Database authentication |
| `NEO4J_URI` | Optional | neo4j.yaml | Override connection URI |
| `OLLAMA_BASE_URL` | Optional | llm.yaml | Custom Ollama endpoint |

### Loading .env

The system automatically loads `.env` files, but you can control this:

**Automatic (Recommended):**
```python
# Config automatically loads .env on import
from src.config import Config
config = Config()  # .env already loaded
```

**Manual Control:**
```python
from dotenv import load_dotenv
from src.config import Config

# Load specific .env file
load_dotenv(".env.production")
config = Config()

# Or load multiple files
load_dotenv(".env.defaults")
load_dotenv(".env.local", override=True)
```

**Programmatic:**
```python
import os
os.environ["NEO4J_PASSWORD"] = "secret"
config = Config()  # Picks up environment variables
```

### Security Considerations

**DO:**
- Store `.env` files outside version control
- Use strong, unique passwords
- Rotate API keys regularly
- Use different keys for dev/prod
- Enable 2FA on provider accounts

**DON'T:**
- Commit `.env` files to git
- Share API keys in logs/messages
- Hardcode credentials in YAML
- Use default/weak passwords
- Expose `.env` files in deployments

**Git Protection:**
```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo ".env.*" >> .gitignore
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore
```

**Docker Secrets (Production):**
```yaml
# docker-compose.yml
secrets:
  neo4j_password:
    file: ./secrets/neo4j_password.txt
  openai_key:
    file: ./secrets/openai_key.txt
```

---

## 6. Configuration Loading

Understanding how configuration files are discovered and loaded.

### How Configs Are Loaded

The configuration system uses a hierarchical loading approach:

```
1. Built-in defaults (lowest priority)
2. Config files (config/*.yaml)
3. Environment variables
4. Explicit programmatic overrides (highest priority)
```

**Loading Order:**
```python
from src.config import Config

# 1. Initialize with defaults
config = Config()

# 2. Load YAML files
config.load_yaml("config/extraction.yaml")
config.load_yaml("config/llm.yaml")
config.load_yaml("config/neo4j.yaml")

# 3. Apply environment variables (automatic)
# Variables override YAML values

# 4. Apply programmatic overrides
config.neo4j.password = "new_password"
```

### Default Paths

The system searches for configs in this order:

1. **Current working directory:** `./config/`
2. **Project root:** Detected from git or file structure
3. **User config:** `~/.config/pdf-extraction/`
4. **System config:** `/etc/pdf-extraction/`

**Standard Layout:**
```
./config/extraction.yaml
./config/llm.yaml
./config/neo4j.yaml
```

### Custom Config Paths

Override default locations:

**Command Line:**
```bash
# Point to custom config directory
python -m src extract --config /path/to/configs/

# Or specific files
python -m src extract \
  --extraction-config /path/to/extraction.yaml \
  --llm-config /path/to/llm.yaml \
  --neo4j-config /path/to/neo4j.yaml
```

**Environment Variable:**
```bash
export CONFIG_PATH=/path/to/configs/
python -m src extract
```

**Python API:**
```python
from src.config import Config

# Custom directory
config = Config(config_dir="/custom/config/path")

# Individual files
config = Config(
    extraction_config="/path/to/extraction.yaml",
    llm_config="/path/to/llm.yaml",
    neo4j_config="/path/to/neo4j.yaml"
)
```

### Reloading Configs

Hot-reload configurations without restarting:

```python
from src.config import Config

config = Config()

# ... later, after file changes ...

# Reload specific file
config.reload("extraction")

# Reload all configs
config.reload_all()

# Auto-reload with file watcher
config.enable_auto_reload(interval=5)  # Check every 5 seconds
```

**CLI Reload:**
```bash
# Send signal to reload
kill -HUP <process_id>
```

---

## 7. Best Practices

Recommendations for maintaining secure and effective configurations.

### Use Environment Variables for Secrets

**Good:**
```yaml
# llm.yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}
```
```bash
# .env
OPENAI_API_KEY=sk-...
```

**Bad:**
```yaml
# llm.yaml
providers:
  openai:
    api_key: "sk-actual-key-here-never-do-this"
```

### Version Control for Non-Sensitive Configs

**Repository Structure:**
```
config/
├── extraction.yaml        # Commit this
├── llm.yaml              # Commit this
├── neo4j.yaml            # Commit this (with ${VARS})
└── README.md             # Explain setup
```

**Template Files:**
```
config/
├── extraction.yaml       # Production values
├── llm.yaml             
├── neo4j.yaml           
├── .env.example         # Template - commit this
└── .env                 # Real values - DO NOT COMMIT
```

`.env.example`:
```bash
# Copy to .env and fill in values
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
NEO4J_PASSWORD=change_me_in_production
```

### Different Configs for Dev/Prod

**Directory Structure:**
```
config/
├── default/              # Base configurations
│   ├── extraction.yaml
│   ├── llm.yaml
│   └── neo4j.yaml
├── development/          # Dev overrides
│   └── neo4j.yaml        # Local Neo4j
├── production/           # Production settings
│   ├── neo4j.yaml        # Remote Neo4j
│   └── extraction.yaml   # Higher DPI
└── testing/              # Test configs
    └── neo4j.yaml        # In-memory/test DB
```

**Loading by Environment:**
```bash
export ENV=production
python -m src extract  # Loads config/production/*.yaml
```

**Python:**
```python
import os
from src.config import Config

env = os.getenv("ENV", "development")
config = Config(env=env)
```

### Backup Configurations

**Version Control:**
```bash
# Commit config changes
git add config/
git commit -m "Update extraction settings for scanned docs"
```

**Backup Script:**
```bash
#!/bin/bash
# backup-configs.sh

BACKUP_DIR="/backup/configs/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"
cp -r config/ "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/"
echo "Backed up to $BACKUP_DIR"
```

**Before Major Changes:**
```bash
# Create snapshot
cp -r config/ config-backup-$(date +%Y%m%d)/

# Make changes
# ...

# Test
# ...

# Restore if needed
rm -rf config/
cp -r config-backup-*/ config/
```

---

## 8. Troubleshooting Config Issues

Common configuration problems and solutions.

### Invalid YAML Syntax

**Problem:** Config file won't load

**Symptoms:**
```
ERROR: Failed to load extraction.yaml
ParserError: while scanning for the next token
```

**Common Causes & Fixes:**

| Issue | Cause | Fix |
|-------|-------|-----|
| Indentation errors | Mixed tabs/spaces | Use 2 spaces only |
| Missing colon | `key value` instead of `key: value` | Add colon |
| Quote issues | Unescaped quotes in strings | Use single quotes or escape |
| List syntax | Wrong dash placement | `- item` with space after dash |

**Validation:**
```bash
# Install yamllint
pip install yamllint

# Check file
yamllint config/extraction.yaml

# Check all
yamllint config/
```

**Online Validator:**
Use https://yaml-online-parser.appspot.com/ for quick checks

### Missing Environment Variables

**Problem:** Variable not found error

**Symptoms:**
```
ERROR: Environment variable NEO4J_PASSWORD not set
```

**Diagnosis:**
```bash
# Check if loaded
env | grep NEO4J

# Check .env file
cat .env | grep NEO4J

# Test loading
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('NEO4J_PASSWORD'))"
```

**Solutions:**

1. **Set variable:**
```bash
export NEO4J_PASSWORD="your-password"
```

2. **Add to .env:**
```bash
echo "NEO4J_PASSWORD=your-password" >> .env
```

3. **Use default in YAML:**
```yaml
password: ${NEO4J_PASSWORD:-defaultpassword}
```

### Wrong Paths

**Problem:** Config files not found

**Symptoms:**
```
ERROR: Configuration file not found: config/extraction.yaml
```

**Diagnosis:**
```bash
# Check current directory
pwd

# List config directory
ls -la config/

# Find config files
find . -name "*.yaml" -type f
```

**Solutions:**

1. **Check working directory:**
```bash
cd /path/to/project
python -m src extract
```

2. **Specify full path:**
```bash
python -m src extract --config /absolute/path/to/config/
```

3. **Set environment variable:**
```bash
export CONFIG_PATH=/path/to/configs
python -m src extract
```

### Permission Issues

**Problem:** Cannot read/write config files

**Symptoms:**
```
ERROR: Permission denied: config/extraction.yaml
```

**Diagnosis:**
```bash
# Check permissions
ls -la config/

# Should show:
# -rw-r--r-- for files
# drwxr-xr-x for directories
```

**Solutions:**

1. **Fix file permissions:**
```bash
chmod 644 config/*.yaml
```

2. **Fix directory permissions:**
```bash
chmod 755 config/
```

3. **Fix ownership:**
```bash
sudo chown -R $USER:$USER config/
```

**Windows:**
```powershell
# Check permissions
Get-Acl config\extraction.yaml

# Fix (if needed)
icacls config\*.yaml /grant %username%:F
```

### Additional Debugging

**Enable Verbose Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check Config Loading:**
```python
from src.config import Config

config = Config()
print(config.to_dict())  # View complete config
```

**Test Database Connection:**
```bash
# Neo4j
neo4j status
neo4j log
```

**Test API Endpoints:**
```bash
# Ollama
curl http://localhost:11434/api/tags

# OpenAI
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

---

## Appendix: Complete Configuration Examples

### Minimal Development Setup

```yaml
# config/extraction.yaml
pdf_dpi: 150
native_threshold: 0.8
api_host: localhost:8080
model: llama3.1:latest
max_tokens: 2048
timeout: 300
parallel_workers: 2
```

```yaml
# config/llm.yaml
default_provider: ollama

providers:
  ollama:
    enabled: true
    base_url: http://localhost:11434
    model: llama3.1:latest
    max_tokens: 2048
    temperature: 0.1

extraction:
  chunk_size: 1000
  chunk_overlap: 100

schema:
  entity_types:
    - Person
    - Organization
    - Location
  relation_types:
    - WORKS_FOR
    - LOCATED_IN
```

```yaml
# config/neo4j.yaml
connection:
  uri: bolt://localhost:7687
  username: neo4j
  password: ${NEO4J_PASSWORD:-password}
  database: neo4j
  max_connection_pool_size: 10

schema:
  constraints: []
  indexes: []
```

### Production Setup

```yaml
# config/extraction.yaml
pdf_dpi: 300
native_threshold: 0.7
api_host: gpu-server.internal:8080
model: mlx-community/GLM-OCR-q4
max_tokens: 8192
timeout: 600
parallel_workers: 16

ocr:
  dpi: 300
  timeout: 600
```

```yaml
# config/llm.yaml
default_provider: claude

providers:
  claude:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-opus-20240229
    max_tokens: 4096
    temperature: 0.0
    
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    max_tokens: 4096
    temperature: 0.0

extraction:
  chunk_size: 4000
  chunk_overlap: 400

schema:
  entity_types:
    - Person
    - Organization
    - Location
    - Date
    - Product
    - Technology
    - Concept
    - Event
    - Industry
    - Market
  relation_types:
    - WORKS_FOR
    - LOCATED_IN
    - CREATED
    - PART_OF
    - MENTIONS
    - RELATED_TO
    - COMPETES_WITH
    - ACQUIRED
    - INVESTS_IN
```

```yaml
# config/neo4j.yaml
connection:
  uri: neo4j+s://prod-cluster.example.com:7687
  username: neo4j
  password: ${NEO4J_PASSWORD}
  database: knowledgegraph
  max_connection_pool_size: 200
  connection_timeout: 60

schema:
  constraints:
    - CREATE CONSTRAINT entity_id IF NOT EXISTS
      FOR (e:Entity) REQUIRE e.id IS UNIQUE
    - CREATE CONSTRAINT document_id IF NOT EXISTS
      FOR (d:Document) REQUIRE d.id IS UNIQUE
      
  indexes:
    - CREATE INDEX entity_type_index IF NOT EXISTS
      FOR (e:Entity) ON (e.type)
    - CREATE INDEX entity_name_index IF NOT EXISTS
      FOR (e:Entity) ON (e.name)
    - CREATE FULLTEXT INDEX search_index IF NOT EXISTS
      FOR (e:Entity) ON EACH [e.name, e.description]

performance:
  batch_size: 5000
  unwind_batch_size: 500
```

---

## Quick Reference Card

**Environment Variables:**
```bash
export OPENAI_API_KEY=""       # OpenAI access
export ANTHROPIC_API_KEY=""    # Claude access
export GOOGLE_API_KEY=""       # Gemini access
export NEO4J_PASSWORD=""       # Database auth
export CONFIG_PATH=""          # Custom config location
```

**Common Commands:**
```bash
# Validate YAML
yamllint config/

# Test config loading
python -c "from src.config import Config; c = Config(); print('OK')"

# Check .env
cat .env | grep -v "^#" | grep -v "^$"

# Backup configs
cp -r config/ config-backup-$(date +%Y%m%d)/
```

**Key Tuning Parameters:**
- **Speed:** Lower `pdf_dpi`, reduce `max_tokens`, increase `native_threshold`
- **Quality:** Increase `pdf_dpi`, use GPT-4/Claude, add more `entity_types`
- **Scale:** Increase `parallel_workers`, tune `batch_size`, use connection pooling

---

*Last Updated: March 2026*
