# Admin Panel CSS Modules

## Overview
The admin panel CSS has been modularized into separate files by functional area, making styles easier to maintain and understand.

## Module Structure

### admin.css (Main Import File)
Imports all admin CSS modules in the correct order. This is the only CSS file that needs to be linked in the HTML template.

```css
@import 'admin/admin-layout.css';
@import 'admin/admin-tables.css';
@import 'admin/admin-forms.css';
@import 'admin/admin-tabs.css';
@import 'admin/admin-presets.css';
@import 'admin/admin-prompts.css';
```

### admin-layout.css (2,308 bytes)
- `.admin-container` - Main container layout
- `.admin-header` - Header section with title and buttons
- `.header-buttons` - Button group styling
- `.logout-btn` - Logout button styles
- `.language-mapping` - Language configuration rows
- `.btn-*` variants - Success, danger, primary buttons

### admin-tables.css (2,122 bytes)
- `.users-table-container` - Table wrapper with scrolling
- `.users-table` - User management table styles
- `.badge-*` - Status and permission badges (yes, no, admin, warning)
- `.action-buttons` - Button group in table cells
- `.btn-small` - Small action buttons (edit, reset, delete)

### admin-forms.css (2,454 bytes)
- `.modal` - Modal overlay
- `.modal-content` - Modal dialog box
- `.modal-header` - Modal title section
- `.form-group` - Form field wrapper
- `.form-group-checkbox` - Checkbox with label
- `.modal-buttons` - Modal action buttons
- `.password-display` - Password reveal styling

### admin-tabs.css (986 bytes)
- `.tab-navigation` - Tab button container
- `.tab-button` - Individual tab buttons
- `.tab-button.active` - Active tab highlighting
- `.tab-content` - Tab panel containers

### admin-presets.css (7,350 bytes)
- `.preset-card` - Individual preset cards
- `.preset-card.recommended` - Recommended preset badge
- `.preset-card.active` - Currently active preset (with pulse animation)
- `.preset-description` - Scrollable description text
- `.preset-specs` - Technical specifications list
- `.preset-requirements` - System requirements box
- `.preset-buttons-container` - Bottom button area
- `.preset-apply-btn` - Apply preset button
- `.preset-details-toggle` - Expandable details button
- `.preset-details-content` - Hidden details section
- `.preset-card.create-new` - Create new preset card
- `@keyframes pulse-glow` - Active preset animation

### admin-prompts.css (1,847 bytes)
- `.prompt-editor` - Prompt configuration container
- `.prompt-header` - Collapsible header
- `.prompt-body` - Prompt input area
- `.prompt-description` - Descriptive text
- `.template-variables` - Template variable buttons
- `.template-var-btn` - Individual variable button
- `.template-var-info` - Template variable help text

## Design System

All modules use CSS custom properties from `main.css`:

- **Colors**: `--color-primary`, `--color-secondary`, `--color-success`, etc.
- **Spacing**: `--space-xs` through `--space-2xl`
- **Typography**: `--font-size-*`, `--font-weight-*`
- **Borders**: `--radius-sm`, `--radius-md`, `--border-light`
- **Transitions**: `--transition-base`

## Adding New Styles

1. Identify the appropriate module for your styles
2. Add styles to that module (or create new module if needed)
3. If creating new module:
   - Create file in `static/css/admin/`
   - Add `@import` statement to `admin.css`
4. Use existing CSS custom properties for consistency

## Performance

- Total CSS size: ~19KB (uncompressed)
- Modular loading allows browser caching
- CSS is minified in production
- Import order ensures specificity cascade

## Migration from Inline Styles

All inline styles from the original 1072-line `admin.html` have been:
- Extracted to appropriate CSS modules
- Converted to use CSS custom properties
- Organized by component/functionality
- Deduplicated where possible
