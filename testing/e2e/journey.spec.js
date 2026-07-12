import { test, expect } from '@playwright/test'
import { enterChat, ask, switchLanguage, shot, record, flushEvidence } from './_helpers.js'

// Step 1 (functional) + Step 7 (live deployment verification): one continuous
// journey against the REAL deployed app — land → consent → chat (EN) → switch
// language → chat (RW) — mirroring how a real user moves through the product.
test.describe('Continuous user journey (deployed)', () => {
  test('land → start chat → ask (EN) → switch to RW → ask again', async ({ page }) => {
    // 1. Landing page loads and reads as the product front page.
    await page.goto('/')
    await expect(page.getByRole('link', { name: /start a conversation/i }).first()).toBeVisible()
    await shot(page, '01-landing')

    // 2. Enter chat through the real consent gate.
    await page.getByRole('link', { name: /start a conversation/i }).first().click()
    await enterChat(page)
    await shot(page, '02-consent-passed-chat-ready')

    // 3. Ask an SRH question in English and get a real answer back.
    const a1 = await ask(page, 'How do I use a condom correctly?', { lang: 'en' })
    expect(a1.length).toBeGreaterThan(20)
    record({ step: 'chat_en', q: 'How do I use a condom correctly?', a: a1 })
    await shot(page, '03-answer-en')

    // 4. Switch language to Kinyarwanda via the header toggle.
    await switchLanguage(page, 'Kinyarwanda')
    await expect(page.getByRole('button', { name: 'English' }).first()).toBeVisible()
    await shot(page, '04-switched-rw')

    // 5. Ask again in Kinyarwanda and get an answer (retrieval routed to the RW index).
    const a2 = await ask(page, 'Ni gute nakoresha agakingirizo?', { lang: 'rw' })
    expect(a2.length).toBeGreaterThan(20)
    record({ step: 'chat_rw', q: 'Ni gute nakoresha agakingirizo?', a: a2 })
    await shot(page, '05-answer-rw')

    flushEvidence('journey_evidence.json')
  })

  test('deployment is live end-to-end (health + real exchange)', async ({ page }) => {
    // Not just a health ping: prove a fresh visit yields a working chat exchange.
    const health = await page.request.get(
      'https://srh-backend-api.onrender.com/api/v1/health')
    expect(health.ok()).toBeTruthy()
    const body = await health.json()
    expect(body.status).toBe('ok')
    record({ step: 'health', body })

    await enterChat(page)
    const ans = await ask(page, 'What are the symptoms of an STI?', { lang: 'en' })
    expect(ans.length).toBeGreaterThan(20)
    record({ step: 'deploy_exchange', a: ans })
    await shot(page, '07-deployment-live-exchange')
    flushEvidence('deployment_evidence.json')
  })
})
