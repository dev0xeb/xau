#!/usr/bin/env python3
"""
config_validator.py - Pre-flight Startup Configuration Validator

Validates configuration schema integrity, required fields, range boundaries,
and logical contradictions (e.g. single trade risk exceeding max daily risk limit)
to prevent execution startup with dangerous/invalid settings.
"""

from execution_engine.errors import ConfigurationError

class ConfigValidator:
    """Pre-flight validator for system configuration schemas."""

    DEFAULT_REQUIRED_KEYS = ["risk_parameters", "execution_parameters", "environment"]

    @staticmethod
    def validate_config(config: dict) -> bool:
        """
        Validates configuration dictionary.
        Raises ConfigurationError if validation fails.
        """
        if not isinstance(config, dict):
            raise ConfigurationError("Configuration must be a dictionary object.")

        # 1. Check required top-level sections
        for key in ConfigValidator.DEFAULT_REQUIRED_KEYS:
            if key not in config:
                raise ConfigurationError(f"Missing required configuration section: '{key}'")

        risk_cfg = config.get("risk_parameters", {})
        exec_cfg = config.get("execution_parameters", {})
        env = config.get("environment", "").upper()

        if env not in ["SIMULATION", "LIVE_BROKER"]:
            raise ConfigurationError(f"Invalid environment configuration: '{env}'. Must be 'SIMULATION' or 'LIVE_BROKER'.")

        # 2. Check risk numerical boundaries & logical consistency
        max_single_trade_risk = risk_cfg.get("max_single_trade_risk_pct", 0.0)
        max_daily_risk = risk_cfg.get("max_daily_risk_pct", 0.0)

        if max_single_trade_risk <= 0 or max_single_trade_risk > 10.0:
            raise ConfigurationError(f"Invalid max_single_trade_risk_pct: {max_single_trade_risk}%. Must be in range (0, 10].")

        if max_daily_risk <= 0 or max_daily_risk > 20.0:
            raise ConfigurationError(f"Invalid max_daily_risk_pct: {max_daily_risk}%. Must be in range (0, 20].")

        # Logical contradiction check
        if max_single_trade_risk > max_daily_risk:
            raise ConfigurationError(
                f"Logical configuration error: single trade risk ({max_single_trade_risk}%) "
                f"exceeds max daily risk ({max_daily_risk}%)."
            )

        # 3. Check execution parameters
        max_spread = exec_cfg.get("max_spread_usd", 0.0)
        if max_spread <= 0 or max_spread > 5.0:
            raise ConfigurationError(f"Invalid max_spread_usd: ${max_spread}. Must be in range (0, 5.0].")

        min_lot = exec_cfg.get("min_lot_size", 0.01)
        max_lot = exec_cfg.get("max_lot_size", 10.0)
        if min_lot >= max_lot:
            raise ConfigurationError(f"Invalid lot limits: min_lot ({min_lot}) >= max_lot ({max_lot}).")

        return True
