import { expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

export const EVID_DIR = path.join(process.cwd(), 'e2e', 'results', 'evidence')
fs.mkdirSync(EVID_DIR, { recursive: true })

// sr-only loading label the ChatWindow announces while awaiting an answer.
export const LOADING = {
  en: 'Preparing a thoughtful answer...',
  rw: 'Turimo gutegura cyiza...',
}

/** Drive the real consent gate (two checkboxes → Continue) into the chat view. */
export async function enterChat(page) {
  await page.goto('/chat')
  const boxes = page.getByRole('checkbox')
  await boxes.nth(0).check({ force: true })
  await boxes.nth(1).check({ force: true })
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('textbox')).toBeVisible()
}

const messages = (page) => page.locator('ul[aria-live="polite"] > li')

/** Send a message and wait for the answer (or safe fallback) to finish rendering. */
export async function ask(page, text, { lang = 'en' } = {}) {
  const before = await messages(page).count()
  const input = page.getByRole('textbox')
  await input.fill(text)
  // Submit via Enter (InputBar submits on Enter) — language-agnostic, unlike the
  // Send button whose accessible name is localized (EN "Send" / RW "Ohereza").
  await input.press('Enter')
  // Wait out the loading indicator (covers cold start). It may flash quickly.
  const loading = page.getByRole('status', { name: LOADING[lang] })
  await loading.waitFor({ state: 'hidden', timeout: 155_000 }).catch(() => {})
  // The assistant bubble is the message added after the user's.
  await expect(messages(page)).toHaveCount(before + 2, { timeout: 155_000 })
  await page.waitForTimeout(400)
  return (await messages(page).last().innerText()).trim()
}

/** Header language toggle: in EN the button reads "Kinyarwanda" (the target lang). */
export async function switchLanguage(page, toName) {
  await page.getByRole('button', { name: toName }).first().click()
}

const evidence = []
export function record(entry) { evidence.push({ ts: new Date().toISOString(), ...entry }) }
export function flushEvidence(file) {
  fs.writeFileSync(path.join(EVID_DIR, file), JSON.stringify(evidence, null, 2))
}
export async function shot(page, name) {
  await page.screenshot({ path: path.join(EVID_DIR, `${name}.png`), fullPage: true })
}
