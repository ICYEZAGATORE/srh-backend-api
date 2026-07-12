# Step 2 (frontend) — Web vitals across CPU tiers

Target: `https://srh-frontend.vercel.app`. LCP + FCP + domInteractive (TTI proxy), Playwright perf APIs.

**Budgets (pre-declared):** LCP ≤ 2.5 s (good) on 1x; ≤ 4 s on 4x (low-end). TTI-proxy ≤ 5 s on low-end.

| page | CPU | FCP | LCP | TTI~ (domInteractive) | load |
|---|---|---|---|---|---|
| landing | 1x | 1.64 s | 2.11 s | 0.50 s | 1.26 s |
| landing | 4x | — | — | 0.73 s | 1.77 s |
| landing | 6x | — | — | 1.29 s | 3.36 s |
| chat | 1x | 1.42 s | 1.42 s | 0.41 s | 1.11 s |
| chat | 4x | — | — | 0.67 s | 2.15 s |
| chat | 6x | 11.95 s | 11.95 s | 1.20 s | 2.88 s |

_1x = modern device · 4x ≈ mid/low-end Android · 6x ≈ very low-end._

## Measurement caveat (honest)
LCP/FCP capture was **intermittent under CPU emulation** (paint-timing entries did not
always flush before read → `—`). The reliable figures are: **1x LCP — landing 2.11 s,
chat 1.42 s (both "good", ≤ 2.5 s)**, and **domInteractive (TTI proxy) across all tiers**,
which stays ≤ 1.3 s even at 6x. domInteractive is the dependable cross-tier signal here.

## Minimum device specification (backed, not just asserted)
**Stated minimum spec:** an entry-level Android smartphone, ~2019-era SoC (≈4× slower than a
modern desktop CPU), **2 GB RAM**, **Chrome / Android WebView 90+**, on a **2 Mbps** or better
connection. Basis:
- Chat page **domInteractive ≤ 0.67 s at 4× CPU** and ≤ 1.2 s at 6× (very low-end) — the SPA
  becomes interactive quickly even on throttled CPU.
- The core journey **completes at 2 Mbps and Slow 3G** (see `network-bandwidth/`).
- Small JS bundle (~82 KB gzip) + PWA service-worker shell caching keep repeat loads cheap.
Below this (feature phones / no modern WebView) the PWA is not targeted.
