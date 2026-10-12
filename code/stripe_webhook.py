# Excerpt from RNLCore Control-Plane (private repo): app/routes/stripe_routes.py
#
# Billing events only change network access through the entitlement state machine.
# The webhook refuses to run unconfigured, verifies Stripe's signature before trusting
# anything, and records each event ID so retries are applied only once.

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(status_code=501, detail="Stripe not configured")
    stripe.api_key = secret_key

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        raise HTTPException(status_code=501, detail="Stripe webhook secret not configured")

    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature or "", webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload")

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    event_obj = event.get("data", {}).get("object", {}) or {}

    # ... look up the account by Stripe customer, skip if this event ID was already
    # recorded (StripeEvent table), then map the event type to an entitlement state
    # (e.g. a cancelled subscription -> "locked_billing") and audit-log the change.
