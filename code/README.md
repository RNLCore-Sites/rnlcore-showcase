# Code excerpts

Selected, lightly trimmed excerpts from the private RNLCore repositories. Model classes, database setup and imports are omitted.

| File | What it shows |
|---|---|
| [`policy_engine.py`](policy_engine.py) | The core of the control plane: device ID validation, the billing → entitlement → enforcement chain, and the fail-closed policy every router receives on check-in |
| [`stripe_webhook.py`](stripe_webhook.py) | Signature-verified, idempotent Stripe webhook that feeds the entitlement state machine |

The full codebase (FastAPI routes, Alembic migrations, pytest suite, admin and customer APIs, React portal) is available for review on request.
