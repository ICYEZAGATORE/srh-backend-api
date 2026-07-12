# Step 6 — Usability & accessibility evidence

## What was actually done (honest)
- A **live 3–5 person moderated session was NOT run** in this test cycle (not feasible
  in the automated environment). The **structured feedback form**
  (`usability_feedback_form.md`) is provided as the lighter-weight substitute, ready to
  administer with the defined task *"find out how to get tested for an STI confidentially."*
- **Automated accessibility testing WAS run** and is the concrete usability evidence here.

## Accessibility evidence (ran this cycle)
- **`jest-axe` automated WCAG checks: 9 assertions across 5 suites — 0 violations.**
  Full frontend suite: **31/31 passing** (`cd srh-frontend && npx vitest run src/test`).
  Covered: landing + all routes (`routes.a11y.test.jsx` ×3), chat (`chat.test.jsx`),
  onboarding/consent (`onboarding.test.jsx`), settings (`settings.test.jsx`), and the new
  voice-input mic states (`voice-input.test.jsx` ×3 — idle / listening / KN-unavailable).
- **Keyboard-operability** is asserted in tests (e.g. tab to input, Enter to send; mic button
  reachable and operable by keyboard with visible focus and `aria-live` announcements).
- **Manual screen-reader audit checklist exists and is ready for a human tester** —
  `srh-frontend/docs/ACCESSIBILITY_MANUAL_AUDIT.md` (WCAG 2.1 AA, NVDA desktop + TalkBack
  Android, per-screen keystroke scripts). This is the pending human-in-the-loop step.

## Accessibility features verified present (map to proposal §3.4)
| feature | state | evidence |
|---|---|---|
| Screen-reader labels / ARIA / live regions | ✅ | jest-axe 0 violations; `aria-live` on chat + mic |
| Keyboard operability + visible focus | ✅ | e2e Enter-to-send; a11y tests |
| Adjustable text size | ✅ | `FontSizeControl`, settings test |
| High-contrast mode | ✅ | `ContrastToggle` + HC token set |
| Read-aloud (TTS output) | 🟡 | Web Speech API fallback (Mozilla-TTS microservice dormant in prod) |
| Voice **input** (STT, EN) | ✅ | `voice-input.test.jsx`; KN shown disabled with honest label |

## Gaps / recommended next steps
- Run the moderated 3–5 user session (form ready) and a human NVDA/TalkBack pass (checklist ready).
- Kinyarwanda screen-reader pronunciation is limited (no KN NVDA voice) — note for the panel.
