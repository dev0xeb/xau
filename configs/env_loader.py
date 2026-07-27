#!/usr/bin/env python3
"""
env_loader.py - Environment Variable Loader

Loads configuration parameters from .env file into os.environ if present.
"""

import os

def load_env_file(env_path: str = ".env"):
    """Parses .env file and sets environment variables if not already set."""
    if not os.path.exists(env_path):
        return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val

# Auto-load on import
load_env_file()
