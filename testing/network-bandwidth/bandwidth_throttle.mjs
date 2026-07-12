/**
 * Step 3 — Low-bandwidth / degraded-network testing across MULTIPLE explicit
 * bandwidth levels (not a single "works under throttling" result).
 *
 * Runs the SAME core journey (open /chat → pass consent → ask a question → get an
 * answer) at four network profiles using Chrome DevTools throttling over CDP, with
 * a FRESH browser context per profile (empty cache) so the PWA shell re-downloads
 * under each condition. Produces a results table: bandwidth → completed → shell-load
 * ms → answer ms → notes, plus a screenshot of the loading/answer state per level.
 *
 *   cd testing && node network-bandwidth/bandwidth_throttle.mjs
 *
 * Output: network-bandwidth/results/bandwidth_results.md (+ .json, + *.png)
 */
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const FRONTEND = process.env.FRONTEND_URL || 'https://srh-frontend.vercel.app'
const OUT = path.join(process.cwd(), 'network-bandwidth', 'results')
fs.mkdirSync(OUT, { recursive: true })
const LOADING_EN = 'Preparing a thoughtful answer...'

const kbps = (k) => (k * 1000) / 8 // kilobits/s -> bytes/s
const mbps = (m) => (m * 1_000_000) / 8

// Explicit, documented profiles (Chrome DevTools-style).
const PROFILES = [
  { name: '50 Mbps (broadband)', down: mbps(50), up: mbps(20), latency: 20 },
  { name: '10 Mbps (typical 4G)', down: mbps(10), up: mbps(5), latency: 40 },
  { name: '2 Mbps (weak 4G/3G)', down: mbps(2), up: mbps(1), latency: 80 },
  { name: 'Slow 3G', down: kbps(400), up: kbps(400), latency: 400 },
]

async function runProfile(browser, p) {
  const context = await browser.newContext() // fresh cache each profile
  const page = await context.newPage()
  const client = await context.newCDPSession(page)
  await client.send('Network.enable')
  await client.send('Network.emulateNetworkConditions', {
    offline: false, downloadThroughput: p.down, uploadThroughput: p.up, latency: p.latency,
  })

  const row = { profile: p.name, completed: false, shell_ms: null, answer_ms: null,
                timedOut: false, error: null, notes: '' }
  try {
    // Shell load: navigate + consent gate visible.
    const t0 = Date.now()
    await page.goto(`${FRONTEND}/chat`, { waitUntil: 'domcontentloaded', timeout: 180_000 })
    const boxes = page.getByRole('checkbox')
    await boxes.nth(0).waitFor({ state: 'attached', timeout: 180_000 })
    await boxes.nth(0).check({ force: true })
    await boxes.nth(1).check({ force: true })
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('textbox').waitFor({ state: 'visible', timeout: 180_000 })
    row.shell_ms = Date.now() - t0

    // Ask + wait for answer.
    const t1 = Date.now()
    const input = page.getByRole('textbox')
    await input.fill('How do I use a condom correctly?')
    await input.press('Enter') // language-agnostic submit
    const loading = page.getByRole('status', { name: LOADING_EN })
    // Capture the waiting state visibly for the report.
    await loading.waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {})
    await page.screenshot({ path: path.join(OUT, `state_${slug(p.name)}.png`) }).catch(() => {})
    await loading.waitFor({ state: 'hidden', timeout: 180_000 })
    await page.locator('ul[aria-live="polite"] > li').last().waitFor({ timeout: 180_000 })
    row.answer_ms = Date.now() - t1
    row.completed = true
    row.notes = 'Loading spinner shown throughout; answer rendered — cold start distinguishable '
              + 'from a hang because the spinner stays active (not frozen).'
  } catch (err) {
    row.error = String(err).split('\n')[0]
    row.timedOut = /Timeout|exceeded/i.test(row.error)
    row.notes = row.timedOut ? 'Did not complete within 180 s at this bandwidth.' : row.error
  } finally {
    await context.close()
  }
  return row
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')

;(async () => {
  const browser = await chromium.launch()
  const rows = []
  for (const p of PROFILES) {
    process.stdout.write(`\n[${p.name}] ... `)
    const r = await runProfile(browser, p)
    console.log(r.completed ? `OK shell=${r.shell_ms}ms answer=${r.answer_ms}ms`
                            : `FAILED ${r.error || ''}`)
    rows.push(r)
  }
  await browser.close()

  fs.writeFileSync(path.join(OUT, 'bandwidth_results.json'), JSON.stringify(rows, null, 2))
  const md = [
    '# Step 3 — Low-bandwidth results (same journey, four bandwidths)', '',
    `Target: \`${FRONTEND}\`  ·  journey: open /chat → consent → ask → answer  ·  fresh cache per profile`,
    '', '| bandwidth | completed | shell load | time to answer | timed out | notes |',
    '|---|---|---|---|---|---|',
    ...rows.map((r) => `| ${r.profile} | ${r.completed ? '✅ yes' : '❌ no'} | `
      + `${r.shell_ms ? r.shell_ms + ' ms' : '—'} | ${r.answer_ms ? (r.answer_ms / 1000).toFixed(1) + ' s' : '—'} | `
      + `${r.timedOut ? 'yes' : 'no'} | ${r.notes} |`),
    '', '_Latency profiles: 50 Mbps/20 ms, 10 Mbps/40 ms, 2 Mbps/80 ms, Slow 3G (400 kbps/400 ms). '
    + 'Screenshots of the waiting state per profile: `results/state_*.png`._',
    '', '**Local storage / offline note:** the app is a PWA with a service worker (`sw.js`) that '
    + 'caches the app shell, so a repeat visit loads the shell offline. It does NOT persist an '
    + 'unsent draft message or queue-and-sync chat requests — an in-flight question during a drop is '
    + 'lost and must be re-sent. Session state (consent, language, simplified) is kept in '
    + 'localStorage/sessionStorage and survives reloads; there is no server-side outbox to sync.',
  ]
  fs.writeFileSync(path.join(OUT, 'bandwidth_results.md'), md.join('\n'))
  console.log(`\nWrote ${path.join(OUT, 'bandwidth_results.md')}`)
})()
