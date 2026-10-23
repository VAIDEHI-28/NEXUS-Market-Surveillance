
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from nexus.schemas.trade import TradeEvent


class TradeStorage:
    """Persist trade batches as separate Parquet files."""

    def __init__(self, data_dir: str = "data/raw/trades"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def write_batch(self, trades: list[TradeEvent]) -> Path | None:
        if not trades:
            return None

        records = [
            trade.model_dump(mode="json")
            for trade in trades
        ]
        table = pa.Table.from_pylist(records)

        now = datetime.now(timezone.utc)
        filename = (
            f"trades_{now:%Y%m%dT%H%M%S}_"
            f"{uuid4().hex[:8]}.parquet"
        )
        output_path = self.data_dir / filename

        pq.write_table(table, output_path, compression="snappy")

        return output_path
