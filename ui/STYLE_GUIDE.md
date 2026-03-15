# Style Guide

## Aesthetic
Dark, cinematic, investigation-board energy. Think case files, typewriter reports, and stamped confidential documents. Not playful — deliberate and gritty.

## Fonts (Google Fonts)

Import:
```html
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Special+Elite&family=Archivo+Black&family=Courier+Prime:wght@400;700&family=Caveat:wght@400;600;700&display=swap" rel="stylesheet">
```

| Role | Font | Weight | Usage |
|------|------|--------|-------|
| Page titles / hero text | Bebas Neue | 400 | All-caps, wide letter-spacing (0.15em), large sizes (32-48px). Always on dark backgrounds with light text. |
| Stamps / labels | Archivo Black | 400 | Uppercase, letter-spacing 0.2em. Used inside bordered pill/box with slight rotation (-3deg). Red on white or white on red. |
| Body / narrative text | Special Elite | 400 | Typewriter texture. 14-16px, line-height 1.8. Feels like a real case report. |
| Data / metadata / code | Courier Prime | 400, 700 | Clean monospace for dates, IDs, stats, structured data. 11-13px. |
| Handwritten annotations | Caveat | 600 | Signatures, marginal notes, informal callouts. 18-22px. Blue (#1a3a6a) for detective notes. |

### Tailwind config (if applicable)
```js
fontFamily: {
  display: ['"Bebas Neue"', 'sans-serif'],
  stamp: ['"Archivo Black"', 'sans-serif'],
  typewriter: ['"Special Elite"', 'monospace'],
  mono: ['"Courier Prime"', 'monospace'],
  handwritten: ['"Caveat"', 'cursive'],
}
```

## Colors

### Core palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#0c0b0f` | Page background |
| `--bg-card` | `#faf3e6` | Card/paper surfaces |
| `--bg-card-white` | `#ffffff` | Clean document cards |
| `--bg-dark-card` | `#1a1a1a` | Dark cards (headers, legends) |
| `--text` | `#e8dcc8` | Primary text on dark bg |
| `--text-dark` | `#222222` | Primary text on light cards |
| `--text-dim` | `#8b7355` | Secondary/muted text |
| `--accent-red` | `#cc3333` | Stamps, labels, highlights, borders |
| `--accent-dark-red` | `#8b0000` | Category labels, evidence IDs |
| `--accent-blue` | `#1a3a6a` | Handwritten notes, signatures |

## Key Components

### Title bar (from case header)
Dark background (#1a1a1a), centered Bebas Neue text, bottom border in accent red. Subtitle in Courier Prime, muted color.
```css
.title-bar {
  background: #1a1a1a;
  padding: 14px 48px;
  text-align: center;
  border-bottom: 3px solid #8b0000;
}
.title-bar h1 {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 38px;
  letter-spacing: 0.15em;
  color: #e8dcc8;
}
.title-bar .subtitle {
  font-family: 'Courier Prime', monospace;
  font-size: 12px;
  color: #8b7355;
  letter-spacing: 0.1em;
}
```

### Confidential note card
White background, red left border, stamped label with Archivo Black, body in Special Elite, signature in Caveat.
```css
.note-card {
  background: #fff;
  padding: 24px 20px;
  border-left: 3px solid #cc3333;
  box-shadow: 2px 3px 12px rgba(0,0,0,0.25);
}
.note-card .stamp {
  font-family: 'Archivo Black', sans-serif;
  font-size: 14px;
  color: #cc3333;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  border: 2px solid #cc3333;
  display: inline-block;
  padding: 2px 10px;
  transform: rotate(-3deg);
  margin-bottom: 14px;
}
.note-card p {
  font-family: 'Special Elite', monospace;
  font-size: 14px;
  color: #222;
  line-height: 1.8;
}
.note-card .signature {
  font-family: 'Caveat', cursive;
  font-size: 20px;
  color: #1a3a6a;
  margin-top: 14px;
}
```

## General Rules
- Cards get subtle rotation (`transform: rotate(-1.5deg)`) and box-shadow for pinned-to-board feel
- Dark backgrounds only — never white page backgrounds
- Stamps/labels always slightly rotated and bordered
- Use Courier Prime for any structured data (dates, IDs, stats)
- Handwritten elements (Caveat) are always blue, never black
- Body text (Special Elite) gets generous line-height (1.8)
- Headlines (Bebas Neue) always uppercase with wide tracking
