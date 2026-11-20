# Mobile popup overlap fix

This archive is a **patch for the live GitHub Pages repository**, not a replacement database.

## Install
Replace only `index.html`, `bg.html`, and `ro.html` in the repository root. Do not overwrite any files in `data/`, `scripts/`, or `.github/`.

## Changes
- Mobile incident popups use a native HTML `dialog.showModal()` bottom sheet. It is rendered in the browser's top layer, so the header, filter toolbar, count, and archive cannot cover it.
- Close control is always in the upper right of the dialog, 44×44px touch target.
- Dialog scrolls internally when descriptions are long, respects iOS bottom/top safe areas, closes on Escape, X, or backdrop tap.
- Desktop map retains ordinary anchored Leaflet popups.
- Responsive breakpoint re-renders marker interaction when switching desktop/mobile.

No news, incidents, translations, DeepL limits, or scheduled jobs have been modified.
