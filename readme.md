# NekoImageGallery

[![GitHub Workflow Status (with event)](https://img.shields.io/github/actions/workflow/status/hv0905/NekoImageGallery/prod.yml?logo=github)](https://github.com/hv0905/NekoImageGallery/actions)
[![codecov](https://codecov.io/gh/hv0905/NekoImageGallery/branch/master/graph/badge.svg?token=JK2KZBDIYP)](https://codecov.io/gh/hv0905/NekoImageGallery)
[![Maintainability](https://api.codeclimate.com/v1/badges/ac97a1146648996b68ea/maintainability)](https://codeclimate.com/github/hv0905/NekoImageGallery/maintainability)
![Man hours](https://img.shields.io/endpoint?url=https%3A%2F%2Fmanhours.aiursoft.cn%2Fr%2Fgithub.com%2Fhv0905%2FNekoImageGallery.json)
[![Docker Pulls](https://img.shields.io/docker/pulls/edgeneko/neko-image-gallery)](https://hub.docker.com/r/edgeneko/neko-image-gallery)

An online AI image search engine based on the Clip model and Qdrant vector database. Supports keyword search and similar image search.

[中文文档](readme_cn.md)

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip package manager
- Git

### One-Click Installation
We provide an installation script to simplify the setup process:

```bash
# Download the project
git clone https://github.com/hv0905/NekoImageGallery.git
cd NekoImageGallery

# Make the install script executable
chmod +x install.sh

# Run the installation
./install.sh
```

After installation, start the application:
```bash
python3 -m uvicorn app.webapp:app --host 0.0.0.0 --port 8000
```

## ✨ Features

[原有Features部分保持不变...]

## 🖥️ Local Deployment

### Manual Installation

1. **Set up Python virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/MacOS
   # OR
   .\venv\Scripts\activate  # Windows
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -e ./wd14-tagger-standalone
   ```

3. **Initialize directories:**
   ```bash
   mkdir -p data/qdrant
   mkdir -p images/thumbnails
   ```

4. **Configuration:**
   - Copy `config/default.env` to `config/local.env`
   - Modify settings in `local.env` as needed

5. **Run the application:**
   ```bash
   python3 -m uvicorn app.webapp:app --host 0.0.0.0 --port 8000
   ```

[原有Deployment部分其他内容保持不变...]

## 💡 Usage Guide

### First Run
1. After starting the server, open `http://localhost:8000` in your browser
2. Use the web interface to upload and search images
3. For API usage, visit `http://localhost:8000/docs` for Swagger documentation

### Managing Images
- To index local images:
  ```bash
  python main.py local-index /path/to/your/images
  ```
- Use `--categories` to add tags:
  ```bash
  python main.py local-index /path/to/images --categories "nature,landscape"
  ```

[原有其他部分保持不变...]
