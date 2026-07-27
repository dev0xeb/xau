#!/usr/bin/env python3
"""
errors.py - Structured Error Taxonomy for Production Execution Engine

Categorizes execution and subsystem failures to enable precise remediation:
- ProgrammingError: Code or logic defect -> Immediate system shutdown
- ConfigurationError: Misconfiguration / schema breach -> Disable execution, alert operator
- ExternalDependencyError: External API or network fault -> Retry with backoff
- ConnectivityError: Broker / network disconnect -> Trigger circuit breaker / reconnect
- BrokerRejectError: Broker order rejection -> Record, evaluate retry / DLQ
- ValidationError: Pre-broker rule failure -> Reject candidate, route to DLQ
- RiskError: Risk gate breach -> Block candidate execution
- MarketClosedError: Session inactive -> Pause execution
- MarginError: Insufficient equity / margin -> Reject candidate
- TimeoutError: Operation timed out -> Evaluate retry / fallback
"""

class ExecutionEngineError(Exception):
    """Base exception for all execution engine errors."""
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

class ProgrammingError(ExecutionEngineError):
    """Internal code/logic defect requiring immediate system shutdown."""
    pass

class ConfigurationError(ExecutionEngineError):
    """Invalid configuration or schema violation requiring operator alert."""
    pass

class ExternalDependencyError(ExecutionEngineError):
    """External API or dependency failure eligible for retry with backoff."""
    pass

class ConnectivityError(ExecutionEngineError):
    """Broker or network connection loss."""
    pass

class BrokerRejectError(ExecutionEngineError):
    """Broker order submission rejection."""
    pass

class ValidationError(ExecutionEngineError):
    """Pre-broker order parameter validation failure."""
    pass

class RiskError(ExecutionEngineError):
    """Risk management threshold breach."""
    pass

class MarketClosedError(ExecutionEngineError):
    """Market trading session is closed."""
    pass

class MarginError(ExecutionEngineError):
    """Insufficient free margin or account equity."""
    pass

class TimeoutError(ExecutionEngineError):
    """Execution or network response timeout."""
    pass
