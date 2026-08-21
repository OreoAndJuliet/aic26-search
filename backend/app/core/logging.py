import logging


def configure_logging(log_level: str) -> None:
    """Configure concise logs without emitting request contents or secrets."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )
