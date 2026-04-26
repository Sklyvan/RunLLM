"""Uvicorn entrypoint."""

from __future__ import annotations

import uvicorn

from runllm.api.app import create_app
from runllm.config import get_settings

app = create_app()


def main() -> None:
    """Run the dev server."""

    settings = get_settings()
    uvicorn.run(
        "runllm.api.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    main()
