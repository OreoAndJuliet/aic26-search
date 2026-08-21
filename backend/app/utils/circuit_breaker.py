"""Circuit breaker implementation for external API calls.

This provides fault tolerance for external service calls by implementing
the circuit breaker pattern to prevent cascading failures.
"""

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, calls fail fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5        # Number of failures before opening
    recovery_timeout: float = 60.0     # Seconds to wait before half-open
    expected_exception: type = Exception  # Exception type to track
    timeout: float = 30.0              # Call timeout in seconds


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""


class CircuitBreaker:
    """Circuit breaker implementation for external service calls."""
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.success_count = 0
        
    def record_success(self) -> None:
        """Record a successful call."""
        self.failure_count = 0
        self.success_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            # If we get enough successes in half-open, close the circuit
            if self.success_count >= 2:  # Require 2 consecutive successes
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' closed after recovery")
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0
        
        if (self.state == CircuitState.CLOSED and 
            self.failure_count >= self.config.failure_threshold):
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker '{self.name}' opened after "
                f"{self.failure_count} failures"
            )
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker '{self.name}' reopened after half-open failure")
    
    def can_attempt(self) -> bool:
        """Check if a call can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if (self.last_failure_time and 
                time.time() - self.last_failure_time >= self.config.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker '{self.name}' moved to half-open")
                return True
            return False
        
        # HALF_OPEN state - allow limited attempts
        return True
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute a synchronous function with circuit breaker protection."""
        if not self.can_attempt():
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is open. "
                f"Service unavailable. Try again later."
            )
        
        try:
            if inspect.iscoroutinefunction(func):
                try:
                    asyncio.get_running_loop()
                    raise RuntimeError("Cannot execute coroutine with sync CircuitBreaker.call() from inside a running event loop; use call_async().")
                except RuntimeError as loop_err:
                    if "no running event loop" in str(loop_err) or "Cannot execute" not in str(loop_err):
                        if self.config.timeout:
                            result = asyncio.run(
                                asyncio.wait_for(
                                    func(*args, **kwargs),
                                    timeout=self.config.timeout
                                )
                            )
                        else:
                            result = asyncio.run(func(*args, **kwargs))
                    else:
                        raise
            else:
                result = func(*args, **kwargs)
                    
        except self.config.expected_exception as e:
            self.record_failure()
            logger.error(
                f"Circuit breaker '{self.name}' recorded failure: {e}"
            )
            raise
        except Exception as e:
            self.record_failure()
            logger.error(
                f"Circuit breaker '{self.name}' recorded unexpected failure: {e}"
            )
            raise
        else:
            self.record_success()
            return result

    async def call_async(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Execute an asynchronous coroutine function with circuit breaker protection."""
        if not self.can_attempt():
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is open. "
                f"Service unavailable. Try again later."
            )

        try:
            coro = func(*args, **kwargs) if inspect.iscoroutinefunction(func) else asyncio.to_thread(func, *args, **kwargs)
            if self.config.timeout:
                result = await asyncio.wait_for(coro, timeout=self.config.timeout)
            else:
                result = await coro
        except self.config.expected_exception as e:
            self.record_failure()
            logger.error(f"Circuit breaker '{self.name}' recorded failure: {e}")
            raise
        except Exception as e:
            self.record_failure()
            logger.error(f"Circuit breaker '{self.name}' recorded unexpected failure: {e}")
            raise
        else:
            self.record_success()
            return result


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None
) -> CircuitBreaker:
    """Get or create a circuit breaker with the given name."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def with_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None
):
    """Decorator to add circuit breaker protection to a function."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker = get_circuit_breaker(name, config)
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return breaker.call(func, *args, **kwargs)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            return await breaker.call_async(func, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
    
    return decorator


def reset_circuit_breaker(name: str) -> None:
    """Reset a circuit breaker to closed state."""
    if name in _circuit_breakers:
        breaker = _circuit_breakers[name]
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 0
        breaker.last_failure_time = None
        breaker.success_count = 0
        logger.info(f"Circuit breaker '{name}' reset to closed state")


def get_circuit_breaker_status(name: str) -> dict[str, Any]:
    """Get the current status of a circuit breaker."""
    if name not in _circuit_breakers:
        return {"error": f"Circuit breaker '{name}' not found"}
    
    breaker = _circuit_breakers[name]
    return {
        "name": breaker.name,
        "state": breaker.state.value,
        "failure_count": breaker.failure_count,
        "success_count": breaker.success_count,
        "last_failure_time": breaker.last_failure_time,
        "config": {
            "failure_threshold": breaker.config.failure_threshold,
            "recovery_timeout": breaker.config.recovery_timeout,
            "timeout": breaker.config.timeout,
        }
    }


def get_all_circuit_breaker_statuses() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    return {
        name: get_circuit_breaker_status(name)
        for name in _circuit_breakers
    }