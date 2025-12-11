# CSS Modular Architecture

The CSS has been refactored from a single 1079-line file into modular, maintainable stylesheets with a centralized design system.

## Structure

```
local_llhama/static/
├── main.css                         # Main entry point (imports all modules)
└── css/
    ├── variables.css                # Design tokens & color palette
    ├── base.css                     # Reset & foundational styles
    ├── layout.css                   # Layout containers & grid
    ├── header.css                   # Header & navigation
    ├── buttons.css                  # All button variants
    ├── dashboard.css                # Dashboard, settings, logs
    ├── chat.css                     # Chat interface & messages
    ├── calendar.css                 # Calendar sidebar & events
    ├── modal.css                    # Modal dialogs & forms
    └── scrollbar.css                # Custom scrollbars
```

## File Breakdown

### `css/variables.css` (133 lines)
**Purpose:** Centralized design system with CSS custom properties

**Contains:**
- Color palette (primary, secondary, semantic colors)
- Neutral and slate gray scales
- Text, background, and border colors
- Spacing scale (xs to 2xl)
- Typography (fonts, sizes, weights)
- Border radius values
- Shadow definitions
- Z-index scale
- Transition timings

**Usage:**
```css
background: var(--color-primary);
padding: var(--space-md);
border-radius: var(--radius-lg);
```

### `css/base.css` (38 lines)
**Purpose:** CSS reset and foundational styles

**Contains:**
- Box-sizing reset
- Body/HTML base styles
- Typography resets
- Form element defaults

### `css/layout.css` (57 lines)
**Purpose:** Page structure and container layouts

**Contains:**
- `.container` - Main page container
- `.dashboard` - Dashboard flex layout
- `#settings-dashboard` - Settings panel
- `#logs-section` - Logs container
- Common panel styles

### `css/header.css` (79 lines)
**Purpose:** Header, navigation, and top bar

**Contains:**
- `.header` - Main header wrapper
- `.header-content` - Header flex container
- `.header-title` - Logo and title area
- `.header-nav` - Navigation buttons
- `.nav-btn` - Navigation button styles
- `.logout-btn` - Logout button

### `css/buttons.css` (179 lines)
**Purpose:** All button variants and states

**Contains:**
- `.btn` - Generic button
- `.btn-save` / `.btn-restart` - Action buttons
- `.btn-icon` - Icon-only buttons
- `.send-btn` / `.send-chat-btn` - Send buttons
- `.btn-cancel` / `.btn-submit` - Modal buttons
- `.delete-event-btn` - Danger/delete buttons
- `.settings-actions` - Button groups

### `css/dashboard.css` (214 lines)
**Purpose:** Dashboard-specific components

**Contains:**
- `.settings-scroll` - Settings panel scroll area
- `.settings-section` - Setting groups
- `.setting-input` - Input fields
- `.log-box` - Log display container
- Log message type classes (`.main-line`, `.log-info`, etc.)
- `.prompt-input` - Prompt textarea
- `.loading-container` - Loading screen
- `.loading-spinner` - Spinner animation

### `css/chat.css` (236 lines)
**Purpose:** Chat interface and message styles

**Contains:**
- `.chat-layout` - Chat page flex layout
- `.chat-sidebar` - Conversation sidebar
- `.chat-main` - Main chat area
- `.chat-messages` - Messages container
- `.chat-message` - Individual message bubble
- `.user-message` / `.assistant-message` - Message variants
- `.message-content` - Message body with code blocks
- `.loading-message` - Typing indicator
- `.chat-input-container` - Input area
- `.chat-input` - Message input field

### `css/calendar.css` (150 lines)
**Purpose:** Calendar sidebar and event cards

**Contains:**
- `.calendar-sidebar` - Calendar side panel
- `.calendar-header` - Calendar header bar
- `.calendar-events` - Events list container
- `.calendar-event` - Event card
- `.event-header` / `.event-title` - Event content
- `.event-type-badge` - Event type indicators
- `.repeat-badge` - Recurring event badge
- Event type variants (reminder, appointment, alarm)

### `css/modal.css` (117 lines)
**Purpose:** Modal dialogs and form styles

**Contains:**
- `.modal` - Modal overlay
- `.modal-content` - Modal window
- `.close` - Close button
- `.form-group` - Form field wrapper
- `.form-group input/select/textarea` - Form controls
- `.form-actions` - Button container
- `.error-text` - Error messages

### `css/scrollbar.css` (100 lines)
**Purpose:** Custom scrollbar styling for all containers

**Contains:**
- Settings panel scrollbar
- Log box scrollbar
- Chat messages scrollbar
- Calendar events scrollbar
- Chat history scrollbar

## Design System (CSS Variables)

### Colors
All colors are defined as CSS custom properties in `variables.css`:

**Primary Palette:**
- `--color-primary` (#3b82f6) - Blue
- `--color-success` (#10b981) - Green
- `--color-warning` (#fbbf24) - Yellow
- `--color-danger` (#ef4444) - Red

**Grays:**
- `--color-gray-50` to `--color-gray-900` - Neutral grays
- `--color-slate-50` to `--color-slate-900` - Slate grays

**Semantic:**
- `--text-primary`, `--text-secondary`, `--text-muted`
- `--bg-primary`, `--bg-secondary`, `--bg-hover`
- `--border-light`, `--border-medium`, `--border-dark`

### Spacing
Consistent spacing scale:
- `--space-xs` (4px)
- `--space-sm` (8px)
- `--space-md` (16px)
- `--space-lg` (24px)
- `--space-xl` (32px)
- `--space-2xl` (48px)

### Typography
- Font family: Segoe UI stack
- Sizes: `--font-size-xs` to `--font-size-3xl`
- Weights: `--font-weight-normal` to `--font-weight-bold`

## Benefits

1. **Maintainability** - Find styles by component, not by scrolling
2. **Reusability** - Design tokens ensure consistency
3. **Modularity** - Each file has a single responsibility
4. **Scalability** - Easy to add new component styles
5. **Performance** - Browser can cache modules separately
6. **Theming** - Change colors globally via variables
7. **Collaboration** - Multiple developers can work on different modules
8. **Debugging** - Browser DevTools show source file names

## Migration Notes

- Original file backed up as `styles.css.backup`
- HTML template updated to load `main.css`
- All styles preserved from original implementation
- No visual changes - pixel-perfect match
- CSS custom properties for easy theming

## Development Workflow

To modify styles:

1. **Locate the component** - Use the structure guide above
2. **Edit the module** - Modify the appropriate CSS file in `local_llhama/static/css/`
3. **Use design tokens** - Reference CSS variables for colors, spacing, etc.
4. **Test** - Reload page (no build step required)
5. **Debug** - Browser DevTools show individual module names

## Theming

To customize colors, edit `css/variables.css`:

```css
:root {
  --color-primary: #your-brand-color;
  --color-success: #your-success-color;
  /* etc. */
}
```

All components will automatically use the new colors.

## Browser Support

- Modern browsers with CSS custom properties support
- Chrome, Firefox, Safari, Edge (all recent versions)
- CSS @import is well-supported
- No build step or preprocessor required
