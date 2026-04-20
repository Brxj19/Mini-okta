"""Billing and subscription helpers for self-serve organization upgrades."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.branding import PRODUCT_NAME
from app.config import settings
from app.models.organization import Organization
from app.services.organization_service import build_self_serve_settings, build_verified_enterprise_settings

FREE_PLAN_CODE = "free"
LEGACY_ENTERPRISE_PLAN_CODE = "enterprise_manual"
PAID_PLAN_CODES = ("go", "plus", "pro")
SUPPORTED_PAYMENT_METHODS = {"upi", "card"}
PLAN_RANK = {
    FREE_PLAN_CODE: 0,
    "go": 1,
    "plus": 2,
    "pro": 3,
    LEGACY_ENTERPRISE_PLAN_CODE: 4,
}

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "free": {
        "code": "free",
        "name": "Free",
        "price_paise": 0,
        "currency": "INR",
        "description": f"Self-serve evaluation tier for trying {PRODUCT_NAME} before upgrade.",
        "limits": {"max_users": 5, "max_apps": 2},
        "features": [
            "Localhost development app integrations",
            "Starter user and app limits",
            "Core identity flows for evaluation",
        ],
        "badge": "Trial",
    },
    "go": {
        "code": "go",
        "name": "Go",
        "price_paise": 100,
        "currency": "INR",
        "description": "Small-team production access with a lightweight monthly subscription.",
        "limits": {"max_users": 25, "max_apps": 10},
        "features": [
            "Production access unlocked",
            "Higher user and app limits",
            "Admin management flows enabled",
        ],
        "badge": "Starter",
    },
    "plus": {
        "code": "plus",
        "name": "Plus",
        "price_paise": 300,
        "currency": "INR",
        "description": "Growing-team plan with room for more apps, users, and admin operations.",
        "limits": {"max_users": 100, "max_apps": 30},
        "features": [
            "Expanded organization limits",
            "More production applications",
            "Best fit for internship demo teams",
        ],
        "badge": "Popular",
    },
    "pro": {
        "code": "pro",
        "name": "Pro",
        "price_paise": 500,
        "currency": "INR",
        "description": "Full-access plan for unrestricted production demos and larger organizations.",
        "limits": {},
        "features": [
            "Highest limits in this demo",
            "Advanced admin capabilities enabled",
            "Best showcase plan for complete access",
        ],
        "badge": "Full Access",
    },
    LEGACY_ENTERPRISE_PLAN_CODE: {
        "code": LEGACY_ENTERPRISE_PLAN_CODE,
        "name": "Admin Provisioned",
        "price_paise": 0,
        "currency": "INR",
        "description": "Legacy enterprise access provisioned manually by the platform.",
        "limits": {},
        "features": [
            "Legacy manually-managed enterprise access",
        ],
        "badge": "Legacy",
        "hidden": True,
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _payment_provider() -> str:
    provider = str(settings.PAYMENTS_PROVIDER or "demo").strip().lower()
    return provider if provider in {"demo", "razorpay"} else "demo"


def _plan_rank(plan_code: str | None) -> int:
    normalized = str(plan_code or "").strip().lower()
    return PLAN_RANK.get(normalized, 0)


def _get_notification_marks(billing: dict[str, Any]) -> dict[str, list[str]]:
    marks = billing.get("notification_marks") if isinstance(billing.get("notification_marks"), dict) else {}
    normalized: dict[str, list[str]] = {}
    for key, values in marks.items():
        if isinstance(values, list):
            normalized[str(key)] = [str(value) for value in values[:20]]
    return normalized


def _has_notification_mark(billing: dict[str, Any], event_key: str, cycle_key: str) -> bool:
    marks = _get_notification_marks(billing)
    return cycle_key in marks.get(event_key, [])


def _set_notification_mark(billing: dict[str, Any], event_key: str, cycle_key: str) -> None:
    marks = _get_notification_marks(billing)
    values = [value for value in marks.get(event_key, []) if value != cycle_key]
    values.append(cycle_key)
    marks[event_key] = values[-12:]
    billing["notification_marks"] = marks


def get_billing_provider_info() -> dict[str, Any]:
    provider = _payment_provider()
    gateway_ready = provider == "demo" or bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
    return {
        "provider": provider,
        "gateway_ready": gateway_ready,
        "supports_live_checkout": provider == "razorpay" and gateway_ready,
    }


def get_plan_definition(plan_code: str) -> dict[str, Any]:
    normalized = str(plan_code or "").strip().lower()
    if normalized not in PLAN_CATALOG:
        raise ValueError("Unknown plan selected.")
    return deepcopy(PLAN_CATALOG[normalized])


def serialize_plan(plan_code: str) -> dict[str, Any]:
    plan = get_plan_definition(plan_code)
    cycle_days = settings.SUBSCRIPTION_CYCLE_DAYS
    return {
        "code": plan["code"],
        "name": plan["name"],
        "badge": plan.get("badge"),
        "description": plan["description"],
        "price_paise": int(plan["price_paise"]),
        "price_inr": int(plan["price_paise"]) / 100,
        "price_display": "Free" if int(plan["price_paise"]) == 0 else f"Rs {int(plan['price_paise']) / 100:.0f}",
        "currency": plan.get("currency") or settings.BILLING_CURRENCY,
        "cycle_days": cycle_days,
        "interval_label": f"Every {cycle_days} days",
        "limits": deepcopy(plan.get("limits") or {}),
        "features": list(plan.get("features") or []),
        "hidden": bool(plan.get("hidden", False)),
    }


def get_visible_plan_catalog() -> list[dict[str, Any]]:
    return [serialize_plan(code) for code in ("free", "go", "plus", "pro")]


def ensure_billing_state(raw_settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(raw_settings, dict):
        payload.update(deepcopy(raw_settings))

    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    billing = deepcopy(billing)
    payments = billing.get("payments") if isinstance(billing.get("payments"), list) else []
    subscription = billing.get("subscription") if isinstance(billing.get("subscription"), dict) else None
    current_plan_code = str(
        billing.get("current_plan_code")
        or (subscription or {}).get("plan_code")
        or ""
    ).strip().lower()

    access_tier = str(payload.get("access_tier") or "verified_enterprise")
    if not current_plan_code:
        current_plan_code = FREE_PLAN_CODE if access_tier == "limited" else LEGACY_ENTERPRISE_PLAN_CODE

    if current_plan_code not in PLAN_CATALOG:
        current_plan_code = FREE_PLAN_CODE if access_tier == "limited" else LEGACY_ENTERPRISE_PLAN_CODE

    if current_plan_code == LEGACY_ENTERPRISE_PLAN_CODE and not subscription:
        subscription = {
            "plan_code": LEGACY_ENTERPRISE_PLAN_CODE,
            "plan_name": PLAN_CATALOG[LEGACY_ENTERPRISE_PLAN_CODE]["name"],
            "status": "active",
            "managed_manually": True,
            "cancel_at_period_end": False,
            "current_period_start": None,
            "current_period_end": None,
        }

    billing.update(
        {
            "provider": str(billing.get("provider") or _payment_provider()),
            "current_plan_code": current_plan_code,
            "payments": payments[-25:],
            "subscription": subscription,
        }
    )
    payload["billing"] = billing
    return payload


def _append_payment_record(billing: dict[str, Any], payment_record: dict[str, Any]) -> None:
    payments = billing.get("payments") if isinstance(billing.get("payments"), list) else []
    payments.append(payment_record)
    billing["payments"] = payments[-25:]


def _clear_pending_checkout(billing: dict[str, Any]) -> None:
    billing.pop("pending_checkout", None)


def _build_active_subscription(plan_code: str, payment_record: dict[str, Any], now: datetime) -> dict[str, Any]:
    plan = get_plan_definition(plan_code)
    cycle_days = settings.SUBSCRIPTION_CYCLE_DAYS
    return {
        "plan_code": plan_code,
        "plan_name": plan["name"],
        "status": "active",
        "managed_manually": False,
        "cancel_at_period_end": False,
        "started_at": now.isoformat(),
        "current_period_start": now.isoformat(),
        "current_period_end": (now + timedelta(days=cycle_days)).isoformat(),
        "renewal_interval_days": cycle_days,
        "payment_method": payment_record.get("payment_method"),
        "provider": payment_record.get("provider"),
        "last_payment_id": payment_record.get("payment_id"),
        "last_payment_at": payment_record.get("paid_at"),
        "amount_paise": int(payment_record.get("amount_paise") or plan["price_paise"]),
        "currency": payment_record.get("currency") or plan.get("currency") or settings.BILLING_CURRENCY,
    }


def apply_successful_plan_payment(
    raw_settings: Optional[dict[str, Any]],
    *,
    plan_code: str,
    payment_record: dict[str, Any],
) -> dict[str, Any]:
    normalized_plan = str(plan_code or "").strip().lower()
    if normalized_plan not in PAID_PLAN_CODES:
        raise ValueError("Only paid plans can be activated through checkout.")

    plan = get_plan_definition(normalized_plan)
    payload = ensure_billing_state(raw_settings)
    payload = build_verified_enterprise_settings(payload)
    payload["limits"] = deepcopy(plan.get("limits") or {})
    payload["verification_status"] = "approved"
    payload.pop("upgrade_request", None)

    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    billing = deepcopy(billing)
    now = _utcnow()
    payment_entry = {
        "payment_id": payment_record["payment_id"],
        "provider": payment_record["provider"],
        "status": "paid",
        "amount_paise": int(payment_record.get("amount_paise") or plan["price_paise"]),
        "currency": payment_record.get("currency") or plan.get("currency") or settings.BILLING_CURRENCY,
        "plan_code": normalized_plan,
        "plan_name": plan["name"],
        "payment_method": payment_record.get("payment_method") or "upi",
        "paid_at": payment_record.get("paid_at") or now.isoformat(),
        "reference": payment_record.get("reference"),
        "notes": payment_record.get("notes"),
    }
    _append_payment_record(billing, payment_entry)
    billing["provider"] = payment_record.get("provider") or billing.get("provider") or _payment_provider()
    billing["current_plan_code"] = normalized_plan
    billing["last_paid_plan_code"] = normalized_plan
    billing["subscription"] = _build_active_subscription(normalized_plan, payment_entry, now)
    _clear_pending_checkout(billing)
    payload["billing"] = billing
    return payload


def reconcile_subscription_status(raw_settings: Optional[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    payload = ensure_billing_state(raw_settings)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    subscription = billing.get("subscription") if isinstance(billing.get("subscription"), dict) else None
    if not subscription:
        return payload, False

    if str(subscription.get("plan_code")) not in PAID_PLAN_CODES:
        return payload, False

    period_end = _parse_iso(subscription.get("current_period_end"))
    if not period_end or period_end > _utcnow():
        return payload, False

    expired_subscription = deepcopy(subscription)
    expired_subscription["status"] = "expired"
    expired_subscription["expired_at"] = _utcnow().isoformat()
    billing["subscription"] = expired_subscription
    billing["current_plan_code"] = FREE_PLAN_CODE
    billing["last_paid_plan_code"] = str(subscription.get("plan_code"))
    payload = build_self_serve_settings(payload)
    payload["verification_status"] = "payment_due"
    payload["billing"] = billing
    return payload, True


async def process_subscription_lifecycle_notifications(db, org: Organization) -> dict[str, bool]:
    """Send plan lifecycle reminders/expiry notices for one organization."""
    from app.services.audit_service import write_audit_event
    from app.services.notification_service import send_org_admin_notification

    now = _utcnow()
    settings_payload = ensure_billing_state(org.settings)
    billing = settings_payload.get("billing") if isinstance(settings_payload.get("billing"), dict) else {}
    subscription = billing.get("subscription") if isinstance(billing.get("subscription"), dict) else None
    result = {"renewal_reminder": False, "cancel_reminder": False, "expired": False, "updated": False}

    if not subscription or str(subscription.get("plan_code")) not in PAID_PLAN_CODES:
        return result

    period_end = _parse_iso(subscription.get("current_period_end"))
    if not period_end:
        return result

    cycle_key = period_end.date().isoformat()
    seconds_remaining = (period_end - now).total_seconds()
    if seconds_remaining <= 0 and str(subscription.get("status")) == "active":
        updated_settings, changed = reconcile_subscription_status(settings_payload)
        if changed:
            org.settings = updated_settings
            org.updated_at = now
            await send_org_admin_notification(
                db=db,
                org_id=org.id,
                title="Subscription expired and plan downgraded",
                message=f"Your organization's paid plan has ended, so access has been moved back to the free self-serve tier.",
                event_key="billing.subscription_expired",
            )
            await write_audit_event(
                db,
                "org.subscription.expired",
                "organization",
                str(org.id),
                org_id=org.id,
                actor_id=None,
                metadata={"org_name": org.display_name or org.name, "previous_plan": subscription.get("plan_name")},
            )
            result["expired"] = True
            result["updated"] = True
        return result

    days_remaining = seconds_remaining / 86400
    if days_remaining <= 3 and not _has_notification_mark(billing, "billing.renewal_reminder", cycle_key):
        await send_org_admin_notification(
            db=db,
            org_id=org.id,
            title="Subscription renewal reminder",
            message=f"Your {subscription.get('plan_name', 'paid')} plan will renew or expire on {period_end.strftime('%b %d, %Y %H:%M %Z')}. Review billing before the cycle ends.",
            event_key="billing.renewal_reminder",
        )
        _set_notification_mark(billing, "billing.renewal_reminder", cycle_key)
        result["renewal_reminder"] = True
        result["updated"] = True

    if (
        bool(subscription.get("cancel_at_period_end"))
        and days_remaining <= 1
        and not _has_notification_mark(billing, "billing.cancel_reminder", cycle_key)
    ):
        await send_org_admin_notification(
            db=db,
            org_id=org.id,
            title="Subscription cancellation reminder",
            message=f"Your subscription is set to end when the current cycle closes on {period_end.strftime('%b %d, %Y %H:%M %Z')}. Resume it before then if you want to avoid downgrade.",
            event_key="billing.cancel_reminder",
        )
        _set_notification_mark(billing, "billing.cancel_reminder", cycle_key)
        result["cancel_reminder"] = True
        result["updated"] = True

    if result["updated"]:
        settings_payload["billing"] = billing
        org.settings = settings_payload
        org.updated_at = now
    return result


def mark_cancel_at_period_end(raw_settings: Optional[dict[str, Any]], *, cancel: bool) -> dict[str, Any]:
    payload = ensure_billing_state(raw_settings)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    subscription = billing.get("subscription") if isinstance(billing.get("subscription"), dict) else None
    if not subscription or str(subscription.get("plan_code")) not in PAID_PLAN_CODES:
        raise ValueError("No active paid subscription is available to manage.")
    if str(subscription.get("status")) != "active":
        raise ValueError("Only active subscriptions can be updated.")

    subscription = deepcopy(subscription)
    subscription["cancel_at_period_end"] = bool(cancel)
    billing["subscription"] = subscription
    payload["billing"] = billing
    return payload


def build_plan_status_payload(org: Organization) -> dict[str, Any]:
    settings_payload, _ = reconcile_subscription_status(org.settings)
    org.settings = settings_payload
    billing = settings_payload.get("billing") if isinstance(settings_payload.get("billing"), dict) else {}
    current_plan_code = str(billing.get("current_plan_code") or FREE_PLAN_CODE)
    active_provider = get_billing_provider_info()["provider"]
    subscription = deepcopy(billing.get("subscription")) if isinstance(billing.get("subscription"), dict) else None
    renewal_available = False
    renewal_available_at = None
    if subscription and str(subscription.get("plan_code")) in PAID_PLAN_CODES:
        renewal_available_at = subscription.get("current_period_end")
        period_end = _parse_iso(subscription.get("current_period_end"))
        if str(subscription.get("status")) != "active":
            renewal_available = True
        elif period_end and period_end <= _utcnow():
            renewal_available = True

    return {
        "org_id": org.id,
        "org_name": org.display_name or org.name,
        "org_slug": org.slug,
        "access_tier": str(settings_payload.get("access_tier") or "verified_enterprise"),
        "verification_status": str(settings_payload.get("verification_status") or "approved"),
        "limits": deepcopy(settings_payload.get("limits") or {}),
        "upgrade_request": settings_payload.get("upgrade_request") if isinstance(settings_payload.get("upgrade_request"), dict) else None,
        "current_plan_code": current_plan_code,
        "current_plan": serialize_plan(current_plan_code),
        "available_plans": get_visible_plan_catalog(),
        "billing_provider": active_provider,
        "gateway_ready": bool(get_billing_provider_info()["gateway_ready"]),
        "subscription": subscription,
        "payments": deepcopy(billing.get("payments") or []),
        "last_paid_plan_code": billing.get("last_paid_plan_code"),
        "current_plan_rank": _plan_rank(current_plan_code),
        "renewal_available": renewal_available,
        "renewal_available_at": renewal_available_at,
    }


def _validate_checkout_request(plan_code: str, payment_method: str) -> tuple[dict[str, Any], str]:
    normalized_plan = str(plan_code or "").strip().lower()
    if normalized_plan not in PAID_PLAN_CODES:
        raise ValueError("Please select Go, Plus, or Pro.")
    normalized_method = str(payment_method or "upi").strip().lower()
    if normalized_method not in SUPPORTED_PAYMENT_METHODS:
        raise ValueError("Payment method must be UPI or card.")
    return get_plan_definition(normalized_plan), normalized_method


def _new_checkout_session(
    raw_settings: Optional[dict[str, Any]],
    *,
    plan_code: str,
    payment_method: str,
    provider: str,
    metadata: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan, normalized_method = _validate_checkout_request(plan_code, payment_method)
    payload = ensure_billing_state(raw_settings)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    billing = deepcopy(billing)
    subscription = billing.get("subscription") if isinstance(billing.get("subscription"), dict) else None
    now = _utcnow()
    if (
        subscription
        and str(subscription.get("status")) == "active"
        and str(subscription.get("plan_code")) == plan["code"]
    ):
        period_end = _parse_iso(subscription.get("current_period_end"))
        if period_end and period_end > now:
            raise ValueError("Renewal becomes available only after the current billing period ends.")
    billing["provider"] = provider
    pending_checkout = {
        "session_id": secrets.token_urlsafe(18),
        "provider": provider,
        "plan_code": plan["code"],
        "payment_method": normalized_method,
        "amount_paise": int(plan["price_paise"]),
        "currency": plan.get("currency") or settings.BILLING_CURRENCY,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=20)).isoformat(),
    }
    if metadata:
        pending_checkout.update(metadata)
    billing["pending_checkout"] = pending_checkout
    payload["billing"] = billing
    return payload, pending_checkout


def start_demo_checkout(
    raw_settings: Optional[dict[str, Any]],
    *,
    plan_code: str,
    payment_method: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, pending_checkout = _new_checkout_session(
        raw_settings,
        plan_code=plan_code,
        payment_method=payment_method,
        provider="demo",
    )
    return payload, {
        "provider": "demo",
        "session_id": pending_checkout["session_id"],
        "amount_paise": pending_checkout["amount_paise"],
        "currency": pending_checkout["currency"],
        "plan_code": pending_checkout["plan_code"],
        "payment_method": pending_checkout["payment_method"],
        "mode": "embedded_demo",
    }


def complete_demo_checkout(
    raw_settings: Optional[dict[str, Any]],
    *,
    session_id: str,
    payment_method: str,
) -> dict[str, Any]:
    payload = ensure_billing_state(raw_settings)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    pending_checkout = billing.get("pending_checkout") if isinstance(billing.get("pending_checkout"), dict) else None
    if not pending_checkout or pending_checkout.get("provider") != "demo":
        raise ValueError("No demo checkout is currently pending.")
    if str(pending_checkout.get("session_id")) != str(session_id):
        raise ValueError("Checkout session does not match the pending payment.")

    expires_at = _parse_iso(pending_checkout.get("expires_at"))
    if expires_at and expires_at <= _utcnow():
        raise ValueError("The pending checkout session has expired. Please start again.")

    normalized_method = str(payment_method or pending_checkout.get("payment_method") or "upi").strip().lower()
    if normalized_method not in SUPPORTED_PAYMENT_METHODS:
        raise ValueError("Payment method must be UPI or card.")

    payment_record = {
        "payment_id": f"demo_pay_{secrets.token_hex(6)}",
        "provider": "demo",
        "amount_paise": int(pending_checkout.get("amount_paise") or 0),
        "currency": pending_checkout.get("currency") or settings.BILLING_CURRENCY,
        "payment_method": normalized_method,
        "paid_at": _utcnow().isoformat(),
        "reference": pending_checkout.get("session_id"),
        "notes": f"Demo payment confirmed inside {PRODUCT_NAME}.",
    }
    return apply_successful_plan_payment(
        payload,
        plan_code=str(pending_checkout.get("plan_code")),
        payment_record=payment_record,
    )


async def start_razorpay_checkout(
    raw_settings: Optional[dict[str, Any]],
    *,
    org: Organization,
    plan_code: str,
    payment_method: str,
    actor_email: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    provider_info = get_billing_provider_info()
    if not provider_info["gateway_ready"]:
        raise ValueError("Razorpay is not configured yet. Add API keys or switch to demo mode.")

    payload, pending_checkout = _new_checkout_session(
        raw_settings,
        plan_code=plan_code,
        payment_method=payment_method,
        provider="razorpay",
    )
    receipt = f"{org.slug[:10]}-{pending_checkout['session_id'][:10]}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            json={
                "amount": int(pending_checkout["amount_paise"]),
                "currency": pending_checkout["currency"],
                "receipt": receipt,
                "notes": {
                    "org_id": str(org.id),
                    "org_slug": org.slug,
                    "plan_code": plan_code,
                    "checkout_session_id": pending_checkout["session_id"],
                },
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"Unable to create Razorpay order: {exc}") from exc
        order_payload = response.json()

    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    pending_checkout["razorpay_order_id"] = order_payload["id"]
    billing["pending_checkout"] = pending_checkout
    payload["billing"] = billing

    plan = get_plan_definition(plan_code)
    return payload, {
        "provider": "razorpay",
        "mode": "razorpay_checkout",
        "session_id": pending_checkout["session_id"],
        "order_id": order_payload["id"],
        "amount_paise": int(order_payload["amount"]),
        "currency": order_payload["currency"],
        "plan_code": plan_code,
        "payment_method": payment_method,
        "key_id": settings.RAZORPAY_KEY_ID,
        "merchant_name": PRODUCT_NAME,
        "description": f"{plan['name']} subscription for {org.display_name or org.name}",
        "prefill": {
            "email": actor_email or "",
        },
        "theme": {
            "color": "#111111",
        },
    }


def complete_razorpay_checkout(
    raw_settings: Optional[dict[str, Any]],
    *,
    session_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    payment_method: str,
) -> dict[str, Any]:
    if not settings.RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay secret is not configured.")

    payload = ensure_billing_state(raw_settings)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    pending_checkout = billing.get("pending_checkout") if isinstance(billing.get("pending_checkout"), dict) else None
    if not pending_checkout or pending_checkout.get("provider") != "razorpay":
        raise ValueError("No Razorpay checkout is currently pending.")
    if str(pending_checkout.get("session_id")) != str(session_id):
        raise ValueError("Checkout session does not match the pending payment.")
    if str(pending_checkout.get("razorpay_order_id")) != str(razorpay_order_id):
        raise ValueError("Razorpay order does not match the pending checkout.")

    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, str(razorpay_signature or "")):
        raise ValueError("Payment signature verification failed.")

    normalized_method = str(payment_method or pending_checkout.get("payment_method") or "upi").strip().lower()
    if normalized_method not in SUPPORTED_PAYMENT_METHODS:
        normalized_method = "upi"

    payment_record = {
        "payment_id": razorpay_payment_id,
        "provider": "razorpay",
        "amount_paise": int(pending_checkout.get("amount_paise") or 0),
        "currency": pending_checkout.get("currency") or settings.BILLING_CURRENCY,
        "payment_method": normalized_method,
        "paid_at": _utcnow().isoformat(),
        "reference": razorpay_order_id,
        "notes": "Razorpay checkout verified successfully.",
    }
    return apply_successful_plan_payment(
        payload,
        plan_code=str(pending_checkout.get("plan_code")),
        payment_record=payment_record,
    )
