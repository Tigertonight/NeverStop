# Design References

This project uses `DESIGN.md` as the persistent visual source of truth for
future AI-assisted design and frontend work.

## Source Projects

- [google-labs-code/design.md](https://github.com/google-labs-code/design.md)
  provides the file format, YAML front matter structure, token reference syntax,
  and canonical section order.
- [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md)
  provides practical examples of brand-specific `DESIGN.md` files, including
  dark, app-like, and consumer-product visual systems.

## What We Adopt

- Root-level `DESIGN.md` so coding agents can read the design system before
  building UI.
- YAML front matter for machine-readable tokens: colors, typography, radius,
  spacing, and components.
- Markdown prose for intent, constraints, and product-specific judgment.
- Standard section order: Overview, Colors, Typography, Layout, Elevation &
  Depth, Shapes, Components, Do's and Don'ts.
- Token references like `{colors.brand}` inside component definitions.

## What We Adapt

NeverStop is not a music product or a generic fitness tracker. The desired feel
is:

- Spotify-inspired: dark immersive app shell, content-first surfaces, compact
  density, strong pill controls.
- Keep-inspired: clear training context, direct coaching, action-oriented
  workout flows.
- Product-specific: video evidence, pose annotations, AI reports, running and
  swimming progress comparisons.

The design system intentionally avoids copying proprietary Spotify/Keep assets,
logos, fonts, or exact component layouts. We borrow design principles, not brand
identity.

## Design Guardrails For Frontend Work

- Build mobile H5 first.
- Default first screen should be the app experience, not a marketing landing
  page.
- Use `DESIGN.md` tokens before inventing new colors, spacing, or type styles.
- Keep report surfaces compact and readable; this is an operational coaching
  app, not an editorial article.
- Use real movement evidence wherever possible: uploaded video, keyframes,
  pose overlays, charts, and historical deltas.
- Keep AI advice easy to understand and non-medical.

## Validation

The Google project provides a CLI that can lint the format:

```bash
npx @google/design.md lint DESIGN.md
```

If a package registry or network policy blocks `npx`, treat the root
`DESIGN.md` as the canonical source and validate manually against the Google
spec structure.
