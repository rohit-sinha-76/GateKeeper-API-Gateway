import time
from enum import Enum
from redis.exceptions import RedisError
from core.config import settings
from services.redis_client import get_redis
from utils.logger import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


async def get_circuit_state(service_name: str = "upstream") -> CircuitState:
    """
    Query the current circuit breaker state for a downstream service.
    
    State Logic:
    1. If explicit 'OPEN' state key exists in Redis:
       - If cooldown period has elapsed, transitions to HALF_OPEN.
       - Otherwise, remains OPEN.
    2. If no 'OPEN' key exists, circuit is CLOSED.
    """
    try:
        redis = await get_redis()
        state_key = f"circuit_breaker:{service_name}:state"
        opened_at_key = f"circuit_breaker:{service_name}:opened_at"

        state_val = await redis.get(state_key)
        if state_val == CircuitState.OPEN.value:
            opened_at_str = await redis.get(opened_at_key)
            if opened_at_str:
                elapsed = time.time() - float(opened_at_str)
                if elapsed >= settings.CIRCUIT_BREAKER_RECOVERY_SECONDS:
                    return CircuitState.HALF_OPEN
            return CircuitState.OPEN

        return CircuitState.CLOSED

    except Exception as e:
        logger.warning("Redis error checking circuit state; defaulting to CLOSED (fail-open)", extra={"error": str(e)})
        return CircuitState.CLOSED


async def acquire_half_open_probe(service_name: str = "upstream") -> bool:
    """
    Atomically acquire permission to execute a single canary probe in HALF_OPEN state.
    Prevents a thundering herd when downstream enters recovery testing.
    """
    try:
        redis = await get_redis()
        probe_key = f"circuit_breaker:{service_name}:probe_lock"
        # SET with NX and 10s TTL: Only 1 concurrent worker gets True
        acquired = await redis.set(probe_key, "1", ex=10, nx=True)
        return bool(acquired)
    except Exception:
        return True


async def record_success(service_name: str = "upstream") -> None:
    """
    Record a successful upstream request.
    If circuit was in HALF_OPEN or OPEN, fully resets circuit to CLOSED.
    """
    try:
        redis = await get_redis()
        state = await get_circuit_state(service_name)
        if state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("Canary probe succeeded; resetting Circuit Breaker to CLOSED", extra={"service": service_name})
            keys_to_delete = [
                f"circuit_breaker:{service_name}:state",
                f"circuit_breaker:{service_name}:opened_at",
                f"circuit_breaker:{service_name}:failures",
                f"circuit_breaker:{service_name}:probe_lock",
            ]
            await redis.delete(*keys_to_delete)

    except Exception as e:
        logger.warning("Redis error recording circuit success", extra={"error": str(e)})



async def record_failure(service_name: str = "upstream") -> CircuitState:
    """
    Record an upstream failure (timeout, 502/503/504, connection error).
    Transitions circuit to OPEN if threshold is exceeded or if failing in HALF_OPEN.
    """
    try:
        redis = await get_redis()
        state = await get_circuit_state(service_name)

        if state == CircuitState.HALF_OPEN:
            # Canary probe failed: Immediately trip circuit back to OPEN with fresh cooldown
            logger.warning("Canary probe failed; tripping circuit back to OPEN", extra={"service": service_name})
            await _trip_circuit_open(redis, service_name)
            return CircuitState.OPEN

        # If currently CLOSED, increment window failure counter
        fail_key = f"circuit_breaker:{service_name}:failures"
        failures = await redis.incr(fail_key)
        if failures == 1:
            await redis.expire(fail_key, settings.CIRCUIT_BREAKER_WINDOW_SECONDS)

        if failures >= settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            logger.warning(
                "Circuit failure threshold exceeded; tripping circuit to OPEN",
                extra={"service": service_name, "failures": failures, "threshold": settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD},
            )
            await _trip_circuit_open(redis, service_name)
            return CircuitState.OPEN

        return CircuitState.CLOSED

    except Exception as e:
        logger.warning("Redis error recording circuit failure", extra={"error": str(e)})
        return CircuitState.CLOSED


async def _trip_circuit_open(redis, service_name: str) -> None:
    """Set circuit state to OPEN with timestamp and expiration."""
    state_key = f"circuit_breaker:{service_name}:state"
    opened_at_key = f"circuit_breaker:{service_name}:opened_at"
    probe_key = f"circuit_breaker:{service_name}:probe_lock"

    # State key TTL is set to recovery duration * 2 as a safety margin
    ttl = int(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS * 2)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(state_key, CircuitState.OPEN.value, ex=ttl)
        pipe.set(opened_at_key, str(time.time()), ex=ttl)
        pipe.delete(probe_key)
        await pipe.execute()


async def reset_circuit(service_name: str = "upstream") -> None:
    """Manually force reset the circuit breaker for a given service."""
    await record_success(service_name)

