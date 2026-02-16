import time
from typing import Callable

class TimeProbe:
    __slots__ = ("latency", "offset")

    def __init__(self, now_us_func: Callable[[], int]):
        before: int = now_us_func()
        utc: int = time.time_ns()
        after: int = now_us_func()

        # Use integer division to keep timestamp as int
        system_timestamp_at_utc: int = (before + after) // 2

        # Latency in us
        self.latency: int = after - before
        # Offset is ns - (us * 1000), result is ns (int)
        self.offset: int = utc - (system_timestamp_at_utc * 1_000)

    def to_utc_ms(self, system_timestamp_us: int) -> int:
        # Convert timestamp from us to ns to apply offset, then final timestamp from ns to ms
        return (system_timestamp_us * 1_000 + self.offset) // 1_000_000

    # Sort by latency, lower is better
    def __lt__(self, other: "TimeProbe") -> bool:
        return self.latency < other.latency

    def __eq__(self, other: "TimeProbe") -> bool:
        return self.latency == other.latency