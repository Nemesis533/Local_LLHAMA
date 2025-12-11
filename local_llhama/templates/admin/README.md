# Admin Panel - Modular Template Structure

## Overview
The admin panel has been refactored from a monolithic 1072-line file into a clean, modular structure following the same pattern as the JavaScript refactoring.

## File Structure

### Main Template
- **admin.html** (43 lines) - Main container with header, navigation, and includes

### Tab Content Includes
Located in `templates/admin/`:
- **users-tab.html** - User management table and controls
- **presets-tab.html** - Configuration preset cards and current config display
- **languages-tab.html** - Text-to-speech language model configuration
- **prompts-tab.html** - LLM prompt configuration interface
- **websearch-tab.html** - Web search settings and API configuration
- **modals.html** - All modal dialogs (Create User, Edit Permissions, Reset Password, Create Preset)

### CSS Modules
Located in `static/css/admin/`:
- **admin.css** - Main import file (loads all modules)
- **admin-layout.css** - Container, header, buttons, general layout
- **admin-tables.css** - Users table styles, badges, action buttons
- **admin-forms.css** - Modal and form styles, password display
- **admin-tabs.css** - Tab navigation and content panel styles
- **admin-presets.css** - Preset cards, details expansion, create-new card
- **admin-prompts.css** - Prompt editor and template variable styles

## Benefits of Modular Structure

1. **Maintainability**: Each component isolated in its own file
2. **Readability**: Small, focused files (43-302 lines vs 1072 lines)
3. **Reusability**: CSS modules can be imported independently
4. **Consistency**: Follows same pattern as JavaScript refactoring
5. **Scalability**: Easy to add new tabs or features
6. **Team Collaboration**: Multiple developers can work on different modules

## Usage

### Adding a New Tab

1. Create tab content template in `templates/admin/your-tab.html`
2. Add include to `admin.html`:
   ```jinja2
   {% include 'admin/your-tab.html' %}
   ```
3. Add tab button to navigation section
4. Create corresponding CSS if needed in `static/css/admin/your-tab.css`
5. Import CSS in `admin.css`

### Adding a New Modal

1. Add modal HTML to `templates/admin/modals.html`
2. Ensure modal uses existing CSS classes or add styles to `admin-forms.css`
3. Add JavaScript handlers in `admin-main.js` or appropriate module

## Backup

Original admin.html backed up to: `templates/admin.html.backup`

## Statistics

- **Before**: 1072 lines in single file
- **After**: 
  - Main template: 43 lines
  - Tab includes: 6 files (664-10,163 bytes)
  - CSS modules: 6 files (986-7,350 bytes)
  - Total reduction: ~96% in main file
