/**
 * Step 2 (frontend) — LCP / TTI-proxy for the landing and chat pages, measured with
 * Playwright's performance APIs, across CPU tiers to back the MINIMUM-SPEC claim.
 *
 * For each page we capture First Contentful Paint, Largest Contentful Paint, and
 * domInteractive (a Time-to-Interactive proxy for a single-page React app) at three
 * CPU-throttle rates via CDP Emulation.setCPUThrottlingRate:
 *   1x = modern desktop/high-end phone, 4x ≈ mid/low-end Android, 6x ≈ very low-end.
 *
 *   cd testing && node performance/lcp_tti.mjs
 * Output: performance/results/web_vitals.md (+ .json)
 */
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const FRONTEND = process.env.FRONTEND_URL || 'https://srh-frontend.vercel.app'
const OUT = path.join(process.cwd(), 'performance', 'results')
fs.mkdirSync(OUT, { recursive: true })

const PAGES = [
  { name: 'landing', url: `${FRONTEND}/` },
  { name: 'chat', url: `${FRONTEND}/chat` },
]
const CPU_RATES = [1, 4, 6]

async function measure(browser, url, rate) {
  const context = await browser.newContext()
  const page = await context.newPage()
  const client = await context.newCDPSession(page)
  await client.send('Emulation.setCPUThrottlingRate', { rate })
  await page.addInitScript(() => {
    window.__lcp = 0
    try {
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) window.__lcp = e.startTime
      }).observe({ type: 'largest-contentful-paint', buffered: true })
    } catch { /* older engines */ }
  })
  await page.goto(url, { waitUntil: 'load', timeout: 120_000 })
  await page.waitForTimeout(2000) // let LCP settle
  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {}
    const fcp = (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || null
    return {
      fcp_ms: fcp ? Math.round(fcp) : null,
      lcp_ms: window.__lcp ? Math.round(window.__lcp) : null,
      domInteractive_ms: nav.domInteractive ? Math.round(nav.domInteractive) : null,
      load_ms: nav.loadEventEnd ? Math.round(nav.loadEventEnd) : null,
    }
  })
  await context.close()
  return m
}

;(async () => {
  const browser = await chromium.launch()
  const results = []
  for (const pg of PAGES) {
    for (const rate of CPU_RATES) {
      process.stdout.write(`${pg.name} @ ${rate}x CPU ... `)
      const m = await measure(browser, pg.url, rate)
      console.log(`FCP=${m.fcp_ms} LCP=${m.lcp_ms} TTI~=${m.domInteractive_ms}`)
      results.push({ page: pg.name, cpu_rate: rate, ...m })
    }
  }
  await browser.close()

  fs.writeFileSync(path.join(OUT, 'web_vitals.json'), JSON.stringify(results, null, 2))
  const md = [
    '# Step 2 (frontend) — Web vitals across CPU tiers', '',
    `Target: \`${FRONTEND}\`. LCP + FCP + domInteractive (TTI proxy), Playwright perf APIs.`,
    '', '**Budgets (pre-declared):** LCP ≤ 2.5 s (good) on 1x; ≤ 4 s on 4x (low-end). '
    + 'TTI-proxy ≤ 5 s on low-end.', '',
    '| page | CPU | FCP | LCP | TTI~ (domInteractive) | load |',
    '|---|---|---|---|---|---|',
    ...results.map((r) => `| ${r.page} | ${r.cpu_rate}x | ${fmt(r.fcp_ms)} | ${fmt(r.lcp_ms)} `
      + `| ${fmt(r.domInteractive_ms)} | ${fmt(r.load_ms)} |`),
    '', '_1x = modern device · 4x ≈ mid/low-end Android · 6x ≈ very low-end._',
  ]
  fs.writeFileSync(path.join(OUT, 'web_vitals.md'), md.join('\n'))
  console.log(`Wrote ${path.join(OUT, 'web_vitals.md')}`)
})()

function fmt(ms) { return ms == null ? '—' : (ms / 1000).toFixed(2) + ' s' }
