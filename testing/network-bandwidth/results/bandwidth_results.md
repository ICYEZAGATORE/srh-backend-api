# Step 3 — Low-bandwidth results (same journey, four bandwidths)

Target: `https://srh-frontend.vercel.app`  ·  journey: open /chat → consent → ask → answer  ·  fresh cache per profile

| bandwidth | completed | shell load | time to answer | timed out | notes |
|---|---|---|---|---|---|
| 50 Mbps (broadband) | ✅ yes | 3347 ms | 1.1 s | no | Loading spinner shown throughout; answer rendered — cold start distinguishable from a hang because the spinner stays active (not frozen). |
| 10 Mbps (typical 4G) | ✅ yes | 3029 ms | 1.8 s | no | Loading spinner shown throughout; answer rendered — cold start distinguishable from a hang because the spinner stays active (not frozen). |
| 2 Mbps (weak 4G/3G) | ✅ yes | 3145 ms | 1.3 s | no | Loading spinner shown throughout; answer rendered — cold start distinguishable from a hang because the spinner stays active (not frozen). |
| Slow 3G | ✅ yes | 5051 ms | 2.5 s | no | Loading spinner shown throughout; answer rendered — cold start distinguishable from a hang because the spinner stays active (not frozen). |

_Latency profiles: 50 Mbps/20 ms, 10 Mbps/40 ms, 2 Mbps/80 ms, Slow 3G (400 kbps/400 ms). Screenshots of the waiting state per profile: `results/state_*.png`._

**Local storage / offline note:** the app is a PWA with a service worker (`sw.js`) that caches the app shell, so a repeat visit loads the shell offline. It does NOT persist an unsent draft message or queue-and-sync chat requests — an in-flight question during a drop is lost and must be re-sent. Session state (consent, language, simplified) is kept in localStorage/sessionStorage and survives reloads; there is no server-side outbox to sync.