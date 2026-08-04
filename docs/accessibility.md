# Accessibility notes

Automated axe checks cover selected home/workspace chrome in Vitest. They do **not**
prove full WCAG conformance.

## Implemented practices

- Semantic landmarks (`main`, headings, labeled sections)
- Form labels for text input and upload browse control
- Keyboard-accessible drag-and-drop fallback (Enter/Space opens file picker)
- `aria-live` / `role="status"` / `role="alert"` for health, loading, and errors
- Visible focus outlines (teal focus ring) and `prefers-reduced-motion` damping
- Non-color cues for health (text + indicator) and verification badges (text labels)
- Delete confirmations via browser `confirm` dialogs
- Download controls with descriptive accessible names on document results

## Remaining limitations

- PDF.js canvas overlays are primarily visual; screen-reader users rely on the entity list
- Manual rectangle drawing is pointer-oriented; keyboard alternatives are limited to
  creating entities via numeric fields / entity list where provided
- Color badges still use color for quick scanning; status text is also present
- Modal dialogs use native `window.confirm` rather than fully managed focus-trap dialogs
- Contrast of some amber/emerald informational panels should be re-checked under user themes
- Full WCAG 2.2 AA audit (manual + assistive technology) has not been completed

## Commands

```bash
cd apps/web
npm run test -- tests/accessibility.test.tsx
```
