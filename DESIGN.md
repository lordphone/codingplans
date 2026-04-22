---
version: alpha
name: Coding Plan Comparison
description: Visual identity and UI for the public directory webapp (web/).
colors:
  primary: "#18181b"
  secondary: "#006c49"
  tertiary: "#7c0022"
  neutral: "#f4f4f5"
  surface: "#f9f9f9"
  on-surface: "#1a1c1c"
  surface-container: "#eeeeee"
  outline: "#777777"
  outline-variant: "#c6c6c6"
  accent-interactive: "#059669"
typography:
  h1:
    fontFamily: Inter
    fontSize: 3.5rem
    fontWeight: 800
    lineHeight: 1
    letterSpacing: -0.05em
  brand-wordmark:
    fontFamily: Inter
    fontSize: 1.25rem
    fontWeight: 300
    letterSpacing: 0.35em
  nav-link:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: 700
    letterSpacing: 0.2em
  body-mono:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  version-badge:
    fontFamily: JetBrains Mono
    fontSize: 9px
    fontWeight: 400
rounded:
  sm: 2px
  md: 4px
spacing:
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  main-padding: 48px
  nav-height: 64px
components:
  top-nav:
    backgroundColor: "#ffffff"
    textColor: "{colors.primary}"
    borderColor: "#e4e4e7"
  table-card:
    backgroundColor: "#ffffff"
    borderColor: "#e4e4e7"
    rounded: "{rounded.sm}"
  search-input:
    typography: "{typography.body-mono}"
    borderColor: "#d4d4d8"
    focusRing: "{colors.accent-interactive}"
  link-provider:
    textColor: "{colors.primary}"
    decorationColor: "#e4e4e7"
  alert-error:
    backgroundColor: "#fef2f2"
    textColor: "#991b1b"
    borderColor: "#fecaca"
---

# Coding Plan Comparison

## Overview

**Coding Plan Comparison** (Brand & style) is a read-only, technical **directory** of AI coding plans and models. The UI should feel **institutional and data-forward**: high contrast, monospace for data and metadata, restrained green and red semantic accents, no decorative illustration.

This file follows the **[Stitch DESIGN.md specification](https://stitch.withgoogle.com/docs/design-md/specification/)**: YAML above is **normative** for tokens; sections below are **rationale**. Stack, routes, and data are **not** defined here; see [AGENTS.md](AGENTS.md). Implement tokens in [web/src/styles.css](web/src/styles.css) (`@theme`).

## Colors

**Neutrals-first:** white top bar, zinc-scale borders, off-white **surface** for the main area. **Emerald** is the single interactive accent (focus, key links). **Burgundy** and theme **secondary/tertiary** support semantic states. Chrome uses **Tailwind `zinc`** for inactive nav and dividers. Errors use a light **red** surface, dark red text, and a clear border.

- **Primary (ink):** Headlines and primary table text.
- **Surface / on-surface:** Page background and default copy.
- **Cards:** White panels on surface; table outer wrap reads as one card.
- **Accent:** Emerald for focus rings and primary links; use sparingly.

### Design tokens

The `colors` map in the front matter is canonical; keep `@theme` in `styles.css` in sync when tokens change.

## Typography

**Inter** for UI, display headings, and navigation. **JetBrains Mono** for version strings, slugs, search field, “RESULTS” counts, and auxiliary technical lines. The main directory title is **large, uppercase, tight display**. Nav links and column headers use **small uppercase** with **letter-spaced** caps for a catalog / spec aesthetic.

### Design tokens

See `typography` in the front matter: `h1`, `brand-wordmark`, `nav-link`, `body-mono`, `version-badge`.

## Layout

**Shell:** Full-height column; **fixed** top **navigation**; scrollable **main** below with top padding for the bar height and generous horizontal padding (`main-padding` / `nav-height` in tokens). **No sidebar** in the main shell. **Directory:** full-width content; the comparison table uses **fixed column weights** so the grid stays stable; search is full-width with a trailing result count.

### Design tokens

See `spacing` in the front matter.

## Elevation & Depth

Hierarchy is **flat**: rely on **borders** and **typographic weight** more than deep shadow. **Table** blocks get a **light shadow** and **tight corner radius** so the grid reads as one card on the surface. The **top bar** is white with a **bottom border** only.

## Shapes

**Tight, engineered** corners: small radius on the directory table card; **rectangular** inputs with visible strokes (not pill-shaped). Rounding stays **subtle** and consistent with the `rounded` tokens.

### Design tokens

See `rounded` in the front matter.

## Components

- **Top navigation:** Wordmark (wide letter-spacing) on the left; two primary text links; **version** in mono after a vertical rule. **Active** link: full-contrast text and a **bottom border** marker.
- **Directory table:** Bordered, lightly elevated **card**; clear header row; performance cells may use compact bar or sparkline affordances; tier and model names link inward.
- **Search:** Monospace field; **focus** state uses the accent color on the border; result count as small meta on the right.
- **Refresh strip:** Inline control for cache / freshness without blocking the table.
- **Inline errors:** Bordered alert block; pair with `role="alert"` in implementation.

### Design tokens

See `components` in the front matter (references `colors`, `typography`, `rounded` as needed).

## Do's and Don'ts

- Do use **one** interactive accent (emerald) and **zinc** neutrals for structure.
- Do pair **Inter** with **JetBrains Mono** for data; do not add a third typeface.
- Do keep **body text** comfortably readable; make error states **obvious**, not timid.
- Do not mix **pill** fields and **sharp** table cards in the same screen without a documented rule.
- Do not use **color alone** for status (e.g. quantization or performance); always include **text** or pattern.
