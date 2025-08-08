from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DateRange = tuple[Optional[datetime], Optional[datetime]]


@dataclass
class EntryFilter:
    prefix_after: str = ""
    modified_date_range: DateRange = (None, None)

    def passes(self, event: dict) -> bool:
        key = event["Key"]
        modified_date = event["LastModified"]

        start_date, end_date = self.modified_date_range
        if start_date and modified_date < start_date:
            return False
        if end_date and modified_date > end_date:
            return False

        return key >= self.prefix_after
