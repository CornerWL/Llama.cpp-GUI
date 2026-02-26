import customtkinter as ctk
import subprocess
import threading
import requests
import os
import sys
import json
import socket
import shlex
import time
import logging
from tkinter import filedialog
from typing import Optional

# Import our new modules
from config_manager import ConfigManager
from server_manager import ServerManager
from utils import setup_logging, validate_model_path, validate_port, validate_host, format_model_info, get_system_info, get_gpu_info


def get_app_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_config_path():
    config_dir = os.path.join(os.path.expanduser("~"), ".llamagui")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.json")


class LlamaGUI(ctk.CTk):

    def __init__(self):
        super().__init__()

        # Setup logging first
        setup_logging("INFO", "llamagui.log")
        self.logger = logging.getLogger(__name__)
        
        self.title("LlamaCPP Control")
        self.geometry("1000x720")
        self.minsize(800, 600)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initialize managers
        self.config_manager = ConfigManager()
        self.server_manager = ServerManager(self.config_manager, self._on_server_status_change)
        
        # Initialize server process attribute
        self.server_process = None
        
        # UI state
        self.stop_generation = False
        self._generating = False
        self.log_lines = 0
        self.max_log_lines = self.config_manager.get("ui.max_log_lines", 1000)

        # Initialize UI
        self._init_ui()
        self._load_initial_state()
    
    def _init_ui(self):
        """Initialize the main UI components."""
        # ===== TOP BAR =====
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", pady=5)

        # Status indicators
        status_frame = ctk.CTkFrame(top_frame)
        status_frame.pack(side="left", padx=10, fill="x", expand=True)
        
        self.status_label = ctk.CTkLabel(status_frame, text="Server: Stopped", font=("", 12, "bold"))
        self.status_label.pack(side="left")
        
        self.model_info_label = ctk.CTkLabel(status_frame, text="", font=("", 10))
        self.model_info_label.pack(side="left", padx=(10, 0))
        
        # Server controls
        control_frame = ctk.CTkFrame(top_frame)
        control_frame.pack(side="right", padx=10)
        
        self.start_button = ctk.CTkButton(
            control_frame,
            text="Start Server",
            command=self.toggle_server,
            width=120
        )
        self.start_button.pack(side="left", padx=5)
        
        self.stop_button = ctk.CTkButton(
            control_frame,
            text="Stop Server",
            command=self.stop_server,
            width=120,
            state="disabled"
        )
        self.stop_button.pack(side="left", padx=5)
        
        # ===== TABS =====
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(expand=True, fill="both", padx=10, pady=10)

        self.chat_tab = self.tabs.add("Chat")
        self.log_tab = self.tabs.add("Log")
        self.settings_tab = self.tabs.add("Settings")
        self.system_tab = self.tabs.add("System")

        self.build_chat_tab()
        self.build_log_tab()
        self.build_settings_tab()
        self.build_system_tab()

        # Keep system info up-to-date when System tab is active
        self.after(3000, self._periodic_system_refresh)
    
    def build_system_tab(self):
        """Build the system information tab."""
        scroll_frame = ctk.CTkScrollableFrame(self.system_tab, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # System info section
        system_frame = ctk.CTkFrame(scroll_frame)
        system_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(system_frame, text="System Information", font=("", 14, "bold")).pack(pady=5)
        
        self.system_info_text = ctk.CTkTextbox(system_frame, height=200)
        self.system_info_text.pack(fill="x", padx=10, pady=5)
        
        refresh_btn = ctk.CTkButton(system_frame, text="Refresh", command=self._refresh_system_info)
        refresh_btn.pack(pady=5)
        
        # GPU info section
        gpu_frame = ctk.CTkFrame(scroll_frame)
        gpu_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(gpu_frame, text="GPU Information", font=("", 14, "bold")).pack(pady=5)
        
        self.gpu_info_text = ctk.CTkTextbox(gpu_frame, height=150)
        self.gpu_info_text.pack(fill="x", padx=10, pady=5)
        
        # Recent models section
        recent_frame = ctk.CTkFrame(scroll_frame)
        recent_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(recent_frame, text="Recent Models", font=("", 14, "bold")).pack(pady=5)
        
        self.recent_models_list = ctk.CTkTextbox(recent_frame, height=100)
        self.recent_models_list.pack(fill="x", padx=10, pady=5)
        
        # Presets section
        presets_frame = ctk.CTkFrame(scroll_frame)
        presets_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(presets_frame, text="Presets", font=("", 14, "bold")).pack(pady=5)
        
        presets_controls = ctk.CTkFrame(presets_frame)
        presets_controls.pack(fill="x", padx=10, pady=5)
        
        self.preset_name_entry = ctk.CTkEntry(presets_controls, placeholder_text="Preset name")
        self.preset_name_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        ctk.CTkButton(presets_controls, text="Save Current as Preset", command=self._save_preset).pack(side="left", padx=5)
        ctk.CTkButton(presets_controls, text="Load Preset", command=self._load_preset).pack(side="left", padx=5)
        ctk.CTkButton(presets_controls, text="Delete Preset", command=self._delete_preset).pack(side="left", padx=5)
        
        self.preset_list = ctk.CTkOptionMenu(presets_frame, values=["No presets available"])
        self.preset_list.pack(fill="x", padx=10, pady=5)
        
        # Load initial data
        self._refresh_system_info()
        self._refresh_gpu_info()
        self._refresh_recent_models()
        self._refresh_presets()
    
    def _refresh_system_info(self):
        """Refresh system information display."""
        try:
            system_info = get_system_info()
            refreshed_at = time.strftime("%Y-%m-%d %H:%M:%S")
            
            info_text = f"""System Information:
Updated: {refreshed_at}
Platform: {system_info.get('platform', 'Unknown')}
Python: {system_info.get('python_version', 'Unknown')}

CPU:
  Cores: {system_info.get('cpu', {}).get('count', 'Unknown')}
  Frequency: {system_info.get('cpu', {}).get('frequency', 'Unknown')} MHz
  Usage: {system_info.get('cpu', {}).get('usage', 'Unknown')}%

Memory:
  Total: {system_info.get('memory', {}).get('total_gb', 'Unknown')} GB
  Available: {system_info.get('memory', {}).get('available_gb', 'Unknown')} GB
  Usage: {system_info.get('memory', {}).get('percent', 'Unknown')}%

Disk:
  Total: {system_info.get('disk', {}).get('total_gb', 'Unknown')} GB
  Free: {system_info.get('disk', {}).get('free_gb', 'Unknown')} GB
  Usage: {system_info.get('disk', {}).get('percent', 'Unknown')}%
"""
            
            self.system_info_text.configure(state="normal")
            self.system_info_text.delete("1.0", "end")
            self.system_info_text.insert("end", info_text)
            self.system_info_text.configure(state="disabled")
            
        except Exception as e:
            self.logger.error(f"Error refreshing system info: {e}")
            self.system_info_text.configure(state="normal")
            self.system_info_text.delete("1.0", "end")
            self.system_info_text.insert("end", f"Error loading system info: {e}")
            self.system_info_text.configure(state="disabled")

    def _periodic_system_refresh(self):
        """Auto-refresh system tab data while that tab is selected."""
        try:
            if hasattr(self, "tabs") and self.tabs.get() == "System":
                self._refresh_system_info()
                self._refresh_gpu_info()
                self._refresh_recent_models()
                self._refresh_presets()
        except Exception as e:
            self.logger.error(f"Periodic system refresh error: {e}")
        finally:
            self.after(5000, self._periodic_system_refresh)
    
    def _refresh_gpu_info(self):
        """Refresh GPU information display."""
        try:
            gpu_info = get_gpu_info()
            
            if gpu_info.get("available", False):
                if "gpus" in gpu_info:
                    gpu_text = "GPU Information:\n"
                    for i, gpu in enumerate(gpu_info["gpus"]):
                        gpu_text += f"\nGPU {i + 1}: {gpu['name']}\n"
                        gpu_text += f"  Memory: {gpu['memory_total']} (Free: {gpu['memory_free']})\n"
                        gpu_text += f"  Utilization: {gpu['utilization']}\n"
                else:
                    gpu_text = f"GPU Information:\n{gpu_info.get('info', 'Unknown')}"
            else:
                gpu_text = f"GPU Information:\nNot available - {gpu_info.get('reason', 'Unknown reason')}"
            
            self.gpu_info_text.configure(state="normal")
            self.gpu_info_text.delete("1.0", "end")
            self.gpu_info_text.insert("end", gpu_text)
            self.gpu_info_text.configure(state="disabled")
            
        except Exception as e:
            self.logger.error(f"Error refreshing GPU info: {e}")
            self.gpu_info_text.configure(state="normal")
            self.gpu_info_text.delete("1.0", "end")
            self.gpu_info_text.insert("end", f"Error loading GPU info: {e}")
            self.gpu_info_text.configure(state="disabled")
    
    def _refresh_recent_models(self):
        """Refresh recent models list."""
        try:
            recent_models = self.config_manager.get_recent_models()
            
            if recent_models:
                models_text = "Recent Models:\n\n"
                for i, model_path in enumerate(recent_models, 1):
                    model_info = format_model_info(model_path)
                    models_text += f"{i}. {model_info['name']}\n"
                    models_text += f"   Size: {model_info['size']}\n"
                    models_text += f"   Path: {model_info['path']}\n\n"
            else:
                models_text = "Recent Models:\n\nNo recent models found."
            
            self.recent_models_list.configure(state="normal")
            self.recent_models_list.delete("1.0", "end")
            self.recent_models_list.insert("end", models_text)
            self.recent_models_list.configure(state="disabled")
            
        except Exception as e:
            self.logger.error(f"Error refreshing recent models: {e}")
            self.recent_models_list.configure(state="normal")
            self.recent_models_list.delete("1.0", "end")
            self.recent_models_list.insert("end", f"Error loading recent models: {e}")
            self.recent_models_list.configure(state="disabled")
    
    def _refresh_presets(self):
        """Refresh presets list."""
        try:
            presets = self.config_manager.get_all_presets()
            
            if presets:
                preset_names = list(presets.keys())
                self.preset_list.configure(values=preset_names)
                self.preset_list.set(preset_names[0])
            else:
                self.preset_list.configure(values=["No presets available"])
                self.preset_list.set("No presets available")
            
        except Exception as e:
            self.logger.error(f"Error refreshing presets: {e}")
            self.preset_list.configure(values=["Error loading presets"])
            self.preset_list.set("Error loading presets")
    
    def _save_preset(self):
        """Save current settings as a preset."""
        try:
            preset_name = self.preset_name_entry.get().strip()
            if not preset_name:
                self.log("Error: Please enter a preset name")
                return
            
            # Get current settings
            preset_data = {
                "server": {
                    "ctx": int(self.ctx_entry.get()),
                    "threads": int(self.threads_entry.get()),
                    "gpu_layers": int(self.gpu_entry.get()),
                    "batch_size": int(self.batch_entry.get()),
                    "n_predict": int(self.n_predict_entry.get()),
                    "host": self.host_entry.get(),
                    "port": int(self.port_entry.get()),
                    "extra_args": self.extra_args_entry.get()
                },
                "generation": {
                    "temperature": float(self.temp_entry.get()),
                    "top_p": float(self.topp_entry.get()),
                    "top_k": int(self.topk_entry.get()),
                    "min_p": float(self.minp_entry.get()),
                    "repeat_penalty": float(self.repeat_penalty_entry.get()),
                    "presence_penalty": float(self.presence_penalty_entry.get()),
                    "frequency_penalty": float(self.frequency_penalty_entry.get()),
                    "seed": int(self.seed_entry.get()),
                    "flash_attention": self.flash_attn_var.get(),
                    "chat_template": self.chat_template_var.get()
                }
            }
            
            self.config_manager.add_preset(preset_name, preset_data)
            self._refresh_presets()
            self.log(f"Preset '{preset_name}' saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving preset: {e}")
            self.log(f"Error saving preset: {e}")
    
    def _load_preset(self):
        """Load selected preset."""
        try:
            selected_preset = self.preset_list.get()
            if selected_preset == "No presets available" or selected_preset == "Error loading presets":
                self.log("Error: No preset selected")
                return
            
            preset_data = self.config_manager.get_preset(selected_preset)
            if not preset_data:
                self.log(f"Error: Could not load preset '{selected_preset}'")
                return
            
            # Apply server settings
            server_config = preset_data.get("server", {})
            self.ctx_entry.delete(0, "end"); self.ctx_entry.insert(0, str(server_config.get("ctx", 4096)))
            self.threads_entry.delete(0, "end"); self.threads_entry.insert(0, str(server_config.get("threads", 8)))
            self.gpu_entry.delete(0, "end"); self.gpu_entry.insert(0, str(server_config.get("gpu_layers", 35)))
            self.batch_entry.delete(0, "end"); self.batch_entry.insert(0, str(server_config.get("batch_size", 2048)))
            self.n_predict_entry.delete(0, "end"); self.n_predict_entry.insert(0, str(server_config.get("n_predict", -1)))
            self.host_entry.delete(0, "end"); self.host_entry.insert(0, server_config.get("host", "127.0.0.1"))
            self.port_entry.delete(0, "end"); self.port_entry.insert(0, str(server_config.get("port", 8080)))
            self.extra_args_entry.delete(0, "end"); self.extra_args_entry.insert(0, server_config.get("extra_args", ""))
            
            # Apply generation settings
            gen_config = preset_data.get("generation", {})
            
            # Temperature
            temp_enabled = gen_config.get("temperature", 0.7) != 0.7
            self.temp_var.set(temp_enabled)
            self.temp_entry.delete(0, "end"); self.temp_entry.insert(0, str(gen_config.get("temperature", 0.7)))
            
            # Top-P
            topp_enabled = gen_config.get("top_p", 0.9) != 0.9
            self.topp_var.set(topp_enabled)
            self.topp_entry.delete(0, "end"); self.topp_entry.insert(0, str(gen_config.get("top_p", 0.9)))
            
            # Top-K
            topk_enabled = gen_config.get("top_k", 40) != 40
            self.topk_var.set(topk_enabled)
            self.topk_entry.delete(0, "end"); self.topk_entry.insert(0, str(gen_config.get("top_k", 40)))
            
            # Min-P
            minp_enabled = gen_config.get("min_p", 0.0) != 0.0
            self.minp_var.set(minp_enabled)
            self.minp_entry.delete(0, "end"); self.minp_entry.insert(0, str(gen_config.get("min_p", 0.0)))
            
            # Repeat Penalty
            repeat_enabled = gen_config.get("repeat_penalty", 1.0) != 1.0
            self.repeat_var.set(repeat_enabled)
            self.repeat_penalty_entry.delete(0, "end"); self.repeat_penalty_entry.insert(0, str(gen_config.get("repeat_penalty", 1.0)))
            
            # Presence Penalty
            presence_enabled = gen_config.get("presence_penalty", 0.0) != 0.0
            self.presence_var.set(presence_enabled)
            self.presence_penalty_entry.delete(0, "end"); self.presence_penalty_entry.insert(0, str(gen_config.get("presence_penalty", 0.0)))
            
            # Frequency Penalty
            frequency_enabled = gen_config.get("frequency_penalty", 0.0) != 0.0
            self.frequency_var.set(frequency_enabled)
            self.frequency_penalty_entry.delete(0, "end"); self.frequency_penalty_entry.insert(0, str(gen_config.get("frequency_penalty", 0.0)))
            
            # Seed
            seed_enabled = gen_config.get("seed", -1) != -1
            self.seed_var.set(seed_enabled)
            self.seed_entry.delete(0, "end"); self.seed_entry.insert(0, str(gen_config.get("seed", -1)))
            
            # Flash Attention
            flash_enabled = gen_config.get("flash_attention", "auto") != "auto"
            self.flash_var.set(flash_enabled)
            self.flash_attn_var.set(gen_config.get("flash_attention", "auto"))
            
            # Chat Template
            template_enabled = gen_config.get("chat_template", "auto") != "auto"
            self.template_var.set(template_enabled)
            self.chat_template_var.set(gen_config.get("chat_template", "auto"))
            
            self.log(f"Preset '{selected_preset}' loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading preset: {e}")
            self.log(f"Error loading preset: {e}")
    
    def _delete_preset(self):
        """Delete selected preset."""
        try:
            selected_preset = self.preset_list.get()
            if selected_preset == "No presets available" or selected_preset == "Error loading presets":
                self.log("Error: No preset selected")
                return
            
            # For now, we'll just remove it from the config manager
            # In a real implementation, you might want to ask for confirmation
            presets = self.config_manager.get_all_presets()
            if selected_preset in presets:
                del presets[selected_preset]
                self.config_manager.set("presets", presets)
                self.config_manager.save()
                self._refresh_presets()
                self.log(f"Preset '{selected_preset}' deleted successfully")
            else:
                self.log(f"Error: Preset '{selected_preset}' not found")
                
        except Exception as e:
            self.logger.error(f"Error deleting preset: {e}")
            self.log(f"Error deleting preset: {e}")
    
    def _on_server_status_change(self, status_type: str, message: str):
        """Handle server status changes from ServerManager."""
        if status_type == "log":
            self.log(message)
        elif status_type == "success":
            self.status_label.configure(text="Server: Running", text_color="green")
            self.start_button.configure(text="Stop Server", state="normal")
            self.stop_button.configure(state="normal")
            self.log(message)
        elif status_type == "error":
            self.status_label.configure(text="Server: Error", text_color="red")
            self.start_button.configure(text="Start Server", state="normal")
            self.stop_button.configure(state="disabled")
            self.log(message)
        elif status_type == "info":
            if "stopping" in message.lower():
                self.status_label.configure(text="Server: Stopping", text_color="orange")
                self.start_button.configure(text="Stop Server", state="disabled")
                self.stop_button.configure(state="disabled")
            else:
                self.status_label.configure(text="Server: Stopped", text_color="red")
                self.start_button.configure(text="Start Server", state="normal")
                self.stop_button.configure(state="disabled")
            self.log(message)
    
    def _load_initial_state(self):
        """Load initial application state from configuration."""
        try:
            # Load model path
            self.model_path = self.config_manager.get("model_path")
            if self.model_path:
                model_info = format_model_info(self.model_path)
                self.model_info_label.configure(text=f"Model: {model_info['name']} ({model_info['size']})")
            
            # Load models directory
            self.models_dir = self.config_manager.get("models_dir", "")
            
            # Load server settings
            server_config = self.config_manager.get("server", {})
            self.ctx_entry.delete(0, "end"); self.ctx_entry.insert(0, str(server_config["ctx"]))
            self.threads_entry.delete(0, "end"); self.threads_entry.insert(0, str(server_config["threads"]))
            self.gpu_entry.delete(0, "end"); self.gpu_entry.insert(0, str(server_config["gpu_layers"]))
            self.batch_entry.delete(0, "end"); self.batch_entry.insert(0, str(server_config["batch_size"]))
            self.n_predict_entry.delete(0, "end"); self.n_predict_entry.insert(0, str(server_config["n_predict"]))
            self.host_entry.delete(0, "end"); self.host_entry.insert(0, server_config["host"])
            self.port_entry.delete(0, "end"); self.port_entry.insert(0, str(server_config["port"]))
            
            # Load generation settings
            gen_config = self.config_manager.get("generation", {})
            
            # Temperature
            temp_enabled = gen_config.get("temperature", 0.7) != 0.7
            self.temp_var.set(temp_enabled)
            self.temp_entry.delete(0, "end"); self.temp_entry.insert(0, str(gen_config["temperature"]))
            
            # Top-P
            topp_enabled = gen_config.get("top_p", 0.9) != 0.9
            self.topp_var.set(topp_enabled)
            self.topp_entry.delete(0, "end"); self.topp_entry.insert(0, str(gen_config["top_p"]))
            
            # Top-K
            topk_enabled = gen_config.get("top_k", 40) != 40
            self.topk_var.set(topk_enabled)
            self.topk_entry.delete(0, "end"); self.topk_entry.insert(0, str(gen_config["top_k"]))
            
            # Min-P
            minp_enabled = gen_config.get("min_p", 0.0) != 0.0
            self.minp_var.set(minp_enabled)
            self.minp_entry.delete(0, "end"); self.minp_entry.insert(0, str(gen_config["min_p"]))
            
            # Repeat Penalty
            repeat_enabled = gen_config.get("repeat_penalty", 1.0) != 1.0
            self.repeat_var.set(repeat_enabled)
            self.repeat_penalty_entry.delete(0, "end"); self.repeat_penalty_entry.insert(0, str(gen_config["repeat_penalty"]))
            
            # Presence Penalty
            presence_enabled = gen_config.get("presence_penalty", 0.0) != 0.0
            self.presence_var.set(presence_enabled)
            self.presence_penalty_entry.delete(0, "end"); self.presence_penalty_entry.insert(0, str(gen_config["presence_penalty"]))
            
            # Frequency Penalty
            frequency_enabled = gen_config.get("frequency_penalty", 0.0) != 0.0
            self.frequency_var.set(frequency_enabled)
            self.frequency_penalty_entry.delete(0, "end"); self.frequency_penalty_entry.insert(0, str(gen_config["frequency_penalty"]))
            
            # Seed
            seed_enabled = gen_config.get("seed", -1) != -1
            self.seed_var.set(seed_enabled)
            self.seed_entry.delete(0, "end"); self.seed_entry.insert(0, str(gen_config["seed"]))
            
            # Flash Attention
            flash_enabled = gen_config.get("flash_attention", "auto") != "auto"
            self.flash_var.set(flash_enabled)
            self.flash_attn_var.set(gen_config["flash_attention"])
            
            # Chat Template
            template_enabled = gen_config.get("chat_template", "auto") != "auto"
            self.template_var.set(template_enabled)
            self.chat_template_var.set(gen_config["chat_template"])
            
            # Extra args
            self.extra_args_entry.delete(0, "end")
            self.extra_args_entry.insert(0, server_config.get("extra_args", ""))
            
            # Refresh models list if directory is set
            if self.models_dir and os.path.isdir(self.models_dir):
                self.refresh_models_list()
            
            self.logger.info("Initial state loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading initial state: {e}")
            self.log(f"Warning: Could not load all settings: {e}")

    def on_closing(self):
        if hasattr(self, 'server_process') and self.server_process and self.server_process.poll() is None:
            self.stop_server()
        self.save_settings()
        self.destroy()

    # =========================================================
    # SETTINGS
    # =========================================================

    def load_settings(self):
        config_path = get_config_path()
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_settings(self):
        config_path = get_config_path()
        settings = {
            "model_path": self.model_path,
            "models_dir": self.models_dir,
            "ctx": self.ctx_entry.get(),
            "threads": self.threads_entry.get(),
            "gpu_layers": self.gpu_entry.get(),
            "batch_size": self.batch_entry.get(),
            "n_predict": self.n_predict_entry.get(),
            "host": self.host_entry.get(),
            "port": self.port_entry.get(),
            "temp_enabled": self.temp_var.get(),
            "temp": self.temp_entry.get(),
            "topp_enabled": self.topp_var.get(),
            "topp": self.topp_entry.get(),
            "topk_enabled": self.topk_var.get(),
            "topk": self.topk_entry.get(),
            "minp_enabled": self.minp_var.get(),
            "minp": self.minp_entry.get(),
            "repeat_enabled": self.repeat_var.get(),
            "repeat": self.repeat_penalty_entry.get(),
            "presence_enabled": self.presence_var.get(),
            "presence": self.presence_penalty_entry.get(),
            "frequency_enabled": self.frequency_var.get(),
            "frequency": self.frequency_penalty_entry.get(),
            "seed_enabled": self.seed_var.get(),
            "seed": self.seed_entry.get(),
            "flash_enabled": self.flash_var.get(),
            "flash": self.flash_attn_var.get(),
            "template_enabled": self.template_var.get(),
            "template": self.chat_template_var.get(),
            "extra_args": self.extra_args_entry.get()
        }
        try:
            with open(config_path, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def load_settings_to_ui(self):
        # Load model path
        self.model_path = self.config_manager.get("model_path")
        if self.model_path:
            model_info = format_model_info(self.model_path)
            self.model_info_label.configure(text=f"Model: {model_info['name']} ({model_info['size']})")
        
        # Load models directory
        self.models_dir = self.config_manager.get("models_dir", "")
        
        # Load server settings
        server_config = self.config_manager.get("server", {})
        self.ctx_entry.delete(0, "end"); self.ctx_entry.insert(0, str(server_config["ctx"]))
        self.threads_entry.delete(0, "end"); self.threads_entry.insert(0, str(server_config["threads"]))
        self.gpu_entry.delete(0, "end"); self.gpu_entry.insert(0, str(server_config["gpu_layers"]))
        self.batch_entry.delete(0, "end"); self.batch_entry.insert(0, str(server_config["batch_size"]))
        self.n_predict_entry.delete(0, "end"); self.n_predict_entry.insert(0, str(server_config["n_predict"]))
        self.host_entry.delete(0, "end"); self.host_entry.insert(0, server_config["host"])
        self.port_entry.delete(0, "end"); self.port_entry.insert(0, str(server_config["port"]))
        
        # Load generation settings
        gen_config = self.config_manager.get("generation", {})
        
        # Temperature
        temp_enabled = gen_config.get("temperature", 0.7) != 0.7
        self.temp_var.set(temp_enabled)
        self.temp_entry.delete(0, "end"); self.temp_entry.insert(0, str(gen_config["temperature"]))
        
        # Top-P
        topp_enabled = gen_config.get("top_p", 0.9) != 0.9
        self.topp_var.set(topp_enabled)
        self.topp_entry.delete(0, "end"); self.topp_entry.insert(0, str(gen_config["top_p"]))
        
        # Top-K
        topk_enabled = gen_config.get("top_k", 40) != 40
        self.topk_var.set(topk_enabled)
        self.topk_entry.delete(0, "end"); self.topk_entry.insert(0, str(gen_config["top_k"]))
        
        # Min-P
        minp_enabled = gen_config.get("min_p", 0.0) != 0.0
        self.minp_var.set(minp_enabled)
        self.minp_entry.delete(0, "end"); self.minp_entry.insert(0, str(gen_config["min_p"]))
        
        # Repeat Penalty
        repeat_enabled = gen_config.get("repeat_penalty", 1.0) != 1.0
        self.repeat_var.set(repeat_enabled)
        self.repeat_penalty_entry.delete(0, "end"); self.repeat_penalty_entry.insert(0, str(gen_config["repeat_penalty"]))
        
        # Presence Penalty
        presence_enabled = gen_config.get("presence_penalty", 0.0) != 0.0
        self.presence_var.set(presence_enabled)
        self.presence_penalty_entry.delete(0, "end"); self.presence_penalty_entry.insert(0, str(gen_config["presence_penalty"]))
        
        # Frequency Penalty
        frequency_enabled = gen_config.get("frequency_penalty", 0.0) != 0.0
        self.frequency_var.set(frequency_enabled)
        self.frequency_penalty_entry.delete(0, "end"); self.frequency_penalty_entry.insert(0, str(gen_config["frequency_penalty"]))
        
        # Seed
        seed_enabled = gen_config.get("seed", -1) != -1
        self.seed_var.set(seed_enabled)
        self.seed_entry.delete(0, "end"); self.seed_entry.insert(0, str(gen_config["seed"]))
        
        # Flash Attention
        flash_enabled = gen_config.get("flash_attention", "auto") != "auto"
        self.flash_var.set(flash_enabled)
        self.flash_attn_var.set(gen_config["flash_attention"])
        
        # Chat Template
        template_enabled = gen_config.get("chat_template", "auto") != "auto"
        self.template_var.set(template_enabled)
        self.chat_template_var.set(gen_config["chat_template"])
        
        # Extra args
        self.extra_args_entry.delete(0, "end")
        self.extra_args_entry.insert(0, server_config.get("extra_args", ""))

    def build_settings_tab(self):
        self.models_dir = ""

        # Use CTkScrollableFrame with proper configuration
        scroll_frame = ctk.CTkScrollableFrame(
            self.settings_tab,
            fg_color="transparent"
        )
        scroll_frame.pack(fill="both", expand=True)

        # ===== Model selection =====
        ctk.CTkLabel(scroll_frame, text="Model", font=("", 14, "bold")).pack(pady=(10, 5))

        model_frame = ctk.CTkFrame(scroll_frame)
        model_frame.pack(fill="x", padx=10, pady=5)

        self.model_label = ctk.CTkLabel(model_frame, text="Model: Not selected", anchor="w")
        self.model_label.pack(side="left", padx=5, fill="x", expand=True)

        ctk.CTkButton(model_frame, text="File", command=self.select_model, width=60).pack(side="right", padx=3)
        ctk.CTkButton(model_frame, text="Folder", command=self.select_models_folder, width=60).pack(side="right", padx=3)

        # Models list (if folder selected)
        self.models_list = ctk.CTkOptionMenu(scroll_frame, command=self.on_model_selected)
        self.models_list.pack(fill="x", padx=10, pady=5)

        # ===== Main params =====
        ctk.CTkLabel(scroll_frame, text="Main params", font=("", 14, "bold")).pack(pady=(10, 5))

        self.ctx_entry = self.create_param(scroll_frame, "Context", "4096")
        self.threads_entry = self.create_param(scroll_frame, "Threads", "8")
        self.gpu_entry = self.create_param(scroll_frame, "GPU Layers", "35")
        self.batch_entry = self.create_param(scroll_frame, "Batch Size", "2048")
        self.n_predict_entry = self.create_param(scroll_frame, "Max Tokens", "-1")

        self.host_entry = self.create_param(scroll_frame, "Host", "127.0.0.1")
        self.port_entry = self.create_param(scroll_frame, "Port", "8080")

        # ===== Extra params =====
        ctk.CTkLabel(scroll_frame, text="Extra params", font=("", 14, "bold")).pack(pady=(15, 5))

        # Temperature
        self.temp_var = ctk.BooleanVar(value=False)
        self.temp_check = ctk.CTkCheckBox(scroll_frame, text="Temperature", variable=self.temp_var)
        self.temp_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.temp_entry = self.create_param(scroll_frame, "  Temp", "0.7")

        # Top-P
        self.topp_var = ctk.BooleanVar(value=False)
        self.topp_check = ctk.CTkCheckBox(scroll_frame, text="Top-P", variable=self.topp_var)
        self.topp_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.topp_entry = self.create_param(scroll_frame, "  Top-P", "0.9")

        # Top-K
        self.topk_var = ctk.BooleanVar(value=False)
        self.topk_check = ctk.CTkCheckBox(scroll_frame, text="Top-K", variable=self.topk_var)
        self.topk_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.topk_entry = self.create_param(scroll_frame, "  Top-K", "40")

        # Min-P
        self.minp_var = ctk.BooleanVar(value=False)
        self.minp_check = ctk.CTkCheckBox(scroll_frame, text="Min-P", variable=self.minp_var)
        self.minp_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.minp_entry = self.create_param(scroll_frame, "  Min-P", "0.0")

        # Repeat Penalty
        self.repeat_var = ctk.BooleanVar(value=False)
        self.repeat_check = ctk.CTkCheckBox(scroll_frame, text="Repeat Penalty", variable=self.repeat_var)
        self.repeat_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.repeat_penalty_entry = self.create_param(scroll_frame, "  Repeat", "1.0")

        # Presence Penalty
        self.presence_var = ctk.BooleanVar(value=False)
        self.presence_check = ctk.CTkCheckBox(scroll_frame, text="Presence Penalty", variable=self.presence_var)
        self.presence_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.presence_penalty_entry = self.create_param(scroll_frame, "  Presence", "0.0")

        # Frequency Penalty
        self.frequency_var = ctk.BooleanVar(value=False)
        self.frequency_check = ctk.CTkCheckBox(scroll_frame, text="Frequency Penalty", variable=self.frequency_var)
        self.frequency_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.frequency_penalty_entry = self.create_param(scroll_frame, "  Frequency", "0.0")

        # Seed
        self.seed_var = ctk.BooleanVar(value=False)
        self.seed_check = ctk.CTkCheckBox(scroll_frame, text="Seed", variable=self.seed_var)
        self.seed_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.seed_entry = self.create_param(scroll_frame, "  Seed", "-1")

        # Flash Attention
        self.flash_var = ctk.BooleanVar(value=False)
        self.flash_check = ctk.CTkCheckBox(scroll_frame, text="Flash Attention", variable=self.flash_var)
        self.flash_check.pack(pady=(3, 0), anchor="w", padx=10)
        self.flash_attn_var = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.flash_attn_var,
            values=["on", "off", "auto"]
        ).pack(pady=3)

        # Chat Template
        self.template_var = ctk.BooleanVar(value=False)
        self.template_check = ctk.CTkCheckBox(scroll_frame, text="Chat Template", variable=self.template_var)
        self.template_check.pack(pady=(3, 0), anchor="w", padx=10)

        self.chat_template_var = ctk.StringVar(value="auto")
        self.chat_template_menu = ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.chat_template_var,
            values=[
                "auto",
                "chatml",
                "llama3",
                "mistral-v7",
                "phi3",
                "vicuna",
                "gemma",
                "deepseek",
                "command-r",
                "qwen2",
                "minicpm"
            ]
        )
        self.chat_template_menu.pack(pady=3)

        # ===== Extra command line args =====
        ctk.CTkLabel(scroll_frame, text="Extra args", font=("", 14, "bold")).pack(pady=(15, 5))
        ctk.CTkLabel(scroll_frame, text="Additional launch params", font=("", 10)).pack()

        self.extra_args_entry = ctk.CTkEntry(scroll_frame, placeholder_text="--param1 value1 --param2 value2")
        self.extra_args_entry.pack(fill="x", padx=10, pady=5)

        # Load saved settings
        self.after(100, self.load_settings_to_ui)

    def create_param(self, parent, label, default):
        frame = ctk.CTkFrame(parent)
        frame.pack(pady=3, fill="x")

        ctk.CTkLabel(frame, text=label).pack(side="left", padx=5)

        entry = ctk.CTkEntry(frame, width=120)
        entry.insert(0, default)
        entry.pack(side="right", padx=5)

        return entry

    def select_model(self):
        path = filedialog.askopenfilename(
            filetypes=[("GGUF files", "*.gguf")]
        )
        if path:
            self.model_path = path
            self.model_label.configure(text=f"Модель: {os.path.basename(path)}")
            self.log(f"Model selected: {path}")

    def select_models_folder(self):
        path = filedialog.askdirectory(title="Выберите папку с моделями")
        if path:
            self.models_dir = path
            self.refresh_models_list()

    def refresh_models_list(self):
        if not self.models_dir or not os.path.isdir(self.models_dir):
            return
        gguf_files = []
        for f in os.listdir(self.models_dir):
            if f.lower().endswith(".gguf"):
                gguf_files.append(f)
        if gguf_files:
            gguf_files.insert(0, "-- Выберите модель --")
            self.models_list.configure(values=gguf_files)
            self.models_list.set(gguf_files[0])
        else:
            self.models_list.configure(values=["Нет моделей"])

    def on_model_selected(self, model_name):
        if model_name and model_name != "-- Выберите модель --" and model_name != "Нет моделей":
            self.model_path = os.path.join(self.models_dir, model_name)
            self.model_label.configure(text=f"Модель: {model_name}")
            self.log(f"Model selected: {self.model_path}")

    # =========================================================
    # LOG
    # =========================================================

    def build_log_tab(self):
        self.log_box = ctk.CTkTextbox(self.log_tab)
        self.log_box.pack(expand=True, fill="both")

    def log(self, message):
        # Limit log size
        self.log_lines += 1
        if self.log_lines > self.max_log_lines:
            # Clear old log entries
            self.log_box.delete("1.0", "100.0")
            self.log_lines = int(self.log_box.index("end-1c").split(".")[0])
        
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    # =========================================================
    # CHAT
    # =========================================================

    def build_chat_tab(self):
        self.chat_box = ctk.CTkTextbox(
            self.chat_tab, 
            state="disabled",
            wrap="word",  # Enable word wrapping for better readability
            font=("Segoe UI", 12)  # Set a readable font
        )
        self.chat_box.pack(expand=True, fill="both", pady=5)

        self.thinking_label = ctk.CTkLabel(self.chat_tab, text="")
        self.thinking_label.pack()

        # Loading indicator
        self.loading_frame = ctk.CTkFrame(self.chat_tab)
        self.loading_frame.pack(fill="x", pady=5)
        self.loading_frame.pack_forget()  # Hidden by default
        
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="Starting server...")
        self.loading_label.pack(side="left", padx=10)
        
        self.loading_progress = ctk.CTkProgressBar(self.loading_frame)
        self.loading_progress.pack(side="right", padx=10, fill="x", expand=True)
        self.loading_progress.set(0)

        bottom = ctk.CTkFrame(self.chat_tab)
        bottom.pack(fill="x")

        self.prompt_entry = ctk.CTkEntry(bottom, placeholder_text="Введите ваш запрос...")
        self.prompt_entry.pack(side="left", expand=True, fill="x", padx=5)

        self.prompt_entry.bind("<Return>", lambda event: self.send_prompt())

        self.send_button = ctk.CTkButton(bottom, text="Send", command=self.send_prompt)
        self.send_button.pack(side="left", padx=5)

    def stop_gen(self):
        self.stop_generation = True

    def send_prompt(self):
        # If generating, stop instead
        if hasattr(self, '_generating') and self._generating:
            self.stop_gen()
            return

        if not self.server_process or self.server_process.poll() is not None:
            self.log("Server not running.")
            return

        self.stop_generation = False
        self._generating = True

        port = self.port_entry.get()
        host = self.host_entry.get()
        url = f"http://{host}:{port}/v1/chat/completions"

        prompt = self.prompt_entry.get().strip()
        if not prompt:
            return

        # Update chat UI immediately
        self._append_chat_text(f"You: {prompt}\nAI: ")
        self.thinking_label.configure(text="Thinking...")
        self.send_button.configure(text="Stop")

        self.prompt_entry.delete(0, "end")

        payload = {
            "model": "model",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": True
        }

        # Add extra params if checkbox is checked
        if self.temp_var.get():
            payload["temperature"] = float(self.temp_entry.get())
        if self.topp_var.get():
            payload["top_p"] = float(self.topp_entry.get())
        if self.topk_var.get():
            payload["top_k"] = int(self.topk_entry.get())
        if self.minp_var.get():
            payload["min_p"] = float(self.minp_entry.get())
        if self.repeat_var.get():
            payload["repeat_penalty"] = float(self.repeat_penalty_entry.get())
        if self.presence_var.get():
            payload["presence_penalty"] = float(self.presence_penalty_entry.get())
        if self.frequency_var.get():
            payload["frequency_penalty"] = float(self.frequency_penalty_entry.get())
        if self.seed_var.get():
            seed_val = int(self.seed_entry.get())
            if seed_val >= 0:
                payload["seed"] = seed_val

        max_tokens = int(self.n_predict_entry.get())
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens

        threading.Thread(
            target=self.generate,
            args=(url, payload),
            daemon=True
        ).start()

    def _append_chat_text(self, text: str):
        """Thread-safe append to chat box."""
        if text is None:
            return

        if not isinstance(text, str):
            text = str(text)

        if text == "":
            return

        self.chat_box.configure(state="normal")
        # CTkTextbox.insert forwards a "tags" argument; pass an empty tuple
        # to avoid underlying Tk receiving an invalid None tag list.
        self.chat_box.insert("end", text, ())
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _finish_generation_ui(self):
        """Reset UI when generation finishes."""
        self._append_chat_text("\n\n")
        self.thinking_label.configure(text="")
        self.send_button.configure(text="Send")
        self._generating = False

    def _handle_generation_error_ui(self, error_text: str):
        """Show generation error and reset UI."""
        self.log("Streaming error: " + error_text)
        self.thinking_label.configure(text="")
        self.send_button.configure(text="Send")
        self._generating = False

    def generate(self, url, payload):
        try:
            with requests.post(url, json=payload, stream=True, timeout=(10, 300)) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if self.stop_generation:
                        break

                    if not line:
                        continue

                    decoded = line.decode("utf-8")

                    if not decoded.startswith("data:"):
                        continue

                    data = decoded[len("data:"):].strip()

                    if data == "[DONE]":
                        break

                    try:
                        json_data = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = json_data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    if "content" in delta:
                        token = delta["content"]
                        self.after(0, self._append_chat_text, token)

                # Finish generation
                self.after(0, self._finish_generation_ui)

        except Exception as e:
            self.after(0, self._handle_generation_error_ui, str(e))

    # =========================================================
    # SERVER
    # =========================================================

    def toggle_server(self):
        if self.server_process and self.server_process.poll() is None:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        # Validate inputs first
        if not self.model_path:
            self.log("Error: Select model first.")
            return

        if not self.validate_inputs():
            return

        # Check if port is available
        if not self.check_port_available():
            return

        # Save settings before starting
        self.save_settings()

        # Show loading indicator
        self.show_loading("Starting server...")

        # Start server in a separate thread to avoid blocking UI
        threading.Thread(target=self._start_server_thread, daemon=True).start()

    def _start_server_thread(self):
        try:
            base_path = get_app_path()
            llama_path = os.path.join(base_path, "bin", "llama-server.exe")
            
            # Check if llama-server.exe exists
            if not os.path.exists(llama_path):
                self.log(f"Error: llama-server.exe not found at {llama_path}")
                self.hide_loading()
                return

            cmd = [
                llama_path,
                "-m", self.model_path,
                "--ctx-size", self.ctx_entry.get(),
                "--threads", self.threads_entry.get(),
                "--n-gpu-layers", self.gpu_entry.get(),
                "--host", self.host_entry.get(),
                "--port", self.port_entry.get(),
                "--batch-size", self.batch_entry.get(),
                "-n", self.n_predict_entry.get()
            ]

            template = self.chat_template_var.get()
            if self.template_var.get() and template != "auto":
                cmd.extend(["--chat-template", template])

            if self.flash_var.get():
                flash_attn = self.flash_attn_var.get()
                if flash_attn != "auto":
                    cmd.extend(["--flash-attn", flash_attn])

            # Add extra command line args
            extra_args = self.extra_args_entry.get().strip()
            if extra_args:
                # Split by spaces but respect quoted args
                try:
                    extra_parts = shlex.split(extra_args)
                    cmd.extend(extra_parts)
                except Exception as e:
                    self.log(f"Error parsing extra args: {e}")
                    self.hide_loading()
                    return

            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            # Wait a moment to see if server starts successfully
            import time
            time.sleep(2)
            
            if self.server_process.poll() is not None:
                # Server exited immediately - likely an error
                self.log("Error: Server failed to start. Check the log for details.")
                self.hide_loading()
                return

            threading.Thread(target=self.read_log, daemon=True).start()

            # Update UI on main thread
            self.after(100, self._update_server_started_ui)

        except Exception as e:
            self.log(f"Error starting server: {e}")
            self.hide_loading()

    def _update_server_started_ui(self):
        self.start_button.configure(text="Stop Server")
        self.status_label.configure(text="Server: Running")
        self.log("Server started successfully.")
        self.hide_loading()

    def stop_server(self):
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process = None
            except Exception as e:
                self.log(f"Error stopping server: {e}")

        self.start_button.configure(text="Start Server")
        self.status_label.configure(text="Server: Stopped")
        self.log("Server stopped.")

    def show_loading(self, message="Loading..."):
        self.loading_label.configure(text=message)
        self.loading_progress.set(0.5)  # Indeterminate progress
        self.loading_frame.pack(fill="x", pady=5)
        self.start_button.configure(state="disabled")

    def hide_loading(self):
        self.loading_frame.pack_forget()
        self.start_button.configure(state="normal")

    def validate_inputs(self) -> bool:
        """Validate all input fields and return True if valid."""
        try:
            # Validate numeric fields
            ctx = int(self.ctx_entry.get())
            threads = int(self.threads_entry.get())
            gpu_layers = int(self.gpu_entry.get())
            batch_size = int(self.batch_entry.get())
            n_predict = int(self.n_predict_entry.get())
            
            if ctx <= 0:
                self.log("Error: Context must be positive")
                return False
            if threads <= 0:
                self.log("Error: Threads must be positive")
                return False
            if gpu_layers < 0:
                self.log("Error: GPU layers must be non-negative")
                return False
            if batch_size <= 0:
                self.log("Error: Batch size must be positive")
                return False
            if n_predict < -1:
                self.log("Error: Max tokens must be -1 or positive")
                return False

            # Validate host and port
            port = int(self.port_entry.get())
            if port <= 0 or port > 65535:
                self.log("Error: Port must be between 1 and 65535")
                return False

            # Validate optional numeric fields if enabled
            if self.temp_var.get():
                temp = float(self.temp_entry.get())
                if temp < 0:
                    self.log("Error: Temperature must be non-negative")
                    return False

            if self.topp_var.get():
                topp = float(self.topp_entry.get())
                if topp <= 0 or topp > 1:
                    self.log("Error: Top-P must be between 0 and 1")
                    return False

            if self.topk_var.get():
                topk = int(self.topk_entry.get())
                if topk <= 0:
                    self.log("Error: Top-K must be positive")
                    return False

            if self.minp_var.get():
                minp = float(self.minp_entry.get())
                if minp < 0 or minp > 1:
                    self.log("Error: Min-P must be between 0 and 1")
                    return False

            if self.repeat_var.get():
                repeat = float(self.repeat_penalty_entry.get())
                if repeat < 0:
                    self.log("Error: Repeat penalty must be non-negative")
                    return False

            if self.presence_var.get():
                presence = float(self.presence_penalty_entry.get())
                if presence < 0:
                    self.log("Error: Presence penalty must be non-negative")
                    return False

            if self.frequency_var.get():
                frequency = float(self.frequency_penalty_entry.get())
                if frequency < 0:
                    self.log("Error: Frequency penalty must be non-negative")
                    return False

            if self.seed_var.get():
                seed = int(self.seed_entry.get())
                if seed < -1:
                    self.log("Error: Seed must be -1 or positive")
                    return False

            return True

        except ValueError:
            self.log("Error: Invalid numeric input")
            return False

    def check_port_available(self) -> bool:
        """Check if the specified port is available."""
        try:
            port = int(self.port_entry.get())
            host = self.host_entry.get()
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                if result == 0:
                    self.log(f"Error: Port {port} is already in use")
                    return False
            return True
        except Exception as e:
            self.log(f"Error checking port: {e}")
            return False

    def read_log(self):
        if not self.server_process or not self.server_process.stdout:
            return
        for line in self.server_process.stdout:
            decoded = line.decode("utf-8", errors="replace")
            self.log(decoded.strip())


if __name__ == "__main__":
    app = LlamaGUI()
    app.mainloop()