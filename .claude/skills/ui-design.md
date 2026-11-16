# React + TypeScript UI Design Rules

## Core Directive
Strictly avoid generic AI layouts. You must use deliberate, modern layouts, asymmetric spacing, and strong typography. Follow these strict rules for every component.

## Tech Stack Constraints
- **Framework:** React 19 (Functional components, Hooks)
- **Language:** TypeScript (Strict typing, no `any`, explicit component props)
- **Styling:** Tailwind CSS (Utility-first, semantic class naming)

## Theme & Variables
- **Palette:** Three primaries, defined as tokens in `frontend/src/shared/index.css`:
  - Ink `#292D32` = `zinc-900` (text, headings). The whole `zinc` scale is overridden as a cool grey ramp.
  - Base `#F9FAFA` = `zinc-50` (page background, with a faint blue/violet wash). Cards are `bg-white`.
  - Accent `#5E65E8` = `brand-500` (primary buttons, focus rings, selection, progress, "current" marks). Use `brand-50/100/200` for tinted info surfaces.
  - Tailwind `violet` is the secondary accent: sparingly, paired with brand (e.g. the logo gradient). Never as a verdict colour.
- **Mood:** Light, airy, modern, distraction-free. Accent colour marks what is interactive or selected; everything else stays neutral.
- **Verdicts:** emerald / amber / red stay reserved for correct / partial / incorrect (`shared/verdictStyles.ts`); don't use brand for them.
- **Borders:** Ultra-thin, low-contrast borders (`border-zinc-200`).
- **Typography:** Poppins (`font-sans`). Headers `tracking-tight font-bold`; clean monospace (JetBrains Mono) only for actual code or numbers.
- **Radius:** Subtle, modern rounding (`rounded-lg` or `rounded-xl`). Never use pill-shaped (`rounded-full`) buttons unless specifically asked.

## Execution Flow
1. Verify the layout structure before writing TypeScript interfaces.
2. Ensure all UI elements have proper hover, focus, and disabled states.
3. Export strict TypeScript prop interfaces for every single component.
