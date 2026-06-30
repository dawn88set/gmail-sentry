# Migration Guide: Embedded SDK → PyPI Package

## Overview

The Clarity SDK has been published to PyPI as a professional Python package. This migration eliminates SDK bloat from every app and enables centralized updates.

## What Changed

### Before (Embedded SDK)
```
agentic-app-seed/
├── claritty_sdk/          # 2,652 lines embedded in every app
│   ├── agent.py
│   ├── workflow.py
│   └── ... (12 files)
├── backend/
│   ├── requirements.txt  # -e ../claritty_sdk
│   └── ...
```

### After (PyPI Package)
```
agentic-app-seed/
├── backend/
│   ├── requirements.txt  # claritty-sdk>=1.0.0,<2.0.0
│   └── ...
```

**SDK is now installed like any other package:**
```bash
pip install claritty-sdk
```

## Migration Steps for Existing Apps

If you have an existing app built with the old template:

### 1. Update requirements.txt

**Old:**
```txt
# Clarity SDK (local development)
-e ../claritty_sdk
```

**New:**
```txt
# Clarity SDK (from PyPI)
claritty-sdk>=1.0.0,<2.0.0
```

### 2. Remove claritty_sdk Directory

```bash
cd your-app
rm -rf claritty_sdk
```

### 3. Install SDK from PyPI

```bash
pip uninstall claritty-sdk  # Remove old editable install if exists
pip install claritty-sdk
```

### 4. Verify Imports Still Work

Your code doesn't need to change - imports remain the same:

```python
from claritty_sdk import agent, BaseAgent, AgentResult, AgentContext
from claritty_sdk import workflow, uses_agent, ExecutionMode
from claritty_sdk import trigger_template, TriggerTemplateType
```

### 5. Test Your App

```bash
./start.sh  # Or your usual startup command
```

## Benefits of PyPI Package

### ✅ **For You (Developer)**
- **No SDK bloat**: 2,652 lines removed from your repo
- **Easy updates**: `pip install --upgrade claritty-sdk`
- **Version pinning**: Specify compatible versions (e.g., `>=1.0.0,<2.0.0`)
- **Standard workflow**: Same as django, fastapi, etc.

### ✅ **For Clarity Platform**
- **Centralized updates**: Bug fixes reach all apps instantly
- **Security patches**: Fast distribution of critical fixes
- **Version management**: Track SDK compatibility
- **Marketplace validation**: Verify apps meet SDK requirements

## Version Compatibility

The SDK follows [Semantic Versioning](https://semver.org/):

| Version | Meaning | Upgrade Safety |
|---------|---------|----------------|
| `1.0.0` | Initial release | - |
| `1.1.0` | New features (backward compatible) | ✅ Safe |
| `1.2.0` | More features (backward compatible) | ✅ Safe |
| `2.0.0` | Breaking changes | ⚠️ Review changelog |

### Recommended Version Pinning

```txt
# Pin to major version (allows minor updates, patches)
claritty-sdk>=1.0.0,<2.0.0

# Pin to minor version (allows patches only)
claritty-sdk>=1.1.0,<1.2.0

# Exact version (no automatic updates)
claritty-sdk==1.0.0
```

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'claritty_sdk'"

**Cause**: SDK not installed or old editable install interfering

**Solution**:
```bash
pip uninstall claritty-sdk  # Remove any old version
pip install claritty-sdk    # Install from PyPI
```

### Issue: "Cannot import name 'agent' from 'claritty_sdk'"

**Cause**: Old cached files or wrong SDK version

**Solution**:
```bash
pip install --upgrade --force-reinstall claritty-sdk
```

### Issue: Imports work but decorators fail

**Cause**: Incompatible SDK version

**Solution**:
Check your requirements.txt has the correct version range:
```txt
claritty-sdk>=1.0.0,<2.0.0
```

## Development Workflow

### Local SDK Development (Advanced)

If you're contributing to the SDK itself:

```bash
# Clone SDK repository
git clone https://github.com/Clarittyai/claritty-sdk.git
cd claritty-sdk

# Install in editable mode
pip install -e .

# Work on your app - uses local SDK
cd /path/to/your-app
# Changes to SDK reflect immediately
```

When done:
```bash
# Switch back to PyPI version
pip uninstall claritty-sdk
pip install claritty-sdk
```

## FAQ

**Q: Do I need to change my code?**
**A**: No! Imports remain exactly the same.

**Q: What if I customized the SDK?**
**A**: Fork the [SDK repository](https://github.com/Clarittyai/claritty-sdk) and install from GitHub:
```bash
pip install git+https://github.com/your-username/claritty-sdk.git@your-branch
```

**Q: How do I see the SDK source code?**
**A**:
- View on GitHub: https://github.com/Clarittyai/claritty-sdk
- View locally: `python -c "import claritty_sdk; print(claritty_sdk.__file__)"`

**Q: Can I still use the old embedded SDK?**
**A**: Not recommended. The embedded version won't receive updates or security patches.

**Q: What if PyPI is down?**
**A**: Pip caches packages. Once installed, works offline. For critical environments, consider a private PyPI mirror.

## Support

- **Issues**: https://github.com/Clarittyai/claritty-sdk/issues
- **Discussions**: https://github.com/Clarittyai/claritty-sdk/discussions
- **Documentation**: https://github.com/Clarittyai/claritty-sdk#readme

---

**Migration complete!** 🎉 Your app now uses the professional PyPI package.
