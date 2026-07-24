---
name: Librarian's Ledger
colors:
  surface: '#f8f9ff'
  surface-dim: '#d1dbec'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eef4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dfe9fa'
  surface-container-highest: '#d9e3f4'
  on-surface: '#121c28'
  on-surface-variant: '#42493e'
  inverse-surface: '#27313e'
  inverse-on-surface: '#eaf1ff'
  outline: '#72796e'
  outline-variant: '#c2c9bb'
  surface-tint: '#3b6934'
  primary: '#154212'
  on-primary: '#ffffff'
  primary-container: '#2d5a27'
  on-primary-container: '#9dd090'
  inverse-primary: '#a1d494'
  secondary: '#5e5f5a'
  on-secondary: '#ffffff'
  secondary-container: '#e3e3dc'
  on-secondary-container: '#646560'
  tertiary: '#00367a'
  on-tertiary: '#ffffff'
  tertiary-container: '#004ca6'
  on-tertiary-container: '#a7c2ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#bcf0ae'
  primary-fixed-dim: '#a1d494'
  on-primary-fixed: '#002201'
  on-primary-fixed-variant: '#23501e'
  secondary-fixed: '#e3e3dc'
  secondary-fixed-dim: '#c7c7c0'
  on-secondary-fixed: '#1b1c18'
  on-secondary-fixed-variant: '#464742'
  tertiary-fixed: '#d8e2ff'
  tertiary-fixed-dim: '#adc6ff'
  on-tertiary-fixed: '#001a42'
  on-tertiary-fixed-variant: '#004395'
  background: '#f8f9ff'
  on-background: '#121c28'
  surface-variant: '#d9e3f4'
typography:
  display:
    fontFamily: Hanken Grotesk
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  headline-lg-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-max-width: 1440px
  gutter: 24px
  margin-desktop: 40px
  margin-mobile: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style

The design system is built for a Small Neighborhood Library Management System, prioritizing utility, focus, and a sense of institutional trust. The brand personality is "The Modern Curator": professional and systematic, yet warm and inviting like a well-kept local library. 

The design style leans into **Corporate Modern with a Bibliophilic Twist**. It utilizes a clean, card-based architecture that feels organized and reliable. While the functionality is strictly administrative, the aesthetic avoids the coldness of generic enterprise software by using a "book-ish" color palette and soft surface treatments. The UI evokes an emotional response of order and calm, ensuring that librarians can manage high volumes of data without cognitive fatigue.

## Colors

This design system utilizes a palette rooted in traditional library aesthetics modernized for digital clarity.

- **Primary (#2D5A27):** A deep, scholarly green used for primary actions, branding, and navigation highlights. It represents growth and stability.
- **Background/Secondary (#FDFCF5):** A soft cream (book-paper) background replaces harsh pure whites to reduce eye strain during long administrative sessions.
- **Neutral (#4B5563):** A balanced slate-gray used for secondary text and borders to maintain high legibility without the jarring contrast of pure black.
- **Functional Colors:** Clear, high-occupancy colors are used for status indication: Blue for informational cues, Red for high-priority overdue alerts, and Amber for warnings.

## Typography

The design system employs **Hanken Grotesk** as the sole typeface. Chosen for its exceptional legibility and contemporary professional feel, it provides the "Pretendard-like" clarity required for data-heavy administrative tasks.

- **Scale:** A systematic scale ensures that hierarchical information—like book titles versus ISBN numbers—is immediately distinguishable.
- **Labels:** Small, uppercase labels are used for metadata headers in table views to maximize vertical space while maintaining readability.
- **Weights:** Use Medium (500) or SemiBold (600) for interactive elements and Regular (400) for all body copy and descriptions.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy for the main content area, centered on the screen to maintain the feel of a dedicated desktop tool.

- **Grid:** A 12-column grid is used for desktop views. Most administrative panels will span 12 columns for tables, or an 8/4 split for master-detail views (e.g., book list on the left, book details on the right).
- **Rhythm:** A 4px baseline grid ensures tight, disciplined spacing between inputs and labels.
- **Internal Padding:** Cards and containers use generous internal padding (24px) to ensure the UI feels "breathable" despite the density of information.
- **Adaptive Strategy:** On tablets, the side navigation collapses into a rail. On mobile, the grid reflows to a single column with 16px horizontal margins.

## Elevation & Depth

To maintain a professional, administrative atmosphere, the design system avoids heavy shadows in favor of **Tonal Layers** and **Low-Contrast Outlines**.

- **Surface Levels:** 
  - Level 0: Background (Cream #FDFCF5).
  - Level 1: Primary Cards (White #FFFFFF with a 1px border of #E5E7EB).
  - Level 2: Popovers and Modals (White #FFFFFF with a soft 12% opacity neutral shadow).
- **Interaction:** Buttons and interactive cards use a subtle "lift" effect (very slight shadow) on hover to indicate clickability without breaking the flat, structured aesthetic.

## Shapes

The design system uses a **Soft (0.25rem)** roundedness level. This provides a balance between the precision of a professional tool and the approachability of a neighborhood library.

- **Standard Elements:** Buttons, input fields, and status badges use the 4px (0.25rem) radius.
- **Containers:** Large content cards and modals use the 8px (0.5rem) radius to define clear boundaries.
- **Status Badges:** These are the only exception where "pill-shaped" (full-round) corners can be used to distinguish them from interactive buttons.

## Components

- **Buttons:** 
  - *Primary:* Solid Deep Green (#2D5A27) with White text. Bold and authoritative.
  - *Secondary:* Ghost style with Deep Green borders and text for less urgent actions like "Export" or "Filter".
- **Status Badges:** 
  - *Borrowing:* Soft Blue background with Dark Blue text.
  - *Returned:* Soft Green background with Deep Green text.
  - *Overdue:* Soft Red background with Dark Red text.
- **Tables:** High-density rows with light horizontal dividers. The header row should have a subtle grey background (#F3F4F6) to anchor the data.
- **Input Fields:** Outlined style using #D1D5DB borders. On focus, the border transitions to the Primary Green with a subtle 2px outer glow.
- **Cards:** Used for grouping book details or member profiles. They should feature a 1px border and no shadow, keeping the interface flat and organized.
- **Action Bar:** A persistent top bar within pages for global actions like "Add New Book" or "Global Search," utilizing the primary green for the most important button.