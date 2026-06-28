"""Stripe webhook processing — updates user subscription tiers in MongoDB."""
import os
from datetime import datetime, timezone

import stripe
from fastapi import HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

PRICE_TO_TIER = {}


def _build_price_map():
    global PRICE_TO_TIER
    PRICE_TO_TIER = {
        os.environ.get("STRIPE_PRICE_DESIGNER", ""): "designer",
        os.environ.get("STRIPE_PRICE_STUDIO", ""): "studio",
        os.environ.get("STRIPE_PRICE_AGENCY", ""): "agency",
    }
    PRICE_TO_TIER.pop("", None)


_build_price_map()


async def handle_webhook(request: Request, db: AsyncIOMotorDatabase):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        await _handle_checkout(data, db)
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        await _handle_subscription_updated(data, db)
    elif etype == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)

    return {"status": "ok"}


async def _handle_checkout(session, db):
    customer_id = session.get("customer")
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id or not customer_id:
        return

    # Retrieve the subscription to get the price
    sub_id = session.get("subscription")
    if sub_id:
        sub = stripe.Subscription.retrieve(sub_id)
        await _upsert_subscription(user_id, customer_id, sub, db)
    else:
        await db["user_subscriptions"].update_one(
            {"user_id": user_id},
            {"$set": {"stripe_customer_id": customer_id, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )


async def _handle_subscription_updated(sub, db):
    customer_id = sub.get("customer")
    doc = await db["user_subscriptions"].find_one({"stripe_customer_id": customer_id})
    user_id = doc["user_id"] if doc else None
    if user_id:
        await _upsert_subscription(user_id, customer_id, sub, db)


async def _handle_subscription_deleted(sub, db):
    customer_id = sub.get("customer")
    await db["user_subscriptions"].update_one(
        {"stripe_customer_id": customer_id},
        {"$set": {"tier": "free", "valid_until": None, "updated_at": datetime.now(timezone.utc)}},
    )


async def _upsert_subscription(user_id: str, customer_id: str, sub, db):
    _build_price_map()
    price_id = sub["items"]["data"][0]["price"]["id"] if sub.get("items", {}).get("data") else ""
    tier = PRICE_TO_TIER.get(price_id, "free")

    period_end = sub.get("current_period_end")
    valid_until = datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None

    await db["user_subscriptions"].update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": sub.get("id"),
            "tier": tier,
            "valid_until": valid_until,
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
