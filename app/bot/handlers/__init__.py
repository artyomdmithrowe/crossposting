from aiogram import Router

from .invitations import router as invitations_router
from .start import router as start_router

router = Router(name="main")

router.include_routers(
    invitations_router,
    start_router,
)

__all__ = ["router"]
