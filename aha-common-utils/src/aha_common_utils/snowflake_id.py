"""
Snowflake ID Generator

A distributed unique ID generator based on Twitter's Snowflake algorithm.

ID Structure (64 bits):
- 1 bit: Reserved (always 0)
- 41 bits: Timestamp (milliseconds since epoch)
- 5 bits: Data center ID
- 5 bits: Worker ID
- 12 bits: Sequence number

This allows for:
- ~69 years of timestamps (from epoch)
- 32 data centers
- 32 workers per data center
- 4096 IDs per millisecond per worker
"""

import threading
import time
from typing import Optional


class SnowflakeIDGenerator:
    """
    Thread-safe Snowflake ID generator.

    Attributes:
        epoch: Custom epoch timestamp in milliseconds (default: 2020-01-01 00:00:00 UTC)
        data_center_id: Data center identifier (0-31)
        worker_id: Worker identifier (0-31)
    """

    # Bit lengths
    WORKER_ID_BITS = 5
    DATA_CENTER_ID_BITS = 5
    SEQUENCE_BITS = 12

    # Max values
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1  # 31
    MAX_DATA_CENTER_ID = (1 << DATA_CENTER_ID_BITS) - 1  # 31
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

    # Bit shifts
    WORKER_ID_SHIFT = SEQUENCE_BITS
    DATA_CENTER_ID_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS + DATA_CENTER_ID_BITS

    # Default epoch: 2020-01-01 00:00:00 UTC (in milliseconds)
    DEFAULT_EPOCH = 1577836800000

    def __init__(
        self,
        data_center_id: int = 0,
        worker_id: int = 0,
        epoch: Optional[int] = None
    ):
        """
        Initialize Snowflake ID generator.

        Args:
            data_center_id: Data center ID (0-31)
            worker_id: Worker ID (0-31)
            epoch: Custom epoch timestamp in milliseconds (default: 2020-01-01)

        Raises:
            ValueError: If data_center_id or worker_id is out of range
        """
        if data_center_id < 0 or data_center_id > self.MAX_DATA_CENTER_ID:
            raise ValueError(
                f"Data center ID must be between 0 and {self.MAX_DATA_CENTER_ID}"
            )

        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(
                f"Worker ID must be between 0 and {self.MAX_WORKER_ID}"
            )

        self.data_center_id = data_center_id
        self.worker_id = worker_id
        self.epoch = epoch if epoch is not None else self.DEFAULT_EPOCH

        self._last_timestamp = -1
        self._sequence = 0
        self._lock = threading.Lock()

    def _current_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        """
        Wait until next millisecond.

        Args:
            last_timestamp: Last generated timestamp

        Returns:
            Next timestamp
        """
        timestamp = self._current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._current_timestamp()
        return timestamp

    def generate_id(self) -> int:
        """
        Generate a unique Snowflake ID.

        Returns:
            64-bit unique ID

        Raises:
            RuntimeError: If clock moves backwards
        """
        with self._lock:
            timestamp = self._current_timestamp()

            # Clock moved backwards
            if timestamp < self._last_timestamp:
                raise RuntimeError(
                    f"Clock moved backwards. Refusing to generate ID for "
                    f"{self._last_timestamp - timestamp} milliseconds"
                )

            # Same millisecond
            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & self.MAX_SEQUENCE

                # Sequence overflow
                if self._sequence == 0:
                    timestamp = self._wait_next_millis(self._last_timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp

            # Generate ID
            snowflake_id = (
                ((timestamp - self.epoch) << self.TIMESTAMP_SHIFT) |
                (self.data_center_id << self.DATA_CENTER_ID_SHIFT) |
                (self.worker_id << self.WORKER_ID_SHIFT) |
                self._sequence
            )

            return snowflake_id

    def generate_ids(self, count: int) -> list[int]:
        """
        Generate multiple unique Snowflake IDs.

        Args:
            count: Number of IDs to generate

        Returns:
            List of unique IDs
        """
        return [self.generate_id() for _ in range(count)]

    def generate_string_id(self) -> str:
        """
        Generate a unique Snowflake ID as a string.

        Returns:
            String representation of 64-bit unique ID
        """
        return str(self.generate_id())

    def generate_string_ids(self, count: int) -> list[str]:
        """
        Generate multiple unique Snowflake IDs as strings.

        Args:
            count: Number of IDs to generate

        Returns:
            List of string IDs
        """
        return [str(self.generate_id()) for _ in range(count)]

    def parse_id(self, snowflake_id: int) -> dict:
        """
        Parse a Snowflake ID into its components.

        Args:
            snowflake_id: Snowflake ID to parse

        Returns:
            Dictionary with timestamp, data_center_id, worker_id, and sequence
        """
        timestamp_bits = (snowflake_id >> self.TIMESTAMP_SHIFT) + self.epoch
        data_center_id = (
            (snowflake_id >> self.DATA_CENTER_ID_SHIFT) & self.MAX_DATA_CENTER_ID
        )
        worker_id = (snowflake_id >> self.WORKER_ID_SHIFT) & self.MAX_WORKER_ID
        sequence = snowflake_id & self.MAX_SEQUENCE

        return {
            "timestamp": timestamp_bits,
            "timestamp_readable": time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(timestamp_bits / 1000)
            ),
            "data_center_id": data_center_id,
            "worker_id": worker_id,
            "sequence": sequence
        }


# Global default instance
_default_generator: Optional[SnowflakeIDGenerator] = None
_generator_lock = threading.Lock()


def get_default_generator(
    data_center_id: int = 0,
    worker_id: int = 0,
    epoch: Optional[int] = None
) -> SnowflakeIDGenerator:
    """
    Get or create the default global Snowflake ID generator.

    Args:
        data_center_id: Data center ID (0-31)
        worker_id: Worker ID (0-31)
        epoch: Custom epoch timestamp in milliseconds

    Returns:
        Default SnowflakeIDGenerator instance
    """
    global _default_generator

    with _generator_lock:
        if _default_generator is None:
            _default_generator = SnowflakeIDGenerator(
                data_center_id=data_center_id,
                worker_id=worker_id,
                epoch=epoch
            )
        return _default_generator


def generate_id() -> int:
    """
    Generate a Snowflake ID using the default generator.

    Returns:
        64-bit unique ID
    """
    return get_default_generator().generate_id()


def generate_ids(count: int) -> list[int]:
    """
    Generate multiple Snowflake IDs using the default generator.

    Args:
        count: Number of IDs to generate

    Returns:
        List of unique IDs
    """
    return get_default_generator().generate_ids(count)


def parse_id(snowflake_id: int) -> dict:
    """
    Parse a Snowflake ID using the default generator.

    Args:
        snowflake_id: Snowflake ID to parse

    Returns:
        Dictionary with timestamp, data_center_id, worker_id, and sequence
    """
    return get_default_generator().parse_id(snowflake_id)


def generate_string_id() -> str:
    """
    Generate a Snowflake ID as a string using the default generator.

    Returns:
        String representation of 64-bit unique ID
    """
    return get_default_generator().generate_string_id()


def generate_string_ids(count: int) -> list[str]:
    """
    Generate multiple Snowflake IDs as strings using the default generator.

    Args:
        count: Number of IDs to generate

    Returns:
        List of string IDs
    """
    return get_default_generator().generate_string_ids(count)


# Convenience aliases
snowflake_id = generate_id
snowflake_string_id = generate_string_id
