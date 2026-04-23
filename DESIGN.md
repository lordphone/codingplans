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
  chart-throughput: "#059669"
  chart-latency: "#2563eb"
  chart-grid: "#d4d4d8"
  chart-tick: "#71717a"
typography:
  h1-display:
    fontFamily: Inter
    fontSize: 3.5rem
    fontWeight: 800
    lineHeight: 1
    letterSpacing: -0.05em
  h1-entity:
    fontFamily: Inter
    fontSize: 2.25rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.025em
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

**Coding Plan Comparison** (Brand & style) is a read-only, technical **directory** of AI coding plans and models. The UI should feel **institutional and data-forward**: high contrast, monospace for data and metadata, semantic greens and burgundy from theme `secondary` / `tertiary`, and **no** decorative illustration.

This file follows the **[Stitch DESIGN.md specification](https://stitch.withgoogle.com/docs/design-md/specification/)**: YAML above is **normative**; sections below are **rationale**. Stack, routes, and data are **not** defined here; see [AGENTS.md](AGENTS.md). **Source of truth in code:** [web/src/styles.css](web/src/styles.css) (`@theme`); this document stays aligned with that file.

## Colors

**Neutrals-first:** white top bar, **zinc** borders for chrome, off-white **surface** for the main area. **Primary** (`#18181b`, ink) is the default for titles and `text-primary` in the app. **Accent-interactive** (`#059669`) is the **UI** accent: link hovers, search focus, refresh hover border. **Secondary** and **tertiary** are semantic (verified / scam-style states), not the same as the blue latency chart. **Chart** line colors are separate tokens so **throughput** and **latency** stay distinguishable. Errors use a light **red** surface, dark red text, and a clear border. Chrome uses **Tailwind `zinc`** for inactive nav and many dividers.

- **primary / on-surface / surface:** Core text, background, and panels (see `components` in front matter and `@theme`).
- **chart-throughput:** Same hue as `accent-interactive` — TPS time-series and legend.
- **chart-latency:** Blue — TTFT time-series and legend (second series, not a third UI accent).
- **chart-grid / chart-tick:** Axes and tick labels in SVGs.

### Design tokens

The `colors` map matches **`@theme` in** `web/src/styles.css`. When you change a token, update both places.

## Typography

**Inter** for UI, navigation, and headings. **JetBrains Mono** for version, slugs, search field, “RESULTS”, and technical lines. There are two **H1** levels:

- **Display (h1-display):** **Directory**, **Benchmarks**, **Models** — `3.5rem`, extrabold, uppercase, tight tracking.
- **Entity (h1-entity):** **Provider** and **Plan** page titles (dynamic names) — `text-3xl` / `md:text-4xl`, semibold, sentence case, because long provider/plan names should not be forced to all-caps.

Nav links and table column headers use **small caps** (uppercase, letter-spaced). Nav link and `version` patterns match `nav-link` and `version-badge` in the front matter.

### Design tokens

See `typography` in the front matter: `h1-display`, `h1-entity`, `brand-wordmark`, `nav-link`, `body-mono`, `version-badge`.

## Layout

**Shell:** Full-height column; **fixed** top **navigation**; **main** below with `nav-height` top padding and `main-padding` horizontal padding. **No sidebar.** The directory table uses **fixed column** weights; search is full-width with a trailing result count.

### Design tokens

See `spacing` in the front matter.

## Elevation & Depth

Hierarchy is **flat**: **borders** and type weight, not deep shadow. **Table** blocks get **`shadow-sm`** and **tight** radius so the grid reads as one **card** on the surface. The **top bar** is white with a **bottom border** only.

## Shapes

**Tight, engineered** corners: **`rounded-sm`** on table cards; **rectangular** inputs and chart window toggles; no pill search fields. See `rounded` in the front matter.

### Design tokens

See `rounded` in the front matter.

## Components

- **Top navigation:** Wordmark; **DIRECTORY** / **BENCHMARKS**; version in mono. Active link: **`text-primary`** and **bottom border** (see [layout](web/src/app/components/layout/layout.component.ts)).
- **Directory table:** Bordered **card**; TPS minibar fill uses **primary**; links use `hover:` **accent-interactive** and matching underline.
- **Search:** `focus:border-accent-interactive`.
- **Refresh strip:** `catalog-refresh-strip` — `hover:border-accent-interactive` and `hover:text-primary` on the button.
- **Plan metrics charts:** Strokes and fills use CSS variables from `@theme` (`--color-chart-throughput`, `--color-chart-latency`, grid, tick).
- **Inline errors:** Bordered alert; use `role="alert"` in markup.

### Design tokens

See `components` in the front matter.

## Do's and Don'ts

- Do use **`text-primary`**, **`bg-primary`**, **`border-primary`** for “ink” interactive states; pair with **zinc** for de-emphasized structure.
- Do use **`text-accent-interactive`**, **`border-accent-interactive`**, and **`bg-chart-throughput` / `bg-chart-latency`** only where the implementation maps to these roles (not arbitrary extra hues).
- Do pair **Inter** with **JetBrains Mono**; do not add a third typeface.
- Do keep error states high-contrast and obvious.
- Do not mix **pill** inputs and **sharp** table cards without a system rule.
- Do not use **color alone** for status; always include **text** (e.g. labels, “Loss detected”).
