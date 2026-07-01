# HEXFIELD · Supabase setup

Everything the live site needs on Supabase: the 4 tables (the "remember"
feature) and the $1 Stripe checkout (edge function). Free tier, $0/month.

## What's here
- `migrations/20260701000000_hexfield_init.sql` — tables + RLS (anon read/append,
  update score on `logo_seeds`). No PII.
- `functions/stripe/index.ts` — `$1` Stripe checkout + payment verification.

## 1. Apply the database migration
Dashboard (easiest): **SQL Editor → paste the contents of the migration file → Run.**
Or CLI:
```bash
supabase link --project-ref <your-ref>
supabase db push
```

## 2. Deploy the Stripe function (MUST disable JWT so the browser can call it)
```bash
supabase functions deploy stripe --no-verify-jwt
supabase secrets set STRIPE_SECRET_KEY=sk_test_xxx   # your Stripe secret key
```
- Use your **sk_test_…** key first (test card `4242 4242 4242 4242`, any future
  date + any CVC). Swap to **sk_live_…** for real money.
- The secret lives only in Supabase — never in this repo or the client.

## 3. Wire the site (values are public-safe)
In `docs/index.html`, the top config script sets these (anon key is RLS-protected,
safe in a static file):
```js
window.MH_SUPABASE_URL      = 'https://<your-ref>.supabase.co';
window.MH_SUPABASE_ANON_KEY = '<your anon / publishable key>';
window.MH_BACKEND_URL       = 'https://<your-ref>.supabase.co/functions/v1/stripe';
```
The client calls `${MH_BACKEND_URL}/api/create-checkout-session` and
`/api/verify-payment`; the function matches on the path suffix, so the `/api/`
prefix is harmless.

## Verify
- DB: load the site's **Logo** tool → a row appears in `logo_seeds` (`select count(*)`).
- Pay (test): click **INSERT $1** → Stripe test Checkout → pay `4242…` → returns
  with `?colour_session=…` → the page flips B&W → colour and the red clock starts.

## Note on the paywall
The colour unlock is client-side (`localStorage`), granted after `verify-payment`
confirms the session. Stripe genuinely charges the $1; the B&W→colour flip is a
cosmetic gag and isn't fraud-proof (a technical user could fake the unlock).
Fine for a $1 novelty.
