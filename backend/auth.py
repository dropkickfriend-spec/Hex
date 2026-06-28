"""Supabase JWT verification and tier-based access control."""
import os
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

TIERS = ["free", "designer", "studio", "agency"]
TIER_LIMITS = {
    "free":     {"brand_kits": 3,   "gif_exports_per_month": 3,   "api_access": False},
    "designer": {"brand_kits": 50,  "gif_exports_per_month": 999, "api_access": False},
    "studio":   {"brand_kits": 200, "gif_exports_per_month": 999, "api_access": True},
    "agency":   {"brand_kits": 999, "gif_exports_per_month": 999, "api_access": True},
}

_jwt_secret: Optional[str] = None


def _get_jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    return _jwt_secret


def _tier_rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else 0


class UserContext:
    def __init__(self, user_id: str, email: str, tier: str = "free"):
        self.user_id = user_id
        self.email = email
        self.tier = tier

    def has_tier(self, min_tier: str) -> bool:
        return _tier_rank(self.tier) >= _tier_rank(min_tier)

    def limit(self, key: str):
        return TIER_LIMITS.get(self.tier, TIER_LIMITS["free"])[key]


ANONYMOUS = UserContext(user_id="", email="", tier="free")


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Optional[AsyncIOMotorDatabase] = None,
) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        return ANONYMOUS

    token = authorization.removeprefix("Bearer ").strip()
    secret = _get_jwt_secret()
    if not secret:
        return ANONYMOUS

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub", "")
    email = payload.get("email", "")
    tier = "free"

    if db is not None and user_id:
        sub = await db["user_subscriptions"].find_one({"user_id": user_id})
        if sub:
            valid_until = sub.get("valid_until")
            if valid_until is None or valid_until > datetime.now(timezone.utc):
                tier = sub.get("tier", "free")

    return UserContext(user_id=user_id, email=email, tier=tier)


def require_tier(min_tier: str):
    """FastAPI dependency — raises 403 if user tier is below min_tier."""
    async def _check(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_tier(min_tier):
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires the {min_tier.title()} plan or above.",
            )
        return user
    return _check
