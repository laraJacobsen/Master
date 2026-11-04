# React + TypeScript UI Design Rules

## Core Directive
Strictly avoid generic AI layouts. You must use deliberate, modern layouts, asymmetric spacing, and strong typography. Follow these strict rules for every component.

## Tech Stack Constraints
- **Framework:** React 19 (Functional components, Hooks)
- **Language:** TypeScript (Strict typing, no `any`, explicit component props)
- **Styling:** Tailwind CSS (Utility-first, semantic class naming)

## Theme & Variables
- **Backgrounds:** Pure Dark (`bg-zinc-950`) or crisp light (`bg-zinc-50`). No off-white cream or generic muddy grays.
- **Borders:** Ultra-thin, low-contrast borders (`border-zinc-800` or `border-zinc-200`).
- **Typography:** Sans-serif headers (`tracking-tight font-bold`), clean monospace only for actual code or numbers.
- **Radius:** Subtle, modern rounding (`rounded-lg` or `rounded-xl`). Never use pill-shaped (`rounded-full`) buttons unless specifically asked.

## Execution Flow
1. Verify the layout structure before writing TypeScript interfaces.
2. Ensure all UI elements have proper hover, focus, and disabled states.
3. Export strict TypeScript prop interfaces for every single component.
