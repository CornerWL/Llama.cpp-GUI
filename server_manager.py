import subprocess
import threading
import socket
import time
import logging
import shlex
import os
import sys
from typing import Optional, Dict, Any, Callable
from pathlib import Path


def get_app_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


class ServerManager:
    """Manages the LlamaCPP server lifecycle with monitoring and error recovery."""
    
    def __init__(self, config_manager, status_callback: Optional[Callable] = None):
        self.config_manager = config_manager
        self.status_callback = status_callback
        self.server_process: Optional[subprocess.Popen] = None
        self._server_running = False
        self._log_thread: Optional[threading.Thread] = None
        self._health_check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Server state
        self.server_info = {
            "status": "stopped",
            "pid": None,
            "start_time": None,
            "health_check_count": 0,
            "last_health_check": None,
            "error_count": 0
        }
    
    def start_server(self) -> bool:
        """Start the LlamaCPP server with validation and monitoring."""
        if self._server_running:
            logging.warning("Server is already running")
            return False
        
        # Validate configuration
        validation_errors = self.config_manager.validate_config()
        if validation_errors:
            logging.error(f"Configuration validation failed: {validation_errors}")
            self._call_status_callback("error", f"Configuration error: {', '.join(validation_errors)}")
            return False
        
        # Check if model exists
        model_path = self.config_manager.get("model_path")
        if not model_path or not os.path.exists(model_path):
            error_msg = f"Model not found: {model_path}"
            logging.error(error_msg)
            self._call_status_callback("error", error_msg)
            return False
        
        # Check if port is available
        port = self.config_manager.get("server.port")
        host = self.config_manager.get("server.host")
        if not self._check_port_available(port, host):
            error_msg = f"Port {port} is already in use"
            logging.error(error_msg)
            self._call_status_callback("error", error_msg)
            return False
        
        try:
            # Build command
            cmd = self._build_server_command()
            logging.info(f"Starting server with command: {' '.join(cmd)}")
            
            # Start server
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            self._server_running = True
            self.server_info["status"] = "starting"
            self.server_info["pid"] = self.server_process.pid
            self.server_info["start_time"] = time.time()
            self.server_info["error_count"] = 0
            
            # Start monitoring threads
            self._start_monitoring()
            
            # Wait for server to start
            if self._wait_for_server_start():
                self.server_info["status"] = "running"
                self._call_status_callback("success", "Server started successfully")
                logging.info("Server started successfully")
                return True
            else:
                self._call_status_callback("error", "Server failed to start")
                self.stop_server()
                return False
                
        except Exception as e:
            error_msg = f"Failed to start server: {e}"
            logging.error(error_msg)
            self._call_status_callback("error", error_msg)
            self.stop_server()
            return False
    
    def stop_server(self):
        """Stop the server gracefully with timeout."""
        if not self._server_running:
            return
        
        self._server_running = False
        self.server_info["status"] = "stopping"
        self._call_status_callback("info", "Stopping server...")
        
        # Stop monitoring threads
        self._stop_monitoring()
        
        if self.server_process:
            try:
                # Try graceful shutdown first
                self.server_process.terminate()
                
                # Wait for process to exit
                try:
                    self.server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown failed
                    logging.warning("Graceful shutdown failed, force killing server")
                    self.server_process.kill()
                    self.server_process.wait()
                
                self.server_process = None
                self.server_info["status"] = "stopped"
                self.server_info["pid"] = None
                self._call_status_callback("info", "Server stopped")
                logging.info("Server stopped")
                
            except Exception as e:
                logging.error(f"Error stopping server: {e}")
                self._call_status_callback("error", f"Error stopping server: {e}")
    
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._server_running and self.server_process and self.server_process.poll() is None
    
    def get_server_info(self) -> Dict[str, Any]:
        """Get current server information."""
        return self.server_info.copy()
    
    def _build_server_command(self) -> list:
        """Build the server command with all parameters."""
        # Get llama-server path
        llama_path = self._get_llama_server_path()
        if not os.path.exists(llama_path):
            raise FileNotFoundError(f"llama-server.exe not found at {llama_path}")
        
        # Basic command
        cmd = [llama_path]
        
        # Model path
        model_path = self.config_manager.get("model_path")
        cmd.extend(["-m", model_path])
        
        # Server settings
        server_config = self.config_manager.get("server", {})
        cmd.extend([
            "--ctx-size", str(server_config["ctx"]),
            "--threads", str(server_config["threads"]),
            "--n-gpu-layers", str(server_config["gpu_layers"]),
            "--host", server_config["host"],
            "--port", str(server_config["port"]),
            "--batch-size", str(server_config["batch_size"]),
            "-n", str(server_config["n_predict"])
        ])
        
        # Generation settings
        gen_config = self.config_manager.get("generation", {})
        
        # Chat template
        if gen_config.get("chat_template") and gen_config["chat_template"] != "auto":
            cmd.extend(["--chat-template", gen_config["chat_template"]])
        
        # Flash attention
        if gen_config.get("flash_attention") and gen_config["flash_attention"] != "auto":
            cmd.extend(["--flash-attn", gen_config["flash_attention"]])
        
        # Extra command line args
        extra_args = server_config.get("extra_args", "").strip()
        if extra_args:
            try:
                extra_parts = shlex.split(extra_args)
                cmd.extend(extra_parts)
            except Exception as e:
                logging.warning(f"Error parsing extra args: {e}")
        
        return cmd
    
    def _get_llama_server_path(self) -> str:
        """Get the path to llama-server executable."""
        # Try different possible locations
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "bin", "llama-server.exe"),
            os.path.join(os.path.abspath("."), "bin", "llama-server.exe"),
            "llama-server.exe"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        base_path = get_app_path()
        llama_path = os.path.join(base_path, "bin", "llama-server.exe")
        if os.path.exists(llama_path):
            return llama_path

        raise FileNotFoundError("Could not find llama-server.exe")
    
    def _check_port_available(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if the specified port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result != 0
        except Exception:
            return False
    
    def _wait_for_server_start(self, timeout: int = 30) -> bool:
        """Wait for server to start and become responsive."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self.is_running():
                logging.error("Server process exited during startup")
                return False
            
            # Try to connect to server
            if self._test_server_connection():
                return True
            
            time.sleep(0.5)
        
        logging.error("Server failed to start within timeout")
        return False
    
    def _test_server_connection(self) -> bool:
        """Test if server is responsive."""
        try:
            import requests
            host = self.config_manager.get("server.host")
            port = self.config_manager.get("server.port")
            url = f"http://{host}:{port}/health"
            
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _start_monitoring(self):
        """Start monitoring threads for log reading and health checks."""
        self._stop_event.clear()
        
        # Start log reader
        self._log_thread = threading.Thread(target=self._read_log, daemon=True)
        self._log_thread.start()
        
        # Start health checker
        self._health_check_thread = threading.Thread(target=self._health_check, daemon=True)
        self._health_check_thread.start()
    
    def _stop_monitoring(self):
        """Stop monitoring threads."""
        self._stop_event.set()
        
        if self._log_thread:
            self._log_thread.join(timeout=2)
        
        if self._health_check_thread:
            self._health_check_thread.join(timeout=2)
    
    def _read_log(self):
        """Read and process server logs."""
        if not self.server_process or not self.server_process.stdout:
            return
        
        try:
            for line in iter(self.server_process.stdout.readline, b''):
                if self._stop_event.is_set():
                    break
                
                if line:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        self._call_status_callback("log", decoded)
                        
                        # Check for error patterns
                        if any(error_word in decoded.lower() for error_word in ["error", "failed", "exception"]):
                            self.server_info["error_count"] += 1
                            
                            # Auto-restart on critical errors (optional)
                            if self.server_info["error_count"] > 5:
                                logging.warning("Too many errors, consider restarting server")
        
        except Exception as e:
            logging.error(f"Error reading server log: {e}")
    
    def _health_check(self):
        """Periodically check server health."""
        while not self._stop_event.is_set():
            try:
                if self.is_running():
                    if self._test_server_connection():
                        self.server_info["health_check_count"] += 1
                        self.server_info["last_health_check"] = time.time()
                    else:
                        self.server_info["error_count"] += 1
                        logging.warning("Server health check failed")
                else:
                    logging.warning("Server process is not running")
                    self._server_running = False
                    self.server_info["status"] = "crashed"
                    self._call_status_callback("error", "Server crashed")
                    break
                
            except Exception as e:
                logging.error(f"Health check error: {e}")
                self.server_info["error_count"] += 1
            
            self._stop_event.wait(5)  # Check every 5 seconds
    
    def _call_status_callback(self, status_type: str, message: str):
        """Call the status callback if available."""
        if self.status_callback:
            try:
                self.status_callback(status_type, message)
            except Exception as e:
                logging.error(f"Status callback error: {e}")