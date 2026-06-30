# Widget Toolkit Setup for Agentic App Developers

This agentic app seed includes the **@claritty/widget-toolkit** - an Apple HIG-compliant widget system that enforces consistent dimensions, typography, and accessibility standards.

## 🔑 One-Time Setup Required

Before running `npm install`, you need to authenticate with GitHub Packages:

### Step 1: Create GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Give it a name like "Clarity Widget Toolkit"
4. Select scope: **`read:packages`** ✅
5. Click **"Generate token"** and **copy it**

### Step 2: Set Environment Variable

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`, or `~/.profile`):

```bash
export GITHUB_TOKEN=your_token_here
```

Then reload your shell:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

### Step 3: Install Dependencies

```bash
cd frontend
npm install
```

The `.npmrc` file is already configured to use GitHub Packages for `@claritty/widget-toolkit`.

## 📦 What's Included

The widget toolkit provides:

### **WidgetContainer** - Automatic dimension enforcement
- **Small**: 190×190px (1:1 square)
- **Large**: 400×190px (2.1:1 wide)
- Enforces 22px border radius
- Automatic overflow handling

### **WidgetButton** - Touch target enforcement
- Minimum 44×44px (Apple HIG requirement)
- Three variants: primary, secondary, ghost
- Automatic sizing

### **Typography Utilities** (`widgetText`)
```typescript
widgetText.display    // 48px, weight 900
widgetText.headline   // 20px, weight 700
widgetText.subheadline // 16px, weight 600
widgetText.body       // 14px, weight 500
widgetText.caption    // 12px, weight 500 (minimum)
widgetText.footnote   // 10px, weight 400
```

### **Gradient Presets** (`widgetGradients`)
20+ beautiful Apple-style gradients:
- `sunset`, `ocean`, `lavender`, `mint`, `ruby`
- And 15 more!

### **Spacing & Animations**
- Apple-standard spacing scale
- iOS-style animation curves
- Framer Motion utilities

## 🚀 Quick Start

```tsx
import {
  WidgetContainer,
  WidgetButton,
  widgetText,
  widgetGradients
} from '@claritty/widget-toolkit';

export default function MyWidget({ size = 'large' }: { size: 'small' | 'large' }) {
  return (
    <WidgetContainer
      size={size}
      padding="default"
      className={widgetGradients.sunset}
    >
      <div className="flex flex-col gap-3">
        <div className={widgetText.display}>42</div>
        <div className={widgetText.caption}>Active Users</div>

        {size === 'large' && (
          <WidgetButton variant="primary">View Details</WidgetButton>
        )}
      </div>
    </WidgetContainer>
  );
}
```

## ✅ Validation

Validate your widget meets Apple HIG standards:

```bash
npx @claritty/widget-toolkit validate src/components/Widget.tsx
```

Checks:
- ✅ Dimensions (190×190 or 400×190)
- ✅ Padding ≥ 12px
- ✅ Font sizes ≥ 12px
- ✅ Touch targets ≥ 44px
- ✅ Border radius = 22px

## 📖 Full Documentation

See `WIDGET_DEVELOPMENT_GUIDELINES.md` for:
- Complete API reference
- Design guidelines
- Example widgets
- Best practices
- Common mistakes to avoid

## 🔧 Troubleshooting

### Error: 404 Not Found - @claritty/widget-toolkit

**Problem**: Package not found on GitHub Packages

**Solution**:
1. Make sure you set `GITHUB_TOKEN` environment variable
2. Verify token has `read:packages` scope
3. Check `.npmrc` file exists in `frontend/` folder:
   ```
   @claritty:registry=https://npm.pkg.github.com
   ```

### Error: need auth

**Problem**: Not authenticated with GitHub Packages

**Solution**:
```bash
npm login --registry=https://npm.pkg.github.com
# Username: your-github-username
# Password: paste-your-github-token
# Email: your-email@example.com
```

### Package installs but imports fail

**Problem**: TypeScript can't find module

**Solution**:
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

## 🆘 Support

For issues with the widget toolkit:
- Check the [Widget Toolkit GitHub Repo](https://github.com/claritty/widget-toolkit)
- Review `WIDGET_DEVELOPMENT_GUIDELINES.md`
- Contact platform team

## 🔄 Updating the Toolkit

To get the latest version:

```bash
cd frontend
npm update @claritty/widget-toolkit
```

Check current version:
```bash
npm list @claritty/widget-toolkit
```
