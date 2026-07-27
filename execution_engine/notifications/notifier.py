#!/usr/bin/env python3
"""
notifier.py - Abstract Notification Subsystem

Provides a decoupled notification interface:
Notifier -> ConsoleNotifier, TelegramNotifier, SlackNotifier, EmailNotifier
"""

from abc import ABC, abstractmethod
import logging
import json
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Notifier")

class Notifier(ABC):
    @abstractmethod
    def notify(self, level: str, title: str, message: str, metadata: dict = None) -> bool:
        """Send a notification alert."""
        pass

class ConsoleNotifier(Notifier):
    """Outputs structured alerts to the system console/logger."""
    def notify(self, level: str, title: str, message: str, metadata: dict = None) -> bool:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "title": title,
            "message": message,
            "metadata": metadata or {}
        }
        log_msg = f"[{payload['level']}] {title}: {message} | {json.dumps(payload['metadata'])}"
        if level.upper() in ["ERROR", "CRITICAL", "HALT"]:
            logger.error(log_msg)
        elif level.upper() == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        return True

class TelegramNotifier(Notifier):
    """Integrates Telegram control bot for live notifications."""
    def __init__(self, bot_token: str = None, chat_id: str = None):
        from execution_engine.notifications.telegram_bot import TelegramControlBot
        self.bot = TelegramControlBot(bot_token=bot_token)
        self.chat_id = chat_id

    def notify(self, level: str, title: str, message: str, metadata: dict = None) -> bool:
        body = f"{message}\n\n*Metadata*: `{json.dumps(metadata or {})}`"
        return self.bot.send_notification(f"[{level.upper()}] {title}", body)

class SlackNotifier(Notifier):
    """Placeholder for Slack webhook notifications."""
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url

    def notify(self, level: str, title: str, message: str, metadata: dict = None) -> bool:
        logger.info(f"[SLACK STUB] [{level}] {title}: {message}")
        return True

class EmailNotifier(Notifier):
    """Placeholder for Email alerts."""
    def __init__(self, smtp_config: dict = None):
        self.smtp_config = smtp_config or {}

    def notify(self, level: str, title: str, message: str, metadata: dict = None) -> bool:
        logger.info(f"[EMAIL STUB] [{level}] {title}: {message}")
        return True
