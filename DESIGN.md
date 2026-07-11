---
version: alpha
name: NeverStop Motion Coach
description: |
  A mobile-first AI sports analysis interface for runners and swimmers. The
  product blends Keep-like training clarity with a Spotify-inspired dark,
  immersive app surface: compact, touch-first, data-rich, and emotionally
  energetic without becoming decorative. Video evidence, keyframes, progress
  charts, and report cards are the primary content; the UI recedes into a
  near-black training studio so motion evidence and performance signals can
  stand out.

colors:
  canvas: "#0B0F0E"
  surface: "#121716"
  surface-raised: "#1A211F"
  surface-pressed: "#202A27"
  overlay: "rgba(0, 0, 0, 0.64)"
  ink: "#F7FAF8"
  ink-muted: "#A7B0AC"
  ink-subtle: "#8A9590"
  hairline: "#2D3935"
  hairline-strong: "#45524D"
  brand: "#1ED760"
  brand-pressed: "#19B952"
  on-brand: "#07110B"
  run: "#63D8FF"
  swim: "#4C8DFF"
  effort: "#F7C948"
  warning: "#FFB020"
  negative: "#F3727F"
  positive: "#45E08F"
  evidence-red: "#FF4D5E"
  evidence-yellow: "#FFD166"
  evidence-blue: "#58A6FF"

typography:
  display:
    fontFamily: "SF Pro Display, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 34px
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: 0px
  headline:
    fontFamily: "SF Pro Display, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: 0px
  title:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: 0px
  body:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0px
  body-strong:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: 0px
  label:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: 0px
  caption:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0px
  metric:
    fontFamily: "SF Pro Display, DIN Alternate, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0px
  micro:
    fontFamily: "SF Pro Text, PingFang SC, Noto Sans CJK SC, system-ui, sans-serif"
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0px

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 18px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 48px
  mobile-margin: 16px

components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.on-brand}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 12px 18px
    height: 48px
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 12px 18px
    height: 48px
  icon-button:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    size: 44px
  sport-chip-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 8px 14px
  sport-chip:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 8px 14px
  report-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 16px
  evidence-card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    padding: 8px
  metric-tile:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.metric}"
    rounded: "{rounded.md}"
    padding: 16px
  bottom-nav:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.micro}"
    height: 64px
  timeline-scrubber:
    backgroundColor: "{colors.hairline}"
    textColor: "{colors.brand}"
    rounded: "{rounded.pill}"
    height: 6px
---

## Overview

NeverStop should feel like a compact AI training studio in the user's pocket.
The interface is dark, focused, and kinetic. It should borrow Spotify's
content-first darkness and Keep's direct training utility, but it must not look
like a music clone or a generic fitness dashboard.

The primary content is always the user's movement: uploaded video, keyframes,
pose lines, timing, progress, and plain-language coaching. The UI should make
the user feel that analysis is precise and approachable: "I can see exactly
what happened, and I know what to try next."

The MVP is mobile H5 first. Every screen must work as a thumb-friendly app
surface, with dense but legible information, strong evidence hierarchy, and no
marketing-style hero page as the default experience.

## Colors

The palette is a dark studio with a restrained functional accent system.

- **Canvas** `{colors.canvas}` is the deepest page background and should be
  visible behind persistent navigation and report screens.
- **Surface** `{colors.surface}` and **surface-raised**
  `{colors.surface-raised}` create hierarchy through tonal layers rather than
  bright borders.
- **Brand green** `{colors.brand}` is reserved for primary actions, active
  states, success progress, and the strongest "continue" affordance.
- **Run blue** `{colors.run}` and **swim blue** `{colors.swim}` identify sport
  context, chart lines, and filters. They should not compete with the primary
  action color.
- **Evidence red/yellow/blue** are annotation colors for generated keyframe
  images and pose overlays. They are evidence tools, not decorative accents.

## Typography

Use system fonts with strong Chinese support. The voice is direct, readable,
and coaching-oriented. Avoid overly technical labels in user-facing copy.

- **Display** is used sparingly for the current score, headline insight, or
  workout status.
- **Metric** is used for scores, pace, stroke rate, cadence, and trend numbers.
- **Body** copy should explain what happened in everyday language.
- **Labels** should be compact and scannable, but not uppercase by default
  because Chinese labels do not benefit from the Spotify-style uppercase voice.

## Layout

Use an 8px-based mobile spacing rhythm with dense app screens, not a landing
page layout. The main H5 app should prioritize:

- Upload and analysis status.
- Current report summary.
- Key evidence frames.
- Training suggestions.
- Historical comparison.
- Manual or imported workout records.

Use a bottom navigation pattern for the primary mobile sections: Home, Analyze,
Progress, Profile. Reports live inside Home and Progress so the navigation stays
focused. Keep top bars minimal and action-specific.

## Elevation & Depth

Depth is created with tonal layers and occasional dark shadows. Avoid bright
outlines around every card. Cards should feel like surfaces inside a dark
training console, not floating marketing tiles.

Use shadows for modals, menus, video overlays, and elevated evidence panels.
Use hairlines only when separating dense report rows or chart sections.

## Shapes

Controls are touch-first and pill-oriented. Buttons, sport chips, filters, and
search inputs use pill geometry. Repeated cards and evidence panels use an 8px
radius to stay compact and functional.

Do not use overly soft, large-radius cards for everything. Report cards should
feel precise; primary actions should feel tactile.

## Components

- **Primary button:** brand green pill, used for upload, start analysis, retry,
  and continue actions.
- **Sport chips:** running and swimming filters with active/inactive states.
- **Video evidence card:** image/video frame with pose overlay, timestamp,
  issue label, and one-sentence explanation.
- **Metric tile:** one metric, one delta, one plain-language interpretation.
- **Insight row:** severity, issue title, evidence reference, and next action.
- **Timeline scrubber:** lets the user move between key moments in the video.
- **Bottom navigation:** persistent mobile app navigation, icon-first with
  short labels.

## Do's and Don'ts

- **Do** make uploaded movement evidence the visual center of the report.
- **Do** keep report thumbnails clean; reserve measurement geometry for the
  detailed evidence viewer instead of drawing full skeletons on every image.
- **Do** explain issues in plain language: "落地点略靠前" beats clinical jargon.
- **Do** preserve sport context: running screens can lean into cadence and pace;
  swimming screens can lean into stroke rhythm and body line.
- **Do** use brand green only for action and positive progression.
- **Do** keep annotations high-contrast and readable on video frames.
- **Don't** create a generic SaaS dashboard with decorative cards.
- **Don't** use gradients, glowing blobs, or ornamental background effects.
- **Don't** make the product feel medical or diagnostic.
- **Don't** overload the first MVP with gym/strength-training patterns.
- **Don't** copy Spotify or Keep brand assets, logos, proprietary fonts, or exact
  component compositions.
