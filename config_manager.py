import json
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

class ConfigManager:
    """Manages application configuration with validation and migration support."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config_dir = os.path.dirname(self.config_path)
        self.config_version = "1.0"
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Default configuration
        self.default_config = {
            "version": self.config_version,
            "model_path": None,
            "models_dir": "",
            "server": {
                "ctx": 4096,
                "threads": 8,
                "gpu_layers": 35,
                "batch_size": 2048,
                "n_predict": -1,
                "host": "127.0.0.1",
                "port": 8080,
                "extra_args": ""
            },
            "generation": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "min_p": 0.0,
                "repeat_penalty": 1.0,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "seed": -1,
                "flash_attention": "auto",
                "chat_template": "auto"
            },
            "ui": {
                "max_log_lines": 1000,
                "auto_save": True,
                "theme": "system"
            },
            "recent_models": [],
            "presets": {}
        }
        
        self.config = self._load_config()
    
    def _get_default_config_path(self) -> str:
        """Get the default configuration file path."""
        config_dir = os.path.join(os.path.expanduser("~"), ".llamagui")
        return os.path.join(config_dir, "config.json")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file with migration support."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # Migrate old config format
                if self._needs_migration(loaded_config):
                    loaded_config = self._migrate_config(loaded_config)
                
                # Merge with defaults
                config = self._merge_with_defaults(loaded_config)
                return config
            
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logging.warning(f"Failed to load config: {e}. Using defaults.")
        
        return self.default_config.copy()
    
    def _needs_migration(self, config: Dict[str, Any]) -> bool:
        """Check if configuration needs migration."""
        return "version" not in config or config.get("version") != self.config_version
    
    def _migrate_config(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old configuration format to new format."""
        new_config = self.default_config.copy()
        
        # Migrate old top-level keys
        migration_map = {
            "model_path": ("model_path", None),
            "models_dir": ("models_dir", ""),
            "ctx": ("server.ctx", 4096),
            "threads": ("server.threads", 8),
            "gpu_layers": ("server.gpu_layers", 35),
            "batch_size": ("server.batch_size", 2048),
            "n_predict": ("server.n_predict", -1),
            "host": ("server.host", "127.0.0.1"),
            "port": ("server.port", 8080),
            "temp": ("generation.temperature", 0.7),
            "topp": ("generation.top_p", 0.9),
            "topk": ("generation.top_k", 40),
            "minp": ("generation.min_p", 0.0),
            "repeat": ("generation.repeat_penalty", 1.0),
            "presence": ("generation.presence_penalty", 0.0),
            "frequency": ("generation.frequency_penalty", 0.0),
            "seed": ("generation.seed", -1),
            "flash": ("generation.flash_attention", "auto"),
            "template": ("generation.chat_template", "auto"),
            "extra_args": ("server.extra_args", "")
        }
        
        for old_key, (new_path, default) in migration_map.items():
            if old_key in old_config:
                self._set_nested_value(new_config, new_path, old_config[old_key])
        
        return new_config
    
    def _set_nested_value(self, config: Dict[str, Any], path: str, value: Any):
        """Set a nested configuration value using dot notation."""
        keys = path.split('.')
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge configuration with defaults."""
        result = self.default_config.copy()
        
        def merge_recursive(base: Dict[str, Any], update: Dict[str, Any]):
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge_recursive(base[key], value)
                else:
                    base[key] = value
        
        merge_recursive(result, config)
        return result
    
    def save(self):
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except (PermissionError, OSError) as e:
            logging.error(f"Failed to save config: {e}")
            raise
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        keys = key_path.split('.')
        current = self.config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def set(self, key_path: str, value: Any):
        """Set a configuration value using dot notation."""
        keys = key_path.split('.')
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    def add_recent_model(self, model_path: str):
        """Add a model to the recent models list."""
        if not model_path:
            return
        
        recent_models = self.get("recent_models", [])
        if model_path in recent_models:
            recent_models.remove(model_path)
        
        recent_models.insert(0, model_path)
        
        # Keep only last 10 models
        recent_models = recent_models[:10]
        self.set("recent_models", recent_models)
        self.save()
    
    def get_recent_models(self) -> List[str]:
        """Get list of recent models."""
        return self.get("recent_models", [])
    
    def add_preset(self, name: str, config: Dict[str, Any]):
        """Add or update a preset configuration."""
        presets = self.get("presets", {})
        presets[name] = config
        self.set("presets", presets)
        self.save()
    
    def get_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a preset configuration."""
        presets = self.get("presets", {})
        return presets.get(name)
    
    def get_all_presets(self) -> Dict[str, Dict[str, Any]]:
        """Get all preset configurations."""
        return self.get("presets", {})
    
    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self.config = self.default_config.copy()
        self.save()
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate server settings
        server = self.get("server", {})
        if not isinstance(server.get("port"), int) or not (1 <= server["port"] <= 65535):
            errors.append("Port must be between 1 and 65535")
        
        if not isinstance(server.get("ctx"), int) or server["ctx"] <= 0:
            errors.append("Context size must be positive")
        
        if not isinstance(server.get("threads"), int) or server["threads"] <= 0:
            errors.append("Threads must be positive")
        
        if not isinstance(server.get("gpu_layers"), int) or server["gpu_layers"] < 0:
            errors.append("GPU layers must be non-negative")
        
        # Validate generation settings
        gen = self.get("generation", {})
        if not isinstance(gen.get("temperature"), (int, float)) or gen["temperature"] < 0:
            errors.append("Temperature must be non-negative")
        
        if not isinstance(gen.get("top_p"), (int, float)) or not (0 <= gen["top_p"] <= 1):
            errors.append("Top-P must be between 0 and 1")
        
        if not isinstance(gen.get("top_k"), int) or gen["top_k"] <= 0:
            errors.append("Top-K must be positive")
        
        if not isinstance(gen.get("min_p"), (int, float)) or not (0 <= gen["min_p"] <= 1):
            errors.append("Min-P must be between 0 and 1")
        
        if not isinstance(gen.get("repeat_penalty"), (int, float)) or gen["repeat_penalty"] < 0:
            errors.append("Repeat penalty must be non-negative")
        
        if not isinstance(gen.get("seed"), int) or gen["seed"] < -1:
            errors.append("Seed must be -1 or positive")
        
        return errors
    
    def get_model_info(self, model_path: str) -> Dict[str, Any]:
        """Get information about a model file."""
        if not model_path or not os.path.exists(model_path):
            return {}
        
        try:
            file_size = os.path.getsize(model_path)
            return {
                "path": model_path,
                "size": file_size,
                "size_mb": round(file_size / (1024 * 1024), 2),
                "basename": os.path.basename(model_path),
                "exists": True
            }
        except OSError:
            return {
                "path": model_path,
                "exists": False
            }