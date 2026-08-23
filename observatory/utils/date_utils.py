from datetime import datetime, timedelta, timezone


def get_date_folder(
    night_folder: bool = True,
    at: datetime | None = None,
) -> str:
    """Return the UTC date folder, optionally grouped by observing night.

    Observing-night folders roll over at noon UTC, so times before noon are
    assigned to the preceding calendar date.
    """
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")

    at_utc = at.astimezone(timezone.utc)
    if night_folder:
        at_utc -= timedelta(hours=12)

    return at_utc.date().isoformat()
