#!/bin/bash

# OpenList Installation Script
# Automated setup for OpenList Directory Crawler

set -e

echo "🚀 OpenList Installation Script"
echo "================================"

# Check Python version
echo "📋 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python $PYTHON_VERSION found"

# Install dependencies
echo "📦 Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt --user
    echo "✅ Dependencies installed successfully"
else
    echo "⚠️  pip3 not found. Please install dependencies manually:"
    echo "   pip3 install -r requirements.txt"
fi

# Make script executable
echo "🔧 Making openlist.py executable..."
chmod +x openlist.py

# Test installation
echo "🧪 Testing installation..."
if python3 openlist.py --help > /dev/null 2>&1; then
    echo "✅ Installation successful!"
    echo ""
    echo "🎉 OpenList is ready to use!"
    echo ""
    echo "📖 Quick Start:"
    echo "   ./openlist.py https://example.com/files/ --no-verify-ssl"
    echo ""
    echo "📚 Full documentation: https://github.com/yourusername/openlist"
else
    echo "❌ Installation test failed. Please check dependencies."
    exit 1
fi