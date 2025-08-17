#!/usr/bin/env python3
"""
OpenList - Recursive Directory Listing Downloader
A tool for downloading all files from open directory listings recursively.

WARNING: This tool is for authorized security research and testing only.
Only use on systems you own or have explicit permission to test.
"""

import os
import sys
import requests
import urllib.parse
import argparse
import time
import threading
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser
import hashlib
import json
from datetime import datetime
import queue
import signal
from tqdm import tqdm
import shutil
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
from html import unescape

class OpenListDownloader:
    def __init__(self, base_url, output_dir="downloads", max_depth=10, max_workers=5, delay=1, verify_ssl=True):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.max_workers = max_workers
        self.delay = delay
        self.verify_ssl = verify_ssl
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        
        # Handle SSL verification
        if not self.verify_ssl:
            # Disable SSL warnings when verification is disabled
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            print("[!] WARNING: SSL certificate verification disabled!")
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Add retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Add common headers to appear more like a browser
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Tracking
        self.visited_urls = set()
        self.downloaded_files = []
        self.failed_downloads = []
        self.total_size = 0
        
        # Threading
        self.download_queue = queue.Queue()
        self.workers_active = False
        self.lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'urls_discovered': 0,
            'files_downloaded': 0,
            'bytes_downloaded': 0,
            'errors': 0,
            'total_files_found': 0,
            'download_speed': 0
        }
        
        # Progress bars
        self.discovery_pbar = None
        self.download_pbar = None
        self.status_thread = None
        self.last_update_time = time.time()
        self.last_bytes_downloaded = 0
        
        # Set up signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        print(f"\n[!] Received signal {signum}. Shutting down gracefully...")
        self.workers_active = False
        self.save_progress()
        sys.exit(0)
        
    def check_robots_txt(self):
        """Check robots.txt for crawling permissions"""
        try:
            robots_url = urllib.parse.urljoin(self.base_url, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            # Use our session for robots.txt check
            try:
                robots_response = self.session.get(robots_url, timeout=10)
                if robots_response.status_code == 200:
                    # Parse robots.txt content
                    rp.set_url(robots_url)
                    rp.feed(robots_response.text)
                    
                    can_fetch = rp.can_fetch(self.session.headers['User-Agent'], self.base_url)
                    if not can_fetch:
                        print(f"[!] robots.txt disallows crawling {self.base_url}")
                        return False
            except:
                # If robots.txt fails, continue anyway
                pass
                
        except Exception as e:
            print(f"[*] Could not check robots.txt: {e}")
            
        return True
        
    def is_safe_path(self, path):
        """Check if path is safe to download"""
        # Avoid path traversal
        if '..' in path or (path.startswith('/') and not path.startswith(self.base_url)):
            return False
        
        # Check file extensions if filtering is enabled
        if hasattr(self, 'allowed_extensions') and self.allowed_extensions:
            file_ext = Path(path).suffix.lower().lstrip('.')
            if file_ext not in self.allowed_extensions:
                return False
            
        # Download all file types if no filtering
        return True
        
    def detect_server_type(self, response):
        """Detect server type from response headers and content"""
        server_header = response.headers.get('Server', '').lower()
        content = response.text.lower()
        
        server_types = []
        
        # Check server headers
        if 'apache' in server_header:
            server_types.append('apache')
        elif 'nginx' in server_header:
            server_types.append('nginx')
        elif 'iis' in server_header or 'microsoft' in server_header:
            server_types.append('iis')
        elif 'lighttpd' in server_header:
            server_types.append('lighttpd')
        elif 'python' in server_header:
            server_types.append('python')
        
        # Check content patterns
        if 'index of' in content and 'apache' in content:
            server_types.append('apache')
        elif 'directory listing for' in content:
            server_types.append('python')
        elif '<h1>index of' in content:
            server_types.append('nginx')
        elif 'autoindex' in content:
            server_types.append('nginx')
        elif '<title>[to parent directory]</title>' in content:
            server_types.append('iis')
        
        return list(set(server_types)) if server_types else ['unknown']
    
    def parse_apache_listing(self, url, soup):
        """Parse Apache-style directory listing"""
        items = []
        
        # Look for table rows or pre-formatted content
        rows = soup.find_all('tr')[1:] if soup.find('table') else []
        
        if not rows:
            # Try pre-formatted listing
            pre = soup.find('pre')
            if pre:
                lines = pre.get_text().split('\n')
                for line in lines:
                    # Match Apache format: icon name date size
                    match = re.search(r'<a href="([^"]+)">([^<]+)</a>', str(line))
                    if match:
                        href, name = match.groups()
                        if href not in ['../', '../', '/', './', '.']:
                            items.append(self._create_item(url, href, name.strip()))
        else:
            for row in rows:
                link = row.find('a')
                if link:
                    href = link.get('href')
                    name = link.get_text().strip()
                    if href and href not in ['../', '../', '/', './', '.']:
                        items.append(self._create_item(url, href, name))
        
        return items
    
    def parse_nginx_listing(self, url, soup):
        """Parse Nginx-style directory listing"""
        items = []
        
        # Nginx typically uses simple links in pre tags
        pre = soup.find('pre')
        if pre:
            links = pre.find_all('a')
            for link in links:
                href = link.get('href')
                name = link.get_text().strip()
                if href and href not in ['../', '../', '/', './', '.']:
                    items.append(self._create_item(url, href, name))
        
        # Also check for any links in the body
        if not items:
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                name = link.get_text().strip()
                if href and href not in ['../', '../', '/', './', '.'] and not href.startswith(('http', 'mailto')):
                    items.append(self._create_item(url, href, name))
        
        return items
    
    def parse_iis_listing(self, url, soup):
        """Parse IIS-style directory listing"""
        items = []
        
        # IIS often uses pre-formatted text
        pre = soup.find('pre')
        if pre:
            lines = pre.get_text().split('\n')
            for line in lines:
                # Look for directory/file patterns
                if ' <DIR> ' in line or re.search(r'\d{2}/\d{2}/\d{4}', line):
                    # Extract filename from the end of the line
                    parts = line.strip().split()
                    if parts and not parts[-1] in ['.', '..']:
                        filename = parts[-1]
                        is_dir = ' <DIR> ' in line
                        href = filename + ('/' if is_dir else '')
                        items.append(self._create_item(url, href, filename))
        
        return items
    
    def parse_python_listing(self, url, soup):
        """Parse Python SimpleHTTPServer-style directory listing"""
        items = []
        
        # Python server typically uses simple ul/li structure
        uls = soup.find_all('ul')
        for ul in uls:
            links = ul.find_all('a')
            for link in links:
                href = link.get('href')
                name = link.get_text().strip()
                if href and href not in ['../', '../', '/', './', '.']:
                    items.append(self._create_item(url, href, name))
        
        # Fallback to all links
        if not items:
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                name = link.get_text().strip()
                if href and href not in ['../', '../', '/', './', '.'] and not href.startswith(('http', 'mailto')):
                    items.append(self._create_item(url, href, name))
        
        return items
    
    def parse_generic_listing(self, url, soup):
        """Generic parser for unknown server types"""
        items = []
        
        # Try multiple strategies
        strategies = [
            # Strategy 1: Look for all links
            lambda: soup.find_all('a', href=True),
            # Strategy 2: Look for links in tables
            lambda: [link for table in soup.find_all('table') for link in table.find_all('a', href=True)],
            # Strategy 3: Look for links in pre tags
            lambda: [link for pre in soup.find_all('pre') for link in pre.find_all('a', href=True)],
            # Strategy 4: Look for links in lists
            lambda: [link for ul in soup.find_all(['ul', 'ol']) for link in ul.find_all('a', href=True)]
        ]
        
        for strategy in strategies:
            try:
                links = strategy()
                if links:
                    for link in links:
                        href = link.get('href')
                        name = link.get_text().strip()
                        if self._is_valid_href(href):
                            items.append(self._create_item(url, href, name))
                    if items:
                        break
            except:
                continue
        
        return items
    
    def _create_item(self, base_url, href, name):
        """Create standardized item dictionary"""
        # Handle encoded URLs
        href = unescape(href)
        
        # Build full URL
        full_url = urllib.parse.urljoin(base_url, href)
        
        # Determine if it's a directory
        is_directory = href.endswith('/') or (name.endswith('/') and not '.' in name.split('/')[-1])
        
        return {
            'url': full_url,
            'name': name.rstrip('/'),
            'is_directory': is_directory,
            'href': href
        }
    
    def _is_valid_href(self, href):
        """Check if href is valid for processing"""
        if not href:
            return False
        
        # Skip parent directory and self references
        if href in ['../', '../', '/', './', '.', '#']:
            return False
        
        # Skip external links and special protocols
        if href.startswith(('http://', 'https://', 'ftp://', 'mailto:', 'javascript:', 'tel:')):
            return False
        
        # Skip anchors and query parameters for directory detection
        if href.startswith('#'):
            return False
        
        return True
    
    def parse_directory_listing(self, url, content):
        """Intelligent directory listing parser that adapts to different server types"""
        soup = BeautifulSoup(content, 'html.parser')
        
        # Create a mock response object for server detection
        class MockResponse:
            def __init__(self, text, headers):
                self.text = text
                self.headers = headers
        
        # Get server type from the session's last response or create mock
        try:
            response = MockResponse(content.decode() if isinstance(content, bytes) else content, {})
        except:
            response = MockResponse(str(content), {})
        
        server_types = self.detect_server_type(response)
        
        print(f"[*] Detected server type(s): {', '.join(server_types)}")
        
        items = []
        
        # Try server-specific parsers first
        for server_type in server_types:
            if server_type == 'apache':
                items = self.parse_apache_listing(url, soup)
            elif server_type == 'nginx':
                items = self.parse_nginx_listing(url, soup)
            elif server_type == 'iis':
                items = self.parse_iis_listing(url, soup)
            elif server_type == 'python':
                items = self.parse_python_listing(url, soup)
            
            if items:
                break
        
        # Fallback to generic parser if server-specific parser didn't work
        if not items:
            items = self.parse_generic_listing(url, soup)
        
        # Additional cleanup and validation
        validated_items = []
        seen_urls = set()
        
        for item in items:
            # Skip duplicates
            if item['url'] in seen_urls:
                continue
            seen_urls.add(item['url'])
            
            # Skip if URL doesn't seem to be under the base URL (unless it's a valid relative path)
            if not item['url'].startswith(self.base_url) and item['href'].startswith(('http://', 'https://')):
                continue
            
            validated_items.append(item)
        
        return validated_items
        
    def get_file_info(self, url):
        """Get file information without downloading"""
        timeout = getattr(self, 'request_timeout', 30)
        try:
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                size = int(response.headers.get('content-length', 0))
                content_type = response.headers.get('content-type', 'unknown')
                last_modified = response.headers.get('last-modified', 'unknown')
                
                return {
                    'size': size,
                    'content_type': content_type,
                    'last_modified': last_modified
                }
        except Exception as e:
            # If HEAD fails, try GET with range header
            try:
                response = self.session.get(url, headers={'Range': 'bytes=0-0'}, timeout=timeout)
                if response.status_code in [206, 200]:  # Partial content or full content
                    size = int(response.headers.get('content-length', 0))
                    if response.status_code == 206:
                        # Extract total size from Content-Range header
                        content_range = response.headers.get('content-range', '')
                        if '/' in content_range:
                            size = int(content_range.split('/')[-1])
                    
                    return {
                        'size': size,
                        'content_type': response.headers.get('content-type', 'unknown'),
                        'last_modified': response.headers.get('last-modified', 'unknown')
                    }
            except:
                pass
            
        return None
        
    def download_file(self, url, local_path):
        """Download a single file with progress tracking"""
        timeout = getattr(self, 'request_timeout', 30)
        try:
            # Create directory if needed
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file already exists
            if local_path.exists():
                with self.lock:
                    self.stats['files_downloaded'] += 1
                    if self.download_pbar:
                        self.download_pbar.update(1)
                        self.download_pbar.set_description(f"Skipped: {local_path.name} (exists)")
                return True
                
            # Download file
            response = self.session.get(url, stream=True, timeout=timeout*2)  # Double timeout for downloads
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Update progress bar description
            if self.download_pbar:
                self.download_pbar.set_description(f"Downloading: {local_path.name}")
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
            # Update statistics
            with self.lock:
                self.stats['files_downloaded'] += 1
                self.stats['bytes_downloaded'] += downloaded
                self.downloaded_files.append({
                    'url': url,
                    'local_path': str(local_path),
                    'size': downloaded,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Update progress bar
                if self.download_pbar:
                    self.download_pbar.update(1)
                    self.download_pbar.set_description(f"Downloaded: {local_path.name} ({self.format_bytes(downloaded)})")
                    
            return True
            
        except Exception as e:
            with self.lock:
                self.stats['errors'] += 1
                self.failed_downloads.append({
                    'url': url,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                
                if self.download_pbar:
                    self.download_pbar.set_description(f"Failed: {local_path.name} - {str(e)[:50]}")
                    
            return False
            
    def format_bytes(self, bytes_size):
        """Format bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"
        
    def calculate_speed(self):
        """Calculate current download speed"""
        current_time = time.time()
        time_diff = current_time - self.last_update_time
        
        if time_diff >= 1.0:  # Update every second
            bytes_diff = self.stats['bytes_downloaded'] - self.last_bytes_downloaded
            self.stats['download_speed'] = bytes_diff / time_diff
            
            self.last_update_time = current_time
            self.last_bytes_downloaded = self.stats['bytes_downloaded']
            
    def init_progress_bars(self):
        """Initialize progress bars"""
        if not self.download_pbar and self.stats['total_files_found'] > 0:
            self.download_pbar = tqdm(
                total=self.stats['total_files_found'],
                desc="Downloading files",
                unit="files",
                position=1,
                leave=True,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} files [{elapsed}<{remaining}, {rate_fmt}]"
            )
            
    def update_status(self):
        """Update status display"""
        while self.workers_active:
            try:
                self.calculate_speed()
                
                # Get terminal width for dynamic display
                terminal_width = shutil.get_terminal_size().columns
                
                # Format status line
                speed_str = self.format_bytes(self.stats['download_speed']) + "/s"
                total_size_str = self.format_bytes(self.stats['bytes_downloaded'])
                
                status = (f"Files: {self.stats['files_downloaded']}/{self.stats['total_files_found']} | "
                         f"Size: {total_size_str} | Speed: {speed_str} | "
                         f"Errors: {self.stats['errors']} | "
                         f"Queue: {self.download_queue.qsize()}")
                
                # Truncate if too long
                if len(status) > terminal_width - 10:
                    status = status[:terminal_width - 13] + "..."
                    
                # Update progress bar postfix
                if self.download_pbar:
                    self.download_pbar.set_postfix_str(f"Speed: {speed_str} | Queue: {self.download_queue.qsize()}")
                    
                time.sleep(1)
                
            except Exception as e:
                break
                
    def crawl_directory(self, url, current_depth=0):
        """Recursively crawl directory listings"""
        if current_depth > self.max_depth:
            print(f"[!] Max depth reached for: {url}")
            return
            
        if url in self.visited_urls:
            return
            
        self.visited_urls.add(url)
        
        try:
            print(f"[*] Crawling: {url} (depth: {current_depth})")
            timeout = getattr(self, 'request_timeout', 30)
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            # Store response in session for server detection
            self._last_response = response
            
            # Parse directory listing
            items = self.parse_directory_listing(url, response.content)
            
            if not items:
                print(f"[!] No items found in directory listing: {url}")
                print(f"[!] Response status: {response.status_code}")
                print(f"[!] Content type: {response.headers.get('content-type', 'unknown')}")
                print(f"[!] Content length: {len(response.content)}")
                
                # Debug: Show a sample of the content
                content_sample = response.text[:500].replace('\n', '\\n')
                print(f"[!] Content sample: {content_sample}...")
                
                # Try alternative parsing approaches
                print(f"[*] Trying alternative parsing methods...")
                
                # Method 1: Look for any downloadable files by extension
                common_extensions = ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.tar', '.gz', '.mp3', '.mp4', '.avi', '.jpg', '.png', '.gif']
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if any(ext in href.lower() for ext in common_extensions):
                        if self._is_valid_href(href):
                            items.append(self._create_item(url, href, link.get_text().strip()))
                
                if items:
                    print(f"[+] Found {len(items)} downloadable files using extension detection")
                else:
                    print(f"[!] No downloadable content detected")
                    return
            
            # Count files for progress tracking
            file_count = sum(1 for item in items if not item['is_directory'])
            
            with self.lock:
                self.stats['urls_discovered'] += len(items)
                self.stats['total_files_found'] += file_count
                
                # Update discovery progress bar
                if self.discovery_pbar and file_count > 0:
                    if self.discovery_pbar.total is None or self.discovery_pbar.total == 0:
                        self.discovery_pbar.total = file_count
                    else:
                        self.discovery_pbar.total += file_count
                    self.discovery_pbar.update(file_count)
                    self.discovery_pbar.refresh()
            
            for item in items:
                if not self.workers_active:
                    break
                    
                # Rate limiting
                time.sleep(self.delay)
                
                if item['is_directory']:
                    # Recursively crawl subdirectories
                    self.crawl_directory(item['url'], current_depth + 1)
                else:
                    # Queue file for download (all file types)
                    if self.is_safe_path(item['href']):
                        # Additional validation for files
                        parsed_url = urllib.parse.urlparse(item['url'])
                        
                        # Skip if it looks like a script or dynamic page
                        if any(param in parsed_url.path.lower() for param in ['?', '&', '.php', '.asp', '.jsp', '.cgi']):
                            if not any(ext in parsed_url.path.lower() for ext in ['.pdf', '.doc', '.txt', '.zip']):
                                print(f"[!] Skipping potential dynamic content: {item['name']}")
                                continue
                        
                        self.download_queue.put(item)
                        # Initialize download progress bar if not exists
                        if not self.download_pbar:
                            self.init_progress_bars()
                        
        except Exception as e:
            print(f"[!] Error crawling {url}: {e}")
            with self.lock:
                self.stats['errors'] += 1
                
    def worker_thread(self):
        """Worker thread for downloading files"""
        while self.workers_active:
            try:
                item = self.download_queue.get(timeout=5)
                
                # Create local path
                parsed_url = urllib.parse.urlparse(item['url'])
                relative_path = parsed_url.path.lstrip('/')
                local_path = self.output_dir / relative_path
                
                # Download file
                self.download_file(item['url'], local_path)
                
                self.download_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[!] Worker error: {e}")
                
    def save_progress(self):
        """Save progress and statistics"""
        progress_file = self.output_dir / 'download_progress.json'
        
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        stats_copy['start_time'] = self.stats['start_time'].isoformat()
        stats_copy['end_time'] = datetime.now().isoformat()
        stats_copy['duration'] = str(datetime.now() - self.stats['start_time'])
        
        progress_data = {
            'base_url': self.base_url,
            'statistics': stats_copy,
            'downloaded_files': self.downloaded_files,
            'failed_downloads': self.failed_downloads,
            'visited_urls': list(self.visited_urls)
        }
        
        try:
            with open(progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
                
            print(f"[+] Progress saved to: {progress_file}")
        except Exception as e:
            print(f"[!] Error saving progress: {e}")
        
    def print_statistics(self):
        """Print enhanced download statistics"""
        duration = datetime.now() - self.stats['start_time']
        avg_speed = self.stats['bytes_downloaded'] / max(1, duration.total_seconds())
        
        print("\n" + "="*70)
        print("📊 DOWNLOAD STATISTICS")
        print("="*70)
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📁 Output Directory: {self.output_dir}")
        print(f"⏱️  Duration: {str(duration).split('.')[0]}")
        print(f"🔍 URLs Discovered: {self.stats['urls_discovered']:,}")
        print(f"📄 Total Files Found: {self.stats['total_files_found']:,}")
        print(f"✅ Files Downloaded: {self.stats['files_downloaded']:,}")
        print(f"💾 Total Size Downloaded: {self.format_bytes(self.stats['bytes_downloaded'])}")
        print(f"⚡ Average Speed: {self.format_bytes(avg_speed)}/s")
        print(f"❌ Errors: {self.stats['errors']:,}")
        print(f"📈 Success Rate: {(self.stats['files_downloaded'] / max(1, self.stats['total_files_found']) * 100):.1f}%")
        
        if self.stats['files_downloaded'] > 0:
            avg_file_size = self.stats['bytes_downloaded'] / self.stats['files_downloaded']
            print(f"📏 Average File Size: {self.format_bytes(avg_file_size)}")
            
        # Top file types
        if self.downloaded_files:
            extensions = {}
            for file_info in self.downloaded_files:
                path = Path(file_info['local_path'])
                ext = path.suffix.lower() or 'no extension'
                extensions[ext] = extensions.get(ext, 0) + 1
                
            print(f"\n📋 Top File Types:")
            for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"   {ext}: {count} files")
                
        print("="*70)
        
    def probe_directory_structure(self, url):
        """Probe the directory to understand its structure better"""
        timeout = getattr(self, 'request_timeout', 30)
        try:
            response = self.session.get(url, timeout=timeout)
            if response.status_code != 200:
                return False
            
            content_type = response.headers.get('content-type', '').lower()
            
            # Check if it's actually HTML content
            if 'html' not in content_type and 'text' not in content_type:
                print(f"[!] Warning: Content type '{content_type}' may not be a directory listing")
                return False
            
            # Check for common directory listing indicators
            content_lower = response.text.lower()
            directory_indicators = [
                'index of',
                'directory listing',
                'parent directory',
                '<pre>',
                'autoindex',
                'files in this folder',
                'folder listing'
            ]
            
            has_indicators = any(indicator in content_lower for indicator in directory_indicators)
            
            if not has_indicators:
                print(f"[!] Warning: URL may not be a directory listing")
                # Try to see if there are any links that look like files/directories
                soup = BeautifulSoup(response.content, 'html.parser')
                links = soup.find_all('a', href=True)
                valid_links = [link for link in links if self._is_valid_href(link.get('href'))]
                
                if len(valid_links) < 2:  # Need at least 2 links to be considered a directory
                    print(f"[!] Insufficient directory-like links found ({len(valid_links)})")
                    return False
            
            return True
            
        except Exception as e:
            print(f"[!] Error probing directory structure: {e}")
            return False
    
    def start_download(self):
        """Start the download process"""
        print(f"[+] Starting recursive download from: {self.base_url}")
        print(f"[+] Output directory: {self.output_dir}")
        print(f"[+] Max depth: {self.max_depth}")
        print(f"[+] Workers: {self.max_workers}")
        
        # First, probe the directory structure
        print(f"[*] Probing directory structure...")
        if not self.probe_directory_structure(self.base_url):
            print(f"[!] Warning: Target may not be a valid directory listing")
            print(f"[!] Continuing anyway... Use Ctrl+C to abort")
            time.sleep(3)
        
        # Check robots.txt
        if not getattr(self, 'ignore_robots', False):
            if not self.check_robots_txt():
                print("[!] Warning: robots.txt disallows crawling. Continue? (y/N)")
                if input().lower() != 'y':
                    return
        else:
            print("[!] Ignoring robots.txt restrictions")
                
        # Initialize discovery progress bar
        self.discovery_pbar = tqdm(
            total=0,
            desc="Discovering files",
            unit="files",
            position=0,
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt} files discovered [{elapsed}]"
        )
        
        # Start worker threads
        self.workers_active = True
        workers = []
        for i in range(self.max_workers):
            worker = threading.Thread(target=self.worker_thread, daemon=True)
            worker.start()
            workers.append(worker)
            
        # Start status update thread
        self.status_thread = threading.Thread(target=self.update_status, daemon=True)
        self.status_thread.start()
            
        try:
            # Start crawling
            self.crawl_directory(self.base_url)
            
            # Close discovery progress bar
            if self.discovery_pbar:
                self.discovery_pbar.close()
            
            # Wait for downloads to complete
            print(f"\n[*] Discovery complete! Found {self.stats['total_files_found']} files.")
            print("[*] Waiting for downloads to complete...")
            
            self.download_queue.join()
            
        finally:
            # Shutdown workers
            self.workers_active = False
            
            # Close progress bars
            if self.download_pbar:
                self.download_pbar.close()
                
            # Wait for workers to finish
            for worker in workers:
                worker.join(timeout=5)
                
            if self.status_thread:
                self.status_thread.join(timeout=2)
                
            # Save progress and print statistics
            self.save_progress()
            self.print_statistics()

def main():
    parser = argparse.ArgumentParser(
        description="OpenList - Recursive Directory Listing Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 openlist.py http://example.com/files/
  python3 openlist.py http://example.com/files/ -o downloads -d 5 -w 3
  python3 openlist.py http://example.com/files/ --delay 2 --max-depth 3
  python3 openlist.py https://example.com/files/ --no-verify-ssl
  python3 openlist.py http://example.com/files/ --extensions pdf,txt,zip
  python3 openlist.py http://example.com/files/ --ignore-robots --timeout 60

WARNING: This tool is for authorized security research only.
Only use on systems you own or have explicit permission to test.
        """
    )
    
    parser.add_argument('url', help='Base URL of directory listing')
    parser.add_argument('-o', '--output', default='downloads', 
                       help='Output directory (default: downloads)')
    parser.add_argument('-d', '--max-depth', type=int, default=10,
                       help='Maximum recursion depth (default: 10)')
    parser.add_argument('-w', '--workers', type=int, default=5,
                       help='Number of download workers (default: 5)')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--resume', help='Resume from progress file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Discovery only, no downloads')
    parser.add_argument('--no-verify-ssl', action='store_true',
                       help='Disable SSL certificate verification (use for self-signed certificates)')
    parser.add_argument('--user-agent', default=None,
                       help='Custom User-Agent string')
    parser.add_argument('--timeout', type=int, default=30,
                       help='Request timeout in seconds (default: 30)')
    parser.add_argument('--extensions', help='Comma-separated list of file extensions to download (e.g., pdf,txt,zip)')
    parser.add_argument('--ignore-robots', action='store_true',
                       help='Ignore robots.txt restrictions')
    
    args = parser.parse_args()
    
    # Validate URL
    if not args.url.startswith(('http://', 'https://')):
        print("[!] Error: URL must start with http:// or https://")
        sys.exit(1)
        
    # Warning message
    print("="*60)
    print("WARNING: AUTHORIZED USE ONLY")
    print("="*60)
    print("This tool downloads files from web directories recursively.")
    print("Only use on systems you own or have explicit permission to test.")
    print("Respect robots.txt and server resources.")
    print("="*60)
    print()
    
    try:
        # Create downloader instance
        downloader = OpenListDownloader(
            base_url=args.url,
            output_dir=args.output,
            max_depth=args.max_depth,
            max_workers=args.workers,
            delay=args.delay,
            verify_ssl=not args.no_verify_ssl
        )
        
        # Apply custom settings
        if args.user_agent:
            downloader.session.headers['User-Agent'] = args.user_agent
        
        if args.extensions:
            downloader.allowed_extensions = [ext.strip().lower() for ext in args.extensions.split(',')]
        
        downloader.request_timeout = args.timeout
        downloader.ignore_robots = args.ignore_robots
        
        # Start download
        downloader.start_download()
        
    except KeyboardInterrupt:
        print("\n[!] Download interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()