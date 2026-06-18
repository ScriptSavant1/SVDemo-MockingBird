"""Entry point: sv-metrics-service."""
import uvicorn

from .main import app


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")


if __name__ == "__main__":
    main()
