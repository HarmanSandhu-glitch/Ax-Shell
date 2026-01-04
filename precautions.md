# Precautions: Unsupported CSS Properties in GObject

## Introduction
This document exists to stop subtle breakage before it starts. GObject-based UI toolkits (most notably GTK) use a **CSS-like** styling system, not real web CSS. Many familiar CSS properties either do nothing, are partially implemented, or are outright ignored. This file lists commonly **unsupported CSS properties** so developers and AI-generated changes don’t accidentally rely on features that GObject simply does not implement.

Treat this as a defensive checklist, not a theoretical discussion.

## Unsupported CSS Properties

- **display: flex / flexbox-related properties**
  - Description: Enables flexible box layouts with dynamic alignment and sizing.
  - Reason for Non-Support: GObject/GTK uses its own layout containers (Box, Grid, etc.). CSS is strictly for styling, not layout logic.

- **display: grid / CSS Grid properties**
  - Description: Defines two-dimensional grid-based layouts.
  - Reason for Non-Support: Layout is handled entirely by GTK widgets, not CSS. Grid logic exists only at the widget level.

- **position (relative, absolute, fixed, sticky)**
  - Description: Controls element positioning relative to parents or the viewport.
  - Reason for Non-Support: GTK does not have a DOM or visual flow model compatible with CSS positioning.

- **top / right / bottom / left**
  - Description: Offsets positioned elements.
  - Reason for Non-Support: These rely on CSS positioning, which GTK does not implement.

- **z-index**
  - Description: Controls stacking order of overlapping elements.
  - Reason for Non-Support: GTK stacking is controlled by widget hierarchy, not CSS layers.

- **transform**
  - Description: Applies translations, rotations, scaling, or skewing.
  - Reason for Non-Support: GTK CSS does not support geometric transformations; these require custom drawing or animations.

- **animation / animation-* properties**
  - Description: Defines keyframe-based animations.
  - Reason for Non-Support: GTK CSS has no keyframe engine. Animations must be implemented programmatically.

- **@keyframes**
  - Description: Defines animation steps.
  - Reason for Non-Support: No animation timeline system exists in GTK CSS.

- **transition / transition-* properties**
  - Description: Smoothly interpolates property changes over time.
  - Reason for Non-Support: GTK does not interpolate CSS property changes automatically.

- **filter**
  - Description: Applies visual effects like blur, brightness, or contrast.
  - Reason for Non-Support: GTK CSS does not include a rendering filter pipeline.

- **backdrop-filter**
  - Description: Applies effects to background content behind an element.
  - Reason for Non-Support: Requires compositor-level support not available in GTK CSS.

- **box-shadow (inset, multiple shadows)**
  - Description: Adds layered or inset shadows.
  - Reason for Non-Support: GTK supports only a limited shadow model; advanced shadows are ignored.

- **outline**
  - Description: Draws a line outside the border without affecting layout.
  - Reason for Non-Support: Not implemented in GTK’s CSS renderer.

- **cursor**
  - Description: Changes the mouse cursor style.
  - Reason for Non-Support: Cursor handling is controlled by widgets and GDK, not CSS.

- **overflow / overflow-x / overflow-y**
  - Description: Controls clipping and scrolling behavior.
  - Reason for Non-Support: Scrolling and clipping are widget responsibilities, not CSS concerns.

- **vh / vw / vmin / vmax units**
  - Description: Viewport-relative sizing units.
  - Reason for Non-Support: GTK CSS has no concept of a browser viewport.

## Best Practices

- Use **GTK layout widgets** (`GtkBox`, `GtkGrid`, `GtkCenterBox`) instead of `flex` or `grid`.
- Use **padding, margin, border, border-radius, and background-color**, which are reliably supported.
- Use **GTK animations (GdkFrameClock, GtkRevealer, GtkStack transitions)** instead of CSS animations.
- Use **opacity** sparingly and only where supported by the specific GTK version.
- Implement advanced visuals using **custom drawing (Cairo, snapshot APIs)** rather than CSS hacks.
- Always test styles with **GTK Inspector**, not browser dev tools.

## Conclusion
GTK’s CSS is intentionally limited. It is a styling language, not a layout or animation engine. Developers should regularly verify supported properties against official GTK documentation and release notes, as support evolves slowly and deliberately. When in doubt, assume a web-only CSS feature does **not** exist in GObject until proven otherwise.
