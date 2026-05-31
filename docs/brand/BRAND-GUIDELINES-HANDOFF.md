# Brand Guidelines — Handoff

**Date:** 2026-05-29 · **Branch:** `codex/homepage-ui-refinement` (not pushed)

## Status

- ✅ **Portable HTML artifact finalized & committed** — `vandoko-brand-guidelines.html` (commit `5ecdcfb`). This is the **source of truth** for the build below.
- ✅ v2 app-icon PNGs copied into `public/images/brand/` (`vandoko-v2-icon-white.png`, `vandoko-v2-icon-black.png`, `vandoko-wordmark-transparent-black.png`) — removes the `Z:` drive dependency.
- ⏳ **NEXT TASK: build the live React page** at `src/app/preview/brand/page.tsx` to match the HTML v1.1.

## Next task — build the live `/preview/brand` page

`src/app/preview/brand/page.tsx` currently exists as a **v1.0 scaffold** (untracked, reflects OLD values) and **must be rebuilt** to match the committed HTML. `src/app/preview/layout.tsx` already has the `Brand system` nav link added (untracked — part of the broader preview WIP tree; commit deliberately).

Render the committed HTML in a browser side-by-side and reproduce it with real tokens/components. Deltas to apply (the full set agreed across review rounds):

1. **Brand cyan `#00EEFF`** (NOT `#00E5FF`). Lime fully retired.
2. **11-step ramps** — Cyan (hue 184): `50 #EBFEFF · 100 #CCFCFF · 200 #99F8FF · 300 #66F5FF · 400 #33F1FF · 500 #00EEFF · 600 #00CDDB · 700 #00A7B3 · 800 #037E87 · 900 #04575D · 950 #04363A`. Neutral (hue 240): `50 #F4F4F6 · 100 #DEDEE3 · 200 #B8B8C1 · 300 #93939F · 400 #6E6E7C · 500 #51515D · 600 #383842 · 700 #25252C · 800 #19191F · 900 #101014 · 950 #09090B`.
3. **Semantic colors** — Destructive `#D00E11` · Positive `#0DBF2E` · Warning `#D23E08` · Alert `#C70971`.
4. **Logos** — both marks **white** (obsidian on light). **5 primary assets**: wordmark white, wordmark black, brandmark (no bg), app icon dark, app icon light. App-icon tiles use the **real PNGs** in `public/images/brand/` (not recreated SVGs). Captions **outside** asset cards. Enforce clear space (≥ "K" counter) + min size (wordmark 20px, brandmark 16px). The black-wordmark card must center the mark (use explicit `align-items/justify-content`).
5. **Type scale** small→large: `xs/sm/base/l/xl/xxl/xxxl` (xxxl largest).
6. **Radius** — `4px` pills/tags · `8px` buttons·fields·cards · `11px` panels · `full` avatars + labeled rank badges only.
7. **Borders** — active/focus accent is a **cyan gradient** (cyan-400→cyan-700), not flat.
8. **Buttons** — matrix: **columns = size, largest→smallest (Large·Default·Small·Icon)**; **rows = priority/variant**. Uniform column widths sized to the secondary button. Plus a states matrix (Rest/Hover/Focus/Disabled). Gradient CTA = cyan ramp.
9. **Cards** — add a **Shadows & Layering** subsection (elevation ramp + depth illustration). **No cyan glow.** `card-border-reveal` hover changes border/surface only — **no Y-axis translate**.
10. **Blueprint UI** — mirror the homepage hero: copy column (eyebrow→xxl headline→body→primary+ghost CTAs) beside a **premium blueprint panel** (`ArcGauge` tick-arc, `SegmentedGaugeBar`, metric cells). Real layering/borders/typography.
11. **Data viz** — from the blueprint atoms: `ArcGauge` (56 ticks, 270° sweep, cyan active / muted inactive), `SegmentedGaugeBar`, `SignalHeatmap` (score `(i*17+i*i*3)%11`), KPI cells. Palette from ramps: dealer `cyan-500`, market `neutral-400`, series step the cyan ramp. Components live in `src/components/launch/data-visuals.tsx` and `src/components/ui/atoms/`.
12. **Gradients & depth** — surface-ramp dark tones; lime / CTA-glow / signal-shadow removed.
13. **No dots/orbs** — strictly. No pulsing/flashing. Status = short cyan **bar**, left-border, or label. Circles only for avatars + labeled rank badges.

## Flagged for separate PRs (token discipline — see CLAUDE.md Design System)

- **Token PR (`src/app/globals.css` + `src/lib/chart-colors.ts`):** set brand cyan to `#00EEFF`; remove lime `--accent` usage; add 11-step cyan + neutral ramps; rename semantic tokens to `--positive` / `--warning` / `--alert` with the new hexes; repoint chart colors to the cyan ramp (retire `#06b6d4`).
- **Component fix (`src/components/ui/button.tsx`):** `lg` is `h-10` (40px) and `default` is `h-12` (48px) — swap so **lg=48 / default=40** to match labels. Decide `toggle` variant: re-radius to 4px (pills) or retire it.

## Verification recipe

- Render: `file://` is **blocked** by playwright-cli → serve over HTTP: `python -m http.server 8765` then `playwright-cli open http://localhost:8765/...`.
- `pnpm exec tsc --noEmit` (clean) + `pnpm exec eslint --fix` on new files (Prettier). **Do not** run full `pnpm build` — known unrelated `/blog/[slug]` MDX/Turbopack break.
- Delete scratch screenshots/files before committing.
