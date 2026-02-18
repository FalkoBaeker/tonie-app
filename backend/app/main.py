from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.services.market_refresh import run_refresh_now
from app.services.persistence import init_db

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    auto_refresh_task: asyncio.Task | None = None

    async def _auto_refresh_loop() -> None:
        interval_seconds = max(1, settings.market_auto_refresh_interval_minutes) * 60
        limit = settings.market_auto_refresh_limit if settings.market_auto_refresh_limit > 0 else None

        while True:
            try:
                await run_refresh_now(
                    limit=limit,
                    delay_ms=max(0, settings.market_auto_refresh_delay_ms),
                    max_items=max(10, settings.market_auto_refresh_max_items),
                )
                logger.info("Market auto-refresh completed")
            except RuntimeError:
                logger.info("Market auto-refresh skipped (another refresh is already running)")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Market auto-refresh failed")

            await asyncio.sleep(interval_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal auto_refresh_task
        init_db()

        if settings.market_auto_refresh_enabled and auto_refresh_task is None:
            auto_refresh_task = asyncio.create_task(_auto_refresh_loop())
            logger.info(
                "Market auto-refresh enabled (interval=%s min, limit=%s)",
                settings.market_auto_refresh_interval_minutes,
                settings.market_auto_refresh_limit,
            )

        try:
            yield
        finally:
            if auto_refresh_task is not None:
                auto_refresh_task.cancel()
                try:
                    await auto_refresh_task
                except asyncio.CancelledError:
                    pass
                finally:
                    auto_refresh_task = None

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
