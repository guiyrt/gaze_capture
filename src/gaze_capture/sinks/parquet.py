import time
import asyncio
import logging
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Optional

from .base import GazeSink
from ..models import GazeData
from ..utils.logging import ThrottledLogger
from ..utils.types import EndToken, _END

logger = logging.getLogger(__name__)

class ParquetSink(GazeSink):
    """
    Optimized Parquet Sink for constant 120Hz Gaze Data.
    Flushes to disk based on buffer size.
    """
    _SCHEMA: Final[pa.Schema] = pa.schema([
        # Unix Epoch
        ("timestamp", pa.timestamp('ms')),
        
        # Derived Midpoint Data
        ("mid_x_px", pa.int32()),
        ("mid_y_px", pa.int32()),
        ("mid_x", pa.float32()),
        ("mid_y", pa.float32()),
        
        # Raw Monotonic Timestamps
        ("device_ts_us", pa.int64()),
        ("system_ts_us", pa.int64()),
        
        # Raw Sensor Data
        ("left_x", pa.float32()),
        ("left_y", pa.float32()),
        ("right_x", pa.float32()),
        ("right_y", pa.float32()),
        ("left_pupil", pa.float32()),
        ("right_pupil", pa.float32()),
        
        # User 3D Coordinates (eye and gaze-point)
        ("left_3d", pa.list_(pa.float32())),
        ("right_3d", pa.list_(pa.float32())),
        ("left_origin", pa.list_(pa.float32())),
        ("right_origin", pa.list_(pa.float32())),
    ])

    def __init__(
        self,
        output_dir: Path,
        drop_when_full: bool,
        max_buffer_size: int,
        queue_size: int,
    ) -> None:
        self.max_buffer_size = max_buffer_size
        self.drop_when_full = drop_when_full
        
        # Setup file with UTC timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = output_dir / f"eye_tracker_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.parquet"
        
        # Internal state
        self._queue: asyncio.Queue[GazeData | EndToken] = asyncio.Queue(maxsize=queue_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._writer: Optional[pq.ParquetWriter] = None

        # Stats
        self._total_rows = 0
        self._total_preds_dropped = 0
        self._drop_logger = ThrottledLogger(logger, interval_sec=1)

        logger.info(f"ParquetSink initialized. Writing to: {self.output_path}")
    
    async def send(self, data: GazeData) -> None:
        """Push data to the queue. Handles backpressure or dropping."""
        if self.drop_when_full:
            try:
                self._queue.put_nowait(data)
            except asyncio.QueueFull:
                self._total_preds_dropped += 1
                self._drop_logger.warning("Queue is full, dropping gaze sample.")
        else:
            await self._queue.put(data)
    
    async def _worker(self) -> None:
        """
        Simplified high-throughput worker.
        Drains queue and flushes when buffer is full.
        """
        buffer: list[GazeData] = []
        
        # Localize variables for tight-loop performance
        queue = self._queue
        max_buf = self.max_buffer_size

        while True:
            # 1. Wait for the first item (Anchor)
            item = await queue.get()
            if item is _END:
                break
            buffer.append(item)

            # 2. Greedy Drain (Grab all currently in queue up to limit)
            while not queue.empty() and len(buffer) < max_buf:
                try:
                    next_item = queue.get_nowait()
                    if next_item is _END:
                        await self._flush(buffer)
                        return 
                    buffer.append(next_item)
                except asyncio.QueueEmpty:
                    break

            # 3. Buffer Full Check
            if len(buffer) >= max_buf:
                await self._flush(buffer)
                buffer.clear()
        
        # Final cleanup on closure
        await self._flush(buffer)

    async def _flush(self, batch: list[GazeData]) -> None:
        """Offloads Columnar conversion and IO to a background thread."""
        if not batch:
            return
        
        try:
            self._total_rows += await asyncio.to_thread(self._write_sync, batch)
        except Exception as e:
            logger.error(f"Parquet flush failed: {e}")
            self._total_preds_dropped += len(batch)

    def _write_sync(self, batch: list[GazeData]) -> int:
        """
        Synchronous Arrow conversion and Parquet write.
        Pre-allocates lists for peak performance.
        """
        size = len(batch)
        
        # Pre-allocate flat columns
        epoch_ts, device_ts, system_ts = [None] * size, [None] * size, [None] * size
        m_x_px, m_y_px, m_x, m_y = [None] * size, [None] * size, [None] * size, [None] * size
        l_x, l_y, r_x, r_y = [None] * size, [None] * size, [None] * size, [None] * size
        l_pup, r_pup = [None] * size, [None] * size
        l_3d, r_3d = [None] * size, [None] * size
        l_origin, r_origin = [None] * size, [None] * size

        for i, d in enumerate(batch):
            epoch_ts[i] = d.epoch_timestamp_ms
            device_ts[i] = d.device_timestamp_us
            system_ts[i] = d.system_timestamp_us
            
            m_x_px[i] = d.mid_x_px
            m_y_px[i] = d.mid_y_px
            m_x[i] = d.mid_x
            m_y[i] = d.mid_y
            
            l_x[i], l_y[i] = d.left_x, d.left_y
            r_x[i], r_y[i] = d.right_x, d.right_y
            
            l_pup[i], r_pup[i] = d.left_pupil, d.right_pupil
            
            # Convert tuples to lists for Arrow FixedSizeList compatibility
            if d.left_3d is not None:
                l_3d[i] = list(d.left_3d)
            if d.right_3d is not None:
                r_3d[i] = list(d.right_3d)
            if d.left_origin is not None:
                l_origin[i] = list(d.left_origin)
            if d.right_origin is not None:
                r_origin[i] = list(d.right_origin)
            
        table = pa.Table.from_arrays(
            [
                pa.array(epoch_ts, type=pa.timestamp('ms')),
                pa.array(m_x_px, type=pa.int32()),
                pa.array(m_y_px, type=pa.int32()),
                pa.array(m_x, type=pa.float32()),
                pa.array(m_y, type=pa.float32()),
                pa.array(device_ts, type=pa.int64()),
                pa.array(system_ts, type=pa.int64()),
                pa.array(l_x, type=pa.float32()),
                pa.array(l_y, type=pa.float32()),
                pa.array(r_x, type=pa.float32()),
                pa.array(r_y, type=pa.float32()),
                pa.array(l_pup, type=pa.float32()),
                pa.array(r_pup, type=pa.float32()),
                pa.array(l_3d, type=pa.list_(pa.float32())),
                pa.array(r_3d, type=pa.list_(pa.float32())),
                pa.array(l_origin, type=pa.list_(pa.float32())),
                pa.array(r_origin, type=pa.list_(pa.float32())),
            ],
            schema=self._SCHEMA
        )
        
        if self._writer is None:
            self._writer = pq.ParquetWriter(
                self.output_path, 
                schema=self._SCHEMA, 
                compression="zstd",
                version="2.6",
                metadata_collector=[]
            )
        
        self._writer.write_table(table)
        return size

    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def close(self) -> None:
        if self._worker_task:
            await self._queue.put(_END)
            await self._worker_task
            self._worker_task = None
        
        if self._writer:
            await asyncio.to_thread(self._writer.close)
            self._writer = None
            logger.info(f"Parquet closed. Written: {self._total_rows:,}, Dropped: {self._total_preds_dropped:,}")