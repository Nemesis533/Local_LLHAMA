# Security Migration Guide

## Overview
This document describes the security improvements made to move sensitive configuration from the JSON settings file to environment variables.

## Changes Made

### 1. Environment Variables (.env)
Created `.env` file to store security-sensitive configuration:
- `HA_BASE_URL` - Home Assistant server URL
- `HA_TOKEN` - Home Assistant API authentication token
- `OLLAMA_IP` - Ollama server IP address and port
- `ALLOWED_IP_PREFIXES` - Comma-separated list of allowed IP prefixes for web UI access

### 2. Files Modified

#### `/local_llhama/Settings_Loader.py`
- Added `import os` and `from dotenv import load_dotenv`
- Added `load_dotenv()` in `__init__` to load environment variables
- Modified `load_llm_models()` to read `OLLAMA_IP` from environment variable

#### `/local_llhama/Home_Assistant_Interface.py`
- Added `import os` and `from dotenv import load_dotenv`
- Modified `HomeAssistantClient.__init__()` to:
  - Load environment variables with `load_dotenv()`
  - Read `HA_BASE_URL` from environment (defaults to empty string)
  - Read `HA_TOKEN` from environment (defaults to empty string)

#### `/local_llhama/Web_Server.py`
- Added `import os` and `from dotenv import load_dotenv`
- Modified `LocalLLHAMA_WebService.__init__()` to:
  - Load environment variables with `load_dotenv()`
  - Read `ALLOWED_IP_PREFIXES` from environment (defaults to '192.168.88.,127.0.0.1')
  - Parse comma-separated IP prefixes into a list

#### `/local_llhama/settings/object_settings.json`
Removed sensitive configuration:
- ❌ `HomeAssistantClient.base_url`
- ❌ `HomeAssistantClient.token`
- ❌ `LocalLLMChecker.ALLOWED_IP_PREFIXES` (entire section removed)
- ❌ `SettingLoaderClass.ollama_ip`

Kept non-sensitive configuration:
- ✅ Model paths and names
- ✅ Feature flags (use_guard_llm, use_ollama, etc.)
- ✅ Device lists (allowed_entities, ALLOWED_DOMAINS)
- ✅ Model settings (ollama_model name)

#### `/requirements.txt`
- Added `python-dotenv` package for loading environment variables from `.env` file

#### `/README.md`
- Added installation step #3 for configuring environment variables
- Added new "Configuration" section explaining environment variables
- Updated references from "settings file" to ".env file" where appropriate
- Removed sensitive values from example JSON snippets

### 3. Files Created

#### `/.env.example`
Template file showing the structure of required environment variables with placeholder values. Safe to commit to version control.

#### `/.env`
Actual environment file with your sensitive values. **Already gitignored** - will not be committed.

## Migration Steps for Users

If you're updating from a previous version:

1. **Copy your existing values**:
   From your old `object_settings.json`, note these values:
   - `HomeAssistantClient.base_url` → `HA_BASE_URL`
   - `HomeAssistantClient.token` → `HA_TOKEN`
   - `SettingLoaderClass.ollama_ip` → `OLLAMA_IP`
   - `LocalLLMChecker.ALLOWED_IP_PREFIXES` → `ALLOWED_IP_PREFIXES` (comma-separated)

2. **Create your .env file**:
   ```bash
   cp .env.example .env
   ```

3. **Edit .env with your values**:
   ```bash
   nano .env  # or use your preferred editor
   ```

4. **Install python-dotenv**:
   ```bash
   pip install python-dotenv
   ```
   Or reinstall all requirements:
   ```bash
   pip install -r requirements.txt
   ```

5. **Verify the configuration**:
   The system will now load these values from environment variables instead of the JSON file.

## Security Benefits

1. **Secrets not in version control**: The `.env` file is gitignored, so tokens won't be accidentally committed
2. **Easier credential rotation**: Change credentials in one place without modifying code
3. **Environment-specific configs**: Different .env files for dev/staging/production
4. **Industry standard**: Using .env files is a widely accepted best practice
5. **Reduced exposure**: Sensitive data separated from application configuration

## Backward Compatibility

The system maintains backward compatibility:
- If environment variables are not set, default values are used
- The `object_settings.json` can still override non-sensitive settings
- Existing functionality is preserved

## Troubleshooting

**Issue**: Home Assistant connection fails
- **Solution**: Verify `HA_BASE_URL` and `HA_TOKEN` are correctly set in `.env`

**Issue**: Web UI rejects connections
- **Solution**: Check `ALLOWED_IP_PREFIXES` includes your network's IP range

**Issue**: Ollama not connecting
- **Solution**: Verify `OLLAMA_IP` is set correctly in `.env`

**Issue**: "No module named 'dotenv'" error
- **Solution**: Install python-dotenv: `pip install python-dotenv`
