#!/usr/bin/env python3
"""
logging_config.py - Centralized Category Log Configurator

Directs logs into dedicated files under logs/:
- logs/market_data.log
- logs/decision.log
- logs/execution.log
- logs/broker.log
- logs/telegram.log
- logs/risk.log
- logs/heartbeat.log
- logs/audit.log
"""

import os
import logging

LOG_CATEGORIES = [
    "market_data",
    "decision",
    "execution",
    "broker",
    "telegram",
    "risk",
    "heartbeat",
    "audit"
]

def setup_category_loggers(logs_dir: str = "logs") -> dict:
    """Configures category-specific file loggers."""
    os.makedirs(logs_dir, exist_ok=True)
    loggers = {}

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")

    for cat in LOG_CATEGORIES:
        logger = logging.getLogger(f"Category.{cat}")
        logger.setLevel(logging.INFO)
        # Clear existing handlers
        logger.handlers.clear()

        log_file = os.path.join(logs_dir, f"{cat}.log")
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        loggers[cat] = logger

    return loggers
