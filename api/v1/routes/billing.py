from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response
from api.v1.dependencies.auth import get_current_user
from api.v1.models.user import User
from api.v1.schemas.billing import CheckoutRequest, PortalRequest, SelectPlanRequest
from api.v1.services import billing_service

billing_router = APIRouter(prefix="/billing", tags=["Billing"])


@billing_router.post("/plan", status_code=status.HTTP_200_OK)
async def select_plan(
    body: SelectPlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await billing_service.set_free_plan(user, db)
    return success_response(message="Plan selected successfully", data=None)


@billing_router.post("/checkout", status_code=status.HTTP_200_OK)
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    checkout_url = await billing_service.create_checkout_session(user, body.currency, db)
    return success_response(
        message="Checkout session created",
        data={"checkout_url": checkout_url},
    )


@billing_router.post("/portal", status_code=status.HTTP_200_OK)
async def create_portal(
    body: PortalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    portal_url = await billing_service.create_portal_session(user, body.return_url)
    return success_response(
        message="Portal session created",
        data={"portal_url": portal_url},
    )


@billing_router.get("/status", status_code=status.HTTP_200_OK)
async def billing_status(
    user: User = Depends(get_current_user),
) -> JSONResponse:
    data = billing_service.get_billing_status(user)
    return success_response(message="Billing status retrieved", data=data)


@billing_router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    await billing_service.handle_webhook(payload, sig_header, db)
    return JSONResponse(status_code=200, content={"received": True})
