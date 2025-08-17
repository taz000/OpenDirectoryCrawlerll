# OpenDirectoryCrawler
**OpenList** is an advanced, intelligent directory listing crawler 

## ⚡ Key Features

### 🎯 **Multi-Server Intelligence**
- **Auto-detection** of Apache, Nginx, IIS, Python SimpleHTTPServer
- **Adaptive parsing** strategies for different directory listing formats
- **Fallback mechanisms** for unknown server types
- **Content validation** to ensure valid directory listings

### 🛡️ **Security & Compatibility**
- **SSL certificate bypass** for self-signed certificates
- **Custom User-Agent** support for stealth operations
- **Rate limiting** and respectful crawling
- **Robots.txt** compliance (with override option)

### 🚀 **Performance & Efficiency**
- **Multi-threaded downloading** with configurable worker count
- **Progress tracking** with real-time statistics
- **Resume capability** from interrupted downloads
- **Smart file filtering** by extension
- **Duplicate detection** and path conflict resolution

### 📊 **Advanced Features**
- **Real-time progress bars** showing discovery and download status
- **Comprehensive statistics** including speed, success rate, file types
- **JSON progress export** for analysis and resumption
- **Graceful shutdown** with signal handling
- **Directory structure probing** before crawling

## 🔧 Installation

### Prerequisites
```bash
# Install required system packages
sudo apt update
sudo apt install python3 python3-pip

# Or for other distributions
yum install python3 python3-pip  # RHEL/CentOS
brew install python3             # macOS
```

### Dependencies
```bash
# Install Python dependencies
pip3 install beautifulsoup4 requests tqdm urllib3

# Or install with requirements file
pip3 install -r requirements.txt
```

### Quick Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/openlist.git
cd openlist

# Make executable
chmod +x openlist.py

# Test installation
python3 openlist.py --help
```

## 📋 Usage

### Basic Usage
```bash
# Simple directory crawling
python3 openlist.py https://example.com/files/

# Crawl with SSL bypass (for self-signed certificates)
python3 openlist.py https://example.com/files/ --no-verify-ssl

# Custom output directory
python3 openlist.py https://example.com/files/ -o my_downloads
```

### Advanced Options
```bash
# High-performance crawling
python3 openlist.py https://example.com/files/ \
    --no-verify-ssl \
    -w 10 \
    --delay 0.2 \
    --timeout 60

# File type filtering
python3 openlist.py https://example.com/files/ \
    --extensions pdf,txt,doc,zip,sql \
    --no-verify-ssl

# Deep crawling with custom settings
python3 openlist.py https://example.com/files/ \
    --max-depth 5 \
    --ignore-robots \
    --user-agent "Custom Bot 1.0"
```

### Discovery-Only Mode
```bash
# Discover files without downloading (reconnaissance)
python3 openlist.py https://example.com/files/ \
    --dry-run \
    --no-verify-ssl
```

## 🎛️ Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | Target URL of directory listing | **Required** |
| `-o, --output` | Output directory for downloads | `downloads` |
| `-d, --max-depth` | Maximum recursion depth | `10` |
| `-w, --workers` | Number of download workers | `5` |
| `--delay` | Delay between requests (seconds) | `1.0` |
| `--timeout` | Request timeout (seconds) | `30` |
| `--no-verify-ssl` | Disable SSL certificate verification | `False` |
| `--user-agent` | Custom User-Agent string | Browser-like default |
| `--extensions` | Comma-separated file extensions to download | All files |
| `--ignore-robots` | Ignore robots.txt restrictions | `False` |
| `--dry-run` | Discovery only, no downloads | `False` |
| `--resume` | Resume from progress file | `None` |

## 📖 Examples

### 🔍 **Security Research Scenarios**

#### Web Application Assessment
```bash
# Discover configuration files and backups
python3 openlist.py https://target.com/backups/ \
    --extensions conf,sql,bak,old,txt \
    --no-verify-ssl
```

#### Source Code Analysis
```bash
# Download source code and documentation
python3 openlist.py https://target.com/src/ \
    --extensions php,js,py,rb,java,md \
    --max-depth 3
```

#### Log File Investigation
```bash
# Collect log files and reports
python3 openlist.py https://target.com/logs/ \
    --extensions log,txt,csv,json \
    --workers 3 \
    --delay 2.0
```

### 🌐 **Different Server Types**

#### Apache Servers
```bash
# Standard Apache mod_autoindex
python3 openlist.py http://apache-server.com/files/
```

#### Nginx Servers  
```bash
# Nginx autoindex module
python3 openlist.py https://nginx-server.com/downloads/ --no-verify-ssl
```

#### Python SimpleHTTPServer
```bash
# Development servers
python3 openlist.py http://dev-server.com:8000/
```

#### IIS Servers
```bash
# Microsoft IIS directory browsing
python3 openlist.py https://iis-server.com/files/ --timeout 60
```

## 📊 Output and Statistics

### Real-time Progress
```
Discovering files: ████████████████████ 45 files discovered [00:12]
Downloading files: ██████████░░░░░░░░░░ 67%|███████▌ | 30/45 files [01:23<00:38, 2.1files/s]
Speed: 1.2 MB/s | Queue: 15
```

### Final Statistics
```
======================================================================
📊 DOWNLOAD STATISTICS
======================================================================
🌐 Base URL: https://example.com/files/
📁 Output Directory: downloads
⏱️  Duration: 0:05:23
🔍 URLs Discovered: 156
📄 Total Files Found: 89
✅ Files Downloaded: 87
💾 Total Size Downloaded: 245.3 MB
⚡ Average Speed: 761.2 KB/s
❌ Errors: 2
📈 Success Rate: 97.8%
📏 Average File Size: 2.8 MB

📋 Top File Types:
   .pdf: 23 files
   .txt: 18 files
   .zip: 12 files
   .doc: 8 files
   .sql: 6 files
======================================================================
```

### Progress Export
The tool automatically saves progress to `download_progress.json`:
```json
{
  "base_url": "https://example.com/files/",
  "statistics": {
    "files_downloaded": 87,
    "bytes_downloaded": 257234567,
    "success_rate": 97.8
  },
  "downloaded_files": [...],
  "failed_downloads": [...]
}
```

## 🔒 Security Considerations

### ⚠️ **Legal and Ethical Use**
```
⚠️  WARNING: AUTHORIZED USE ONLY
This tool is designed for legitimate security research and testing.
Only use on systems you own or have explicit permission to test.
```

### 🛡️ **Defensive Measures**
- **Rate limiting**: Configurable delays between requests
- **Robots.txt compliance**: Respects crawling permissions by default  
- **User-Agent identification**: Uses realistic browser headers
- **Connection limits**: Prevents server overload
- **Graceful shutdown**: Handles interruptions cleanly

### 🔐 **SSL/TLS Handling**
```bash
# For development/testing environments with self-signed certificates
python3 openlist.py https://internal-server.com/ --no-verify-ssl
```

**Note**: Only disable SSL verification for trusted internal systems.

## 🏗️ Architecture

### Server Detection Logic
```python
def detect_server_type(response):
    """Intelligent server type detection"""
    # Analyze headers and content patterns
    # Support for Apache, Nginx, IIS, Python servers
    # Fallback to generic parsing strategies
```

### Parsing Strategies
1. **Server-specific parsers** for optimal accuracy
2. **Generic HTML parsing** with multiple strategies  
3. **Pattern-based extraction** for edge cases
4. **Fallback mechanisms** for unknown formats

### Threading Model
- **Discovery thread**: Crawls directory structure
- **Worker threads**: Download files concurrently  
- **Status thread**: Updates progress and statistics
- **Signal handlers**: Graceful shutdown management

## 🚨 Troubleshooting

### Common Issues

#### SSL Certificate Errors
```bash
# Problem: [SSL: CERTIFICATE_VERIFY_FAILED]
# Solution: Use --no-verify-ssl flag
python3 openlist.py https://target.com/ --no-verify-ssl
```

#### No Files Found
```bash
# Problem: "Found 0 files" message
# Solution: Check if target is actually a directory listing
python3 openlist.py https://target.com/ --dry-run --timeout 60
```

#### Path Too Long Errors
```bash
# Problem: File path conflicts or too long
# Solution: Use shorter output directory name
python3 openlist.py https://target.com/ -o dl
```

#### Rate Limiting/Blocking
```bash
# Problem: Server blocking requests
# Solution: Increase delays and reduce workers
python3 openlist.py https://target.com/ --delay 3.0 -w 2
```

### Debug Mode
```bash
# Enable verbose output for debugging
python3 openlist.py https://target.com/ --dry-run --timeout 10
```


### 📋 **Development Setup**
```bash
# Clone for development
git clone https://github.com/yourusername/openlist.git
cd openlist

# Install development dependencies
pip3 install -r requirements-dev.txt

# Run tests
python3 -m pytest tests/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚖️ Legal Disclaimer

This tool is intended for legitimate security research, penetration testing, and authorized assessments only. Users are responsible for ensuring they have proper authorization before using this tool against any target. The authors are not responsible for any misuse or damage caused by this tool.


## 📈 Changelog

### v2.0.0 (Latest)
- ✨ Multi-server intelligence (Apache, Nginx, IIS, Python)
- 🔒 SSL certificate bypass option
- 🚀 Enhanced performance with better threading
- 📊 Real-time progress tracking and statistics
- 🛡️ Improved error handling and recovery
- 🎯 Smart file type filtering
- 📱 Better command-line interface

### v1.0.0
- 🎉 Initial release
- 📁 Basic directory listing crawling
- 💾 Multi-threaded downloading
- 📋 Progress tracking
