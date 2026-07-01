// HEXFIELD $1 colour checkout — Supabase Edge Function (Deno).
// Ports backend/server.py's create_checkout_session + verify_payment to call
// the Stripe REST API directly (no python/pip). Deploy with verify_jwt = false
// so the browser can call it without a Supabase JWT.
//
//   POST  <fn>/api/create-checkout-session   { success_url, cancel_url } -> { checkout_url }
//   GET   <fn>/api/verify-payment?session_id=...                        -> { paid: boolean }
//
// The Stripe secret key is read from the STRIPE_SECRET_KEY function secret and
// never leaves the server. Set it with:  supabase secrets set STRIPE_SECRET_KEY=sk_...

const STRIPE_API = "https://api.stripe.com/v1";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });

// Stripe wants application/x-www-form-urlencoded with bracketed nested keys.
function form(params: Record<string, string>): string {
  return Object.entries(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });

  const key = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
  if (!key) return json({ error: "Stripe not configured. Set STRIPE_SECRET_KEY." }, 503);

  const url = new URL(req.url);
  const path = url.pathname;
  const auth = { Authorization: `Bearer ${key}` };

  try {
    // ── Create a $1 checkout session ──────────────────────────────────────
    if (req.method === "POST" && path.endsWith("create-checkout-session")) {
      const body = await req.json().catch(() => ({}));
      const success_url = body.success_url ?? url.origin;
      const cancel_url = body.cancel_url ?? url.origin;

      const r = await fetch(`${STRIPE_API}/checkout/sessions`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/x-www-form-urlencoded" },
        body: form({
          mode: "payment",
          "payment_method_types[0]": "card",
          success_url,
          cancel_url,
          "line_items[0][quantity]": "1",
          "line_items[0][price_data][currency]": "usd",
          "line_items[0][price_data][unit_amount]": "100",
          "line_items[0][price_data][product_data][name]": "Hexfield Colour Render — 60 seconds of colour",
        }),
      });
      const session = await r.json();
      if (!r.ok) return json({ error: session?.error?.message ?? "stripe error" }, 502);
      return json({ checkout_url: session.url });
    }

    // ── Verify a returning session actually paid ──────────────────────────
    if (req.method === "GET" && path.endsWith("verify-payment")) {
      const id = url.searchParams.get("session_id") ?? "";
      if (!id) return json({ paid: false });
      const r = await fetch(`${STRIPE_API}/checkout/sessions/${encodeURIComponent(id)}`, {
        headers: auth,
      });
      const session = await r.json();
      if (!r.ok) return json({ paid: false });
      return json({ paid: session.payment_status === "paid" });
    }

    return json({ error: "not found" }, 404);
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
