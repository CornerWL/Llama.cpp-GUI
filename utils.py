import os
import sys
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import shlex


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Setup logging configuration."""
    # Create logs directory
    log_dir = os.path.join(os.path.expanduser("~"), ".llamagui", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Setup file handler if log_file specified
    if log_file:
        log_path = os.path.join(log_dir, log_file)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.root.addHandler(file_handler)
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.root.addHandler(console_handler)
    
    # Set level
    logging.basicConfig(level=getattr(logging, log_level.upper()))


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid characters."""
    # Remove invalid characters for Windows/Linux/Mac
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '', filename)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "untitled"
    
    return sanitized


def validate_model_path(model_path: str) -> tuple[bool, str]:
    """Validate model file path and return (is_valid, error_message)."""
    if not model_path:
        return False, "Model path is empty"
    
    if not os.path.exists(model_path):
        return False, f"Model file does not exist: {model_path}"
    
    if not os.path.isfile(model_path):
        return False, f"Path is not a file: {model_path}"
    
    if not model_path.lower().endswith('.gguf'):
        return False, f"File is not a GGUF model: {model_path}"
    
    # Check file size (minimum 1MB)
    try:
        file_size = os.path.getsize(model_path)
        if file_size < 1024 * 1024:  # 1MB
            return False, f"Model file is too small ({file_size} bytes)"
    except OSError as e:
        return False, f"Cannot access model file: {e}"
    
    return True, "Valid"


def get_file_size_info(file_path: str) -> Dict[str, Union[int, str]]:
    """Get human-readable file size information."""
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_mb / 1024
        
        if size_gb >= 1:
            size_str = f"{size_gb:.2f} GB"
        elif size_mb >= 1:
            size_str = f"{size_mb:.2f} MB"
        else:
            size_str = f"{size_bytes:,} bytes"
        
        return {
            "bytes": size_bytes,
            "mb": round(size_mb, 2),
            "gb": round(size_gb, 2),
            "human_readable": size_str
        }
    except OSError:
        return {
            "bytes": 0,
            "mb": 0,
            "gb": 0,
            "human_readable": "Unknown"
        }


def validate_port(port: Union[str, int]) -> tuple[bool, str]:
    """Validate port number."""
    try:
        port_num = int(port)
        if 1 <= port_num <= 65535:
            return True, "Valid"
        else:
            return False, "Port must be between 1 and 65535"
    except (ValueError, TypeError):
        return False, "Port must be a valid number"


def validate_host(host: str) -> tuple[bool, str]:
    """Validate host address."""
    if not host:
        return False, "Host cannot be empty"
    
    # Basic validation - allow localhost, IP addresses, and domain names
    if host.lower() in ['localhost', '127.0.0.1', '::1']:
        return True, "Valid"
    
    # Check for valid IP address format
    import ipaddress
    try:
        ipaddress.ip_address(host)
        return True, "Valid"
    except ValueError:
        pass
    
    # Check for valid domain name format
    if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', host):
        return True, "Valid"
    
    return False, "Invalid host format"


def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available."""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0
    except Exception:
        return False


def get_system_info() -> Dict[str, Any]:
    """Get basic system information."""
    import platform
    import shutil
    
    try:
        # Try to import psutil
        import psutil
        has_psutil = True
    except ImportError:
        has_psutil = False
        logging.warning("psutil not available, using basic system info only")
    
    try:
        if has_psutil:
            # CPU info
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memory info
            memory = psutil.virtual_memory()
            
            # Disk info
            disk = psutil.disk_usage('/')
            
            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "cpu": {
                    "count": cpu_count,
                    "frequency": cpu_freq.current if cpu_freq else 0,
                    "usage": cpu_usage
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "percent": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": round((disk.used / disk.total) * 100, 2)
                }
            }
        else:
            # Fallback without psutil (best-effort real values)
            cpu_count = os.cpu_count()

            # Memory fallback (Windows + generic fallback)
            memory_info = {
                "total_gb": None,
                "available_gb": None,
                "percent": None
            }

            try:
                if sys.platform == "win32":
                    import ctypes

                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [
                            ("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                        ]

                    mem_status = MEMORYSTATUSEX()
                    mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status)):
                        total = mem_status.ullTotalPhys
                        avail = mem_status.ullAvailPhys
                        used_pct = (1 - (avail / total)) * 100 if total else None
                        memory_info = {
                            "total_gb": round(total / (1024**3), 2),
                            "available_gb": round(avail / (1024**3), 2),
                            "percent": round(used_pct, 2) if used_pct is not None else None
                        }
            except Exception as e:
                logging.debug(f"Memory fallback info unavailable: {e}")

            # Disk fallback
            disk_info = {
                "total_gb": None,
                "free_gb": None,
                "percent": None
            }
            try:
                root_path = os.path.abspath(os.sep)
                total, used, free = shutil.disk_usage(root_path)
                disk_info = {
                    "total_gb": round(total / (1024**3), 2),
                    "free_gb": round(free / (1024**3), 2),
                    "percent": round((used / total) * 100, 2) if total else None
                }
            except Exception as e:
                logging.debug(f"Disk fallback info unavailable: {e}")

            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "cpu": {
                    "count": cpu_count,
                    "frequency": None,
                    "usage": None
                },
                "memory": memory_info,
                "disk": disk_info,
                "note": "psutil not available - detailed system info not available"
            }
    except Exception as e:
        logging.warning(f"Could not get system info: {e}")
        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "error": str(e)
        }


def safe_execute_command(cmd: Union[str, List[str]], timeout: int = 30) -> tuple[bool, str, str]:
    """Safely execute a command and return (success, stdout, stderr)."""
    try:
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        return True, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        return False, "", str(e)


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    elif seconds < 60:
        return f"{seconds:.1f} s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{int(minutes)}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"


def create_backup(file_path: str, backup_dir: Optional[str] = None) -> Optional[str]:
    """Create a backup of the specified file."""
    if not os.path.exists(file_path):
        return None
    
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(file_path), "backups")
    
    os.makedirs(backup_dir, exist_ok=True)
    
    # Create backup filename with timestamp
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(file_path)
    name, ext = os.path.splitext(basename)
    backup_name = f"{name}_backup_{timestamp}{ext}"
    backup_path = os.path.join(backup_dir, backup_name)
    
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception as e:
        logging.error(f"Failed to create backup: {e}")
        return None


def get_llama_server_version() -> Optional[str]:
    """Get the version of llama-server if available."""
    try:
        # Try to find llama-server
        llama_path = None
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "bin", "llama-server.exe"),
            os.path.join(os.path.abspath("."), "bin", "llama-server.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                llama_path = path
                break
        
        if not llama_path:
            return None
        
        # Try to get version
        success, stdout, stderr = safe_execute_command([llama_path, "--version"], timeout=5)
        if success and stdout:
            # Parse version from output
            version_match = re.search(r'(\d+\.\d+\.\d+)', stdout)
            if version_match:
                return version_match.group(1)
        
        return None
        
    except Exception:
        return None


def validate_extra_args(args_string: str) -> tuple[bool, str, List[str]]:
    """Validate extra command line arguments."""
    if not args_string.strip():
        return True, "No extra arguments", []
    
    try:
        args = shlex.split(args_string)
        
        # Basic validation - check for dangerous commands
        dangerous_patterns = [
            r'rm\s+',
            r'del\s+',
            r'format\s+',
            r'format\s+',
            r'fdisk',
            r'format',
            r'format',
        ]
        
        for arg in args:
            for pattern in dangerous_patterns:
                if re.search(pattern, arg, re.IGNORECASE):
                    return False, f"Dangerous command detected: {arg}", []
        
        return True, "Valid arguments", args
    
    except Exception as e:
        return False, f"Invalid argument format: {e}", []


def get_gpu_info() -> Dict[str, Any]:
    """Get GPU information if available."""
    try:
        # Try to get GPU info using nvidia-smi
        success, stdout, stderr = safe_execute_command(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], timeout=10)
        
        if success and stdout:
            gpus = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(', ')
                    if len(parts) >= 4:
                        gpus.append({
                            "name": parts[0],
                            "memory_total": f"{parts[1]} MB",
                            "memory_free": f"{parts[2]} MB",
                            "utilization": f"{parts[3]}%"
                        })
            
            return {
                "available": True,
                "count": len(gpus),
                "gpus": gpus
            }
        
        # Try to get AMD GPU info
        success, stdout, stderr = safe_execute_command(["rocminfo"], timeout=10)
        if success:
            return {
                "available": True,
                "type": "AMD",
                "info": "AMD GPU detected"
            }
        
        return {
            "available": False,
            "reason": "No compatible GPU found or drivers not installed"
        }
        
    except Exception as e:
        return {
            "available": False,
            "error": str(e)
        }


def sanitize_model_name(model_path: str) -> str:
    """Extract and sanitize model name from path."""
    if not model_path:
        return "Unknown Model"
    
    basename = os.path.basename(model_path)
    name, ext = os.path.splitext(basename)
    
    # Remove common suffixes and prefixes
    name = re.sub(r'(_v\d+|_q[0-9]+|_f16|_f32|_gguf)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^(ggml_|model_)', '', name, flags=re.IGNORECASE)
    
    # Clean up extra underscores and spaces
    name = re.sub(r'_+', ' ', name)
    name = name.strip()
    
    return name.title() if name else "Unknown Model"


def format_model_info(model_path: str) -> Dict[str, str]:
    """Format model information for display."""
    if not model_path or not os.path.exists(model_path):
        return {
            "name": "No Model Selected",
            "size": "Unknown",
            "path": "N/A"
        }
    
    size_info = get_file_size_info(model_path)
    model_name = sanitize_model_name(model_path)
    
    return {
        "name": model_name,
        "size": size_info["human_readable"],
        "path": model_path
    }