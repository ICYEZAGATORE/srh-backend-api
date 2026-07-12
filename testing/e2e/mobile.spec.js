import { test, expect } from '@playwright/test'
import { enterChat, ask, shot, record, flushEvidence } from './_helpers.js'

// Step 1 (mobile) — the proposal targets Android smartphones as the primary device
// (§3.4). Run with --project=mobile-android (Pixel 5 emulation) to confirm the
// mobile-first PWA layout works and a chat exchange completes on a phone viewport.
test.describe('Mobile (Android Pixel 5 emulation)', () => {
  test('mobile landing → consent → chat works', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /start a conversation/i }).first()).toBeVisible()
    await shot(page, 'mobile-01-landing')

    await enterChat(page)
    await shot(page, 'mobile-02-chat-ready')

    const ans = await ask(page, 'What changes happen during puberty?', { lang: 'en' })
    expect(ans.length).toBeGreaterThan(20)
    record({ device: 'Pixel 5', case: 'mobile_chat', pass: true, answer: ans.slice(0, 200) })
    await shot(page, 'mobile-03-answer')
    flushEvidence('mobile_evidence.json')
  })
})
