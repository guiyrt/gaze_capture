from pathlib import Path
from typing import List
import nats

from ..configs import AppSettings
from ..sinks import GazeSink, ParquetSink, NATSSink

def create_sinks(
    settings: AppSettings,
    output_dir: Path | None = None,
    nc: nats.NATS | None = None
) -> List[GazeSink]:
    """
    Creates fresh sink instances for a new recording session.
    """
    sinks = []

    # NATS
    if settings.nats.enabled:
        if nc is not None:
            sinks.append(
                NATSSink(
                    nc=nc,
                    subject=settings.nats.subject
                )
            )
        else:
            ValueError("NATS sink not created, no `nc` NATS instance passed to factory.")

    # Parquet
    if settings.parquet.enabled:
        sinks.append(
            ParquetSink(
                output_dir=output_dir or settings.data_dir,
                drop_when_full=settings.parquet.drop_when_full,
                max_buffer_size=settings.parquet.max_buffer_size,
                queue_size=settings.parquet.queue_size
            )
        )

    return sinks