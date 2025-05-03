#!/bin/bash

# 一键安装脚本 for NekoImageGallery

echo "=== NekoImageGallery 安装程序 ==="

# 检查Python版本
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if [[ "$PYTHON_VERSION" < "3.10" ]]; then
    echo "错误: 需要Python 3.10或更高版本"
    exit 1
fi
echo "✓ Python版本检查通过 ($PYTHON_VERSION)"

# 安装依赖
echo "安装Python依赖..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "错误: 依赖安装失败"
    exit 1
fi
echo "✓ Python依赖安装完成"

# 安装wd14-tagger
echo "设置wd14-tagger..."
pip install -e ./wd14-tagger-standalone
if [ $? -ne 0 ]; then
    echo "错误: wd14-tagger安装失败"
    exit 1
fi
echo "✓ wd14-tagger设置完成"

# 创建数据目录
mkdir -p data/qdrant
mkdir -p images/thumbnails

echo "=== 安装完成 ==="
echo "可以运行以下命令启动应用:"
echo "python3 -m uvicorn app.webapp:app --host 0.0.0.0 --port 8000"