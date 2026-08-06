import os

from observatory.logging_setup import configure_logging, shutdown_logging


def main() -> None:
    configure_logging()
    try:
        import uvicorn

        uvicorn.run(
            "main:app",
            host=os.getenv("ALPAQUERO_HOST", "127.0.0.1"),
            port=int(os.getenv("ALPAQUERO_PORT", "8000")),
            log_config=None,
            access_log=True,
            workers=1,
        )
    finally:
        shutdown_logging()


if __name__ == "__main__":
    main()
