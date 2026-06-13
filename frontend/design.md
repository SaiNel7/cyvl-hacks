# Neo-Brutalist Web App Design System

## Overview

The application uses a neo-brutalist visual language that prioritizes boldness, clarity, personality, and usability over subtlety and realism.

Core principles:

* High contrast
* Visible structure
* Minimal visual effects
* Playful but functional
* Strong hierarchy
* Accessible interactions

The interface should feel handmade, confident, and memorable rather than polished or corporate.

---

# Visual Identity

## Design Goals

Users should perceive the product as:

* Creative
* Honest
* Modern
* Fun
* Fast
* Independent

Avoid:

* Glassmorphism
* Excessive gradients
* Soft shadows
* Overly rounded interfaces
* Enterprise SaaS aesthetics

---

# Color System

## Primary Colors

* Black: #000000
* White: #FFFFFF
* Yellow: #FFD600
* Blue: #4D7CFE
* Pink: #FF5C8A
* Green: #00D26A

## Usage Rules

* Large flat color surfaces
* Maximum contrast between foreground and background
* No subtle color transitions
* Use color intentionally for emphasis

Example:

* Primary CTA → Yellow
* Secondary CTA → White
* Danger → Pink
* Success → Green

---

# Typography

## Primary Font

* Inter
* Space Grotesk
* IBM Plex Sans

Preferred: Space Grotesk

## Typography Principles

* Large headings
* Tight hierarchy
* Bold weights
* Minimal font variations

### Heading Scale

| Element | Size |
| ------- | ---- |
| H1      | 64px |
| H2      | 48px |
| H3      | 32px |
| H4      | 24px |
| Body    | 16px |
| Small   | 14px |

### Font Weights

* Heading: 700–800
* Body: 500
* Labels: 600

---

# Layout System

## Grid

* 12-column desktop grid
* 8px spacing system

Spacing values:

* 8
* 16
* 24
* 32
* 48
* 64

## Container Widths

* Small: 768px
* Medium: 1024px
* Large: 1280px

---

# Border System

The border is the primary visual separator.

## Rules

* Default border: 3px solid black
* Interactive elements: 4px solid black
* Cards: 3px solid black

No translucent borders.

---

# Shadow System

Neo-brutalist shadows are geometric and obvious.

## Standard Shadow

box-shadow:
8px 8px 0px #000;

## Hover Shadow

box-shadow:
4px 4px 0px #000;

Hover should appear physically pressed.

---

# Component Library

## Buttons

### Primary

* Yellow background
* Black text
* 4px black border
* Hard shadow

Hover:

* Move down 4px
* Shadow reduces

Active:

* Move down 8px
* Shadow disappears

---

## Cards

Properties:

* White background
* Black border
* Hard shadow
* Large title
* Visible spacing

Card layout:

Header
Body
Actions

---

## Inputs

Properties:

* White background
* Black border
* No glow effects
* Large hit area

Focus state:

* 4px outline
* High contrast color

---

## Navigation

Top navigation should be:

* Fixed or sticky
* Thick border
* Contrasting background
* Large clickable targets

---

## Tables

* Visible grid lines
* Strong headers
* No zebra striping
* Borders define structure

---

# Motion Design

## Principles

Motion should feel mechanical rather than fluid.

Use:

* Position changes
* Scale changes
* Press effects

Avoid:

* Long easing curves
* Floating animations
* Excessive fades

### Duration

* Fast: 100ms
* Normal: 150ms
* Slow: 200ms

---

# Illustrations

Style:

* Hand-drawn
* Doodles
* Marker-style
* Simple geometric characters

Avoid:

* Corporate stock illustrations
* 3D renders
* Realistic graphics

---

# Accessibility

Requirements:

* WCAG AA contrast minimum
* Keyboard navigable
* Visible focus states
* Touch targets ≥ 44px
* Semantic HTML

---

# Example Page Structure

Navigation
├── Logo
├── Links
└── CTA Button

Hero
├── Large Headline
├── Supporting Copy
└── Primary CTA

Feature Grid
├── Card
├── Card
├── Card

Content Section
├── Statistics
├── Charts
└── Insights

Footer
├── Links
├── Contact
└── Socials

---

# Success Criteria

A user should immediately recognize the product as:

* Bold
* Unique
* Playful
* High-confidence
* Easy to navigate

The interface should never feel delicate, glossy, or overly corporate.
