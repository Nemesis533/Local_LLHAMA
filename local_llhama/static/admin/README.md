# Admin Panel JavaScript Modules

The admin panel JavaScript has been refactored from a single 1050-line file into modular, maintainable components.

## Structure

```
local_llhama/static/
├── admin-main.js                    # Main entry point, coordinates modules
└── admin/
    ├── utils.js                     # Common utilities (escapeHtml, formatDate, etc.)
    ├── user-management.js           # User CRUD, permissions, password reset
    ├── language-management.js       # TTS language-to-voice mappings
    ├── prompt-management.js         # LLM prompt templates
    ├── websearch-management.js      # Web search config & allowed sites
    └── preset-management.js         # Configuration presets & system restart
```

## Module Responsibilities

### `admin-main.js` (105 lines)
- Entry point loaded by admin.html
- Imports all modules
- Exposes functions to global scope for HTML onclick handlers
- Handles tab switching logic
- Initializes modules on page load

### `admin/utils.js` (52 lines)
- `formatDate()` - Format timestamps
- `escapeHtml()` - XSS protection
- `showError()` / `showSuccess()` - User notifications
- `closeModal()` - Modal management
- Modal click-outside handler

### `admin/user-management.js` (276 lines)
- `loadUsers()` - Fetch and display users
- `showCreateUserModal()` - Open create user dialog
- `createUser()` - Create new user account
- `editPermissions()` - Modify user permissions
- `updatePermissions()` - Save permission changes
- `resetPassword()` - Generate new temporary password
- `deleteUser()` - Remove user account
- `initUserManagement()` - Set up event listeners

### `admin/language-management.js` (173 lines)
- `loadLanguageSettings()` - Load voice models and mappings
- `displayLanguageMappings()` - Render language list
- `addLanguageMapping()` - Add new language
- `updateLanguageCode()` - Change language code
- `updateLanguageModel()` - Change voice model
- `removeLanguageMapping()` - Delete language
- `saveLanguageModels()` - Persist to server

### `admin/prompt-management.js` (199 lines)
- `loadPromptsData()` - Fetch prompt templates
- `displayPrompts()` - Render prompt editors
- `togglePromptBody()` - Expand/collapse prompt
- `updatePromptDescription()` - Change prompt description
- `updatePromptValue()` - Edit prompt content
- `insertTemplateVariable()` - Insert {variable} at cursor
- `savePrompts()` - Persist to server

### `admin/websearch-management.js` (208 lines)
- `loadWebSearchConfig()` - Fetch web search settings
- `displayWebSearchConfig()` - Render config form
- `displayWebsites()` - Show allowed websites list
- `addWebsite()` - Add new allowed site
- `editWebsite()` - Modify existing site
- `deleteWebsite()` - Remove site
- `togglePasswordVisibility()` - Show/hide API keys
- `saveWebSearchConfig()` - Persist to server

### `admin/preset-management.js` (200 lines)
- `loadPresets()` - Fetch presets and current config
- `displayCurrentConfig()` - Show active configuration
- `displayPresets()` - Render preset cards
- `loadPresetDetails()` - Fetch detailed preset info
- `applyPreset()` - Apply configuration preset
- `restartSystem()` - Restart Local LLHAMA system

## Benefits of Modular Structure

1. **Maintainability** - Each module has a single responsibility
2. **Readability** - ~200 lines per module vs 1050 in one file
3. **Testability** - Modules can be tested independently
4. **Reusability** - Common utilities shared via imports
5. **Collaboration** - Multiple developers can work on different modules
6. **Debugging** - Easier to locate and fix issues
7. **Performance** - Browser can cache modules separately

## Migration Notes

- Old file backed up as `admin.js.backup`
- HTML template updated to load `admin-main.js` as ES6 module
- All onclick handlers still work via window object exposure
- No changes required to admin.html structure
- All functionality preserved from original implementation

## Development

To modify admin panel functionality:
1. Locate the relevant module (user, language, prompt, websearch, or preset)
2. Edit the module file in `local_llhama/static/admin/`
3. Changes take effect on page reload (no build step required)
4. Use browser DevTools to debug individual modules
