# Junior FC Store

A demo fan-store site for "Junior FC" — a single-page storefront with cart, wishlist,
CMS-driven product/category content, and Cognito-based sign-in. Static HTML/CSS/JS,
served from S3 through CloudFront.

> Educational/demo project. Not affiliated with any real club or brand.

## Live pages

| File            | Role                                                             |
|-----------------|-------------------------------------------------------------------|
| `login.html`    | Entry point for auth. Generates the PKCE `code_verifier` and starts the Cognito Hosted UI flow. **Only this page may start a login flow.** |
| `callback.html` | Cognito Hosted UI redirect target. Exchanges the auth code for tokens (PKCE) and stores `id_token`/`access_token` in `sessionStorage`. |
| `junior-fc.html`| The storefront itself — product grid, categories, filters/search, cart drawer, wishlist, membership/newsletter sections, GA4 ecommerce tracking, and the signed-in header state. |
| `junior.html`   | Legacy 2.8&nbsp;MB scrape of the original adidas-style page, kept only as a rollback reference — **not meant to be deployed or `s3 sync`'d**. |

## Auth flow

```
login.html  →  Cognito Hosted UI  →  callback.html  →  junior-fc.html
(PKCE start)                          (token exchange)   (post-login landing)
```

- `login.html` creates the PKCE `code_verifier`, stashes the intended return path in
  `sessionStorage.post_login`, and redirects to the Cognito Hosted UI.
- `callback.html` is the **only** registered redirect URI on the Cognito app client. It
  performs the code→token exchange and stores `id_token` before redirecting onward.
- Because the `code_verifier` only ever lives in `login.html`'s session, no other page can
  start its own Hosted UI flow — anything needing auth must hand off to `/login.html`.
- Pages read the `id_token` claims (e.g. email) for **display only**. A static site can't
  verify a JWT signature against the pool's JWKS, so nothing here uses the token for real
  access control.

## Content

Product, category, hero-banner, and promo-bar copy come from **Contentful** (Content
Delivery API, no SDK — plain `fetch` calls in `junior-fc.html`). If Contentful isn't
configured, the page falls back to a small hard-coded `FALLBACK` dataset so the storefront
is always fully functional. A yellow banner at the top of the page tells you which mode
you're in.

Content models: `product`, `category`, `heroBanner`, `promoBar` (field definitions are
documented inline in `junior-fc.html` above the `PALETTE` constant). Product photography is
resized on the fly through Contentful's Images API (`fit=pad`, so odd aspect ratios don't
get cropped).

Products with no photo yet render a generated SVG jersey instead, colored from a small
fixed palette (`red`/`white`/`black`/`blue`/`yellow`, English or Spanish) so a typo in
Contentful can't inject into the markup.

## Analytics

Google Analytics 4 (`gtag.js`), using the standard ecommerce event set: `view_item_list`,
`select_item`, `view_item`, `add_to_cart`, `remove_from_cart`, `add_to_wishlist` /
`remove_from_wishlist`, `view_cart`, `begin_checkout`, plus `search`, `generate_lead`
(newsletter), `select_promotion`, and scroll-depth milestones (25/50/75/90%). Every event
also logs to the console when `CONFIG.debugAnalytics` is `true`.

Checkout is a demo — `#checkoutBtn` fires `begin_checkout` and shows a toast; there's no
payment gateway wired up.

## Infrastructure (AWS)

- **S3**: bucket `adidas-junior-luisrro`, private, reachable only through CloudFront via
  Origin Access Control. No `index.html` — the three real pages are `login.html`,
  `callback.html`, `junior.html`/`junior-fc.html`.
- **CloudFront**: distribution serving the bucket, `DefaultRootObject` set to `login.html`.
  Cache policy is Managed-CachingOptimized — **every upload needs a cache invalidation**, or
  the old object keeps serving.
- **Cognito**: user pool with Hosted UI, app client configured for the Authorization Code +
  PKCE flow described above.

Deploys are targeted `aws s3 cp` uploads followed by a CloudFront invalidation — never a
full `s3 sync` from this folder, since it still contains the legacy `junior.html` backup.

## Status / next steps

This is currently a single hand-edited HTML file per page, no build step. A React rewrite
is under consideration — the plan is to keep `login.html` / `callback.html` as separate
static pages (so the Cognito app client's redirect URI doesn't need to change) and rebuild
`junior-fc.html`'s storefront as a component tree with the same state (cart, wishlist,
filters), the same Contentful fetch layer, and the same GA4 events.
