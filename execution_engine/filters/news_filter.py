#!/usr/bin/env python3
"""
news_filter.py - Automated Economic News Calendar Guardrail Filter

Fetches and evaluates live High-Impact (Red Folder) economic events for USD / XAUUSD:
- Automatically pauses trade signal generation 30 minutes BEFORE and 30 minutes AFTER
  high-impact releases (FOMC Rate Decisions, CPI Inflation, NFP Employment, Fed Chair Speeches).
- Includes local fallback schedules for high-impact release windows.
"""

import os
import sys
import logging
import json
import urllib.request
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("EconomicNewsFilter")

class EconomicNewsFilter:
    """Automated Economic Calendar News Guardrail Filter."""

    def __init__(
        self,
        buffer_minutes_before: int = 30,
        buffer_minutes_after: int = 30,
        enabled: bool = True
    ):
        self.buffer_before = timedelta(minutes=buffer_minutes_before)
        self.buffer_after = timedelta(minutes=buffer_minutes_after)
        self.enabled = enabled
        self.cached_events = []
        self.last_fetch_time = None
        self._load_initial_calendar()

    def _load_initial_calendar(self):
        """Fetches live economic calendar or initializes fallback high-impact event windows."""
        try:
            self.fetch_live_events()
        except Exception as e:
            logger.warning(f"Could not fetch live economic calendar feed ({e}). Initializing high-impact news windows.")
            self._use_fallback_events()

    def fetch_live_events(self):
        """Fetches live economic events from public calendar API endpoint."""
        url = "https://nfp.ourfocus.net/api/news"  # Public economic calendar feed
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    events = []
                    for item in data:
                        impact = str(item.get("impact", "")).lower()
                        currency = str(item.get("currency", "")).upper()
                        if currency in ["USD", "XAU"] and impact in ["high", "red", "3"]:
                            t_str = item.get("date") or item.get("time")
                            if t_str:
                                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                                events.append({"title": item.get("title", "High Impact USD Event"), "datetime": dt})
                    self.cached_events = events
                    self.last_fetch_time = datetime.now(timezone.utc)
                    logger.info(f"Successfully loaded {len(events)} high-impact economic news events.")
                    return
        except Exception:
            pass

        # Fallback to local high-impact event detection if live API unavailable
        self._use_fallback_events()

    def _use_fallback_events(self):
        """Populates known high-impact FOMC / CPI / NFP windows for safety."""
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # High impact recurring windows (e.g. FOMC 18:00 - 20:00 UTC, CPI/NFP 13:30 UTC)
        fallback = [
            {"title": "FOMC Rate Announcement & Press Conference", "datetime": today.replace(hour=18, minute=0)},
            {"title": "FOMC Press Conference", "datetime": today.replace(hour=18, minute=30)},
            {"title": "FOMC Policy Statement", "datetime": today.replace(hour=19, minute=0)},
            {"title": "US CPI / NFP High-Impact Data", "datetime": today.replace(hour=13, minute=30)},
        ]
        self.cached_events = fallback
        self.last_fetch_time = now

    def is_news_blocked(self, check_time: datetime = None) -> tuple[bool, str]:
        """
        Evaluates whether check_time (default current UTC time) falls within
        the 30-minute pre/post window of a high-impact news event.

        Returns:
            (is_blocked: bool, reason: str)
        """
        if not self.enabled:
            return False, "News Filter Disabled"

        if check_time is None:
            check_time = datetime.now(timezone.utc)

        # Refresh cached events if older than 4 hours
        if self.last_fetch_time is None or (check_time - self.last_fetch_time) > timedelta(hours=4):
            self.fetch_live_events()

        for ev in self.cached_events:
            ev_dt = ev["datetime"]
            start_block = ev_dt - self.buffer_before
            end_block = ev_dt + self.buffer_after

            if start_block <= check_time <= end_block:
                title = ev.get("title", "High-Impact Event")
                reason = f"PAUSED: {title} at {ev_dt.strftime('%H:%M UTC')} (Window {start_block.strftime('%H:%M')}-{end_block.strftime('%H:%M UTC')})"
                return True, reason

        return False, "CLEAN"
