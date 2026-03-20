from pathlib import Path
from typing import List

from ..configs import AppSettings
from ..sinks import GazeSink, ParquetSink, NATSSink

def create_session_sinks(
    settings: AppSettings, 
    participant_dir: Path
) -> List[GazeSink]:
    """
    Creates fresh sink instances for a new recording session.
    """
    sinks = []

    # NATS
    if settings.nats.enabled:
        sinks.append(NATSSink(host=settings.nats.host))

    # Parquet
    if settings.parquet.enabled:
        sinks.append(
            ParquetSink(
                output_dir=participant_dir,
                drop_when_full=settings.parquet.drop_when_full,
                max_buffer_size=settings.parquet.max_buffer_size,
                queue_size=settings.parquet.queue_size
            )
        )

    return sinks