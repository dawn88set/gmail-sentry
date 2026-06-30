# Widget Testing Guide

Complete guide for testing widget components to ensure they meet Apple-style design standards.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Validation Script](#validation-script)
4. [Unit Tests](#unit-tests)
5. [Visual Tests](#visual-tests)
6. [Pre-Commit Hooks](#pre-commit-hooks)
7. [CI/CD Integration](#cicd-integration)
8. [Troubleshooting](#troubleshooting)

---

## Overview

Widget testing ensures your widgets meet the following Apple standards:

- **Small Widget**: 170×170px (1:1 ratio - SQUARE)
- **Large Widget**: 360×170px (2.1:1 ratio - WIDE RECTANGLE)
- **Padding**: 16px (p-4) constant across all widgets
- **Border Radius**: 24px (rounded-3xl) Apple-style corners
- **Overflow**: Hidden to prevent scrollbars

### Testing Pyramid

```
          /\
         /  \  Visual Tests (Playwright)
        /____\
       /      \
      /  Unit  \  Unit Tests (Vitest)
     /  Tests  \
    /___________\
   /             \
  /  Validation  \  CLI Validation Script
 /_________________\
```

**Bottom Layer**: Quick static analysis (< 1 second)
**Middle Layer**: Component behavior tests (< 30 seconds)
**Top Layer**: Visual regression tests (~ 2 minutes)

---

## Quick Start

### Install Dependencies

```bash
cd frontend

# Install test frameworks
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom jsdom
npm install --save-dev @playwright/test

# Initialize Playwright
npx playwright install
```

### Run All Tests

```bash
# Quick validation (< 1 second)
npm run validate:widgets

# Unit tests (< 30 seconds)
npm run test:widgets

# Visual tests (~ 2 minutes)
npm run test:visual

# Run everything
npm run test:all
```

---

## Validation Script

### Purpose

The CLI validation script (`scripts/validate-widgets.js`) performs static analysis of your Widget.tsx code to ensure it follows Apple standards.

### What It Checks

✅ Small widget has `w-[170px] h-[170px]` classes
✅ Large widget has `w-[360px] h-[170px]` classes
✅ Both widgets have `p-4` (16px padding)
✅ Both widgets have `rounded-3xl` (24px border radius)
✅ Both widgets have `overflow-hidden`
✅ Widget size prop is typed as `"small" | "large"` (no "medium")
✅ `data-widget-size` attribute exists for testing

### Running the Script

```bash
# From project root
npm run validate:widgets

# Or directly
node scripts/validate-widgets.js

# From anywhere
./scripts/validate-widgets.js
```

### Example Output

```
🔍 Validating widget constraints...

✅ Small widget: 170×170px square (correct)
✅ Large widget: 360×170px wide rectangle (correct)
✅ Padding: 16px (p-4) found
✅ Overflow: overflow-hidden set
✅ Border radius: 24px (rounded-3xl) found
✅ Test attributes: data-widget-size found
✅ Type safety: size prop restricted to "small" | "large"

==================================================

✅ All widget constraints validated!

Your widgets meet Apple-style design standards.
Ready for Clarity Marketplace submission.
```

### Failure Example

```
🔍 Validating widget constraints...

✅ Small widget: 170×170px square (correct)
❌ Large widget: Missing w-[360px] h-[170px]
   Expected: className="... w-[360px] h-[170px] ..."
✅ Padding: 16px (p-4) found
❌ Overflow: Missing overflow-hidden class
   CRITICAL: Add overflow-hidden to prevent content overflow

==================================================

❌ Widget validation FAILED

Fix the errors above before proceeding.
See docs/WIDGET_DESIGN_GUIDE.md for specifications.
```

---

## Unit Tests

### Purpose

Unit tests verify component behavior, data handling, and API integration using Vitest and React Testing Library.

### Test File Location

```
frontend/src/components/__tests__/Widget.test.tsx
```

### What It Tests

**Apple Standard Dimensions:**
- ✅ Small widget renders with exact 170×170px
- ✅ Large widget renders with exact 360×170px
- ✅ Both widgets have 16px padding (p-4)
- ✅ Both widgets have 24px border radius (rounded-3xl)
- ✅ Both widgets have overflow-hidden

**Data Loading:**
- ✅ Loading state displays correctly
- ✅ API called with correct size parameter
- ✅ Defaults to large size when no prop provided

**Error Handling:**
- ✅ Error state displays with correct dimensions
- ✅ Error message shown when fetch fails
- ✅ Error state maintains widget constraints

**Data Display:**
- ✅ Small widget shows minimal data
- ✅ Large widget shows detailed data
- ✅ Active triggers count displayed
- ✅ Success rate displayed
- ✅ Recent executions shown (large only)

**Auto-refresh:**
- ✅ 30-second refresh interval set
- ✅ Re-fetches when size prop changes

**Type Safety:**
- ✅ Only "small" or "large" accepted as size prop

### Running Unit Tests

```bash
cd frontend

# Run all tests
npm run test:widgets

# Watch mode (auto-rerun on changes)
npm run test:widgets -- --watch

# With coverage report
npm run test:widgets -- --coverage

# Run specific test
npm run test:widgets -- -t "renders small widget"
```

### Example Output

```
✓ frontend/src/components/__tests__/Widget.test.tsx (32)
  ✓ Apple Standard Dimensions (8)
    ✓ renders small widget with exact 170×170px dimensions
    ✓ renders large widget with exact 360×170px dimensions
    ✓ small widget has correct padding (16px = p-4)
    ✓ large widget has correct padding (16px = p-4)
    ✓ small widget has correct border radius (24px = rounded-3xl)
    ✓ large widget has correct border radius (24px = rounded-3xl)
    ✓ small widget has overflow-hidden class
    ✓ large widget has overflow-hidden class
  ✓ Data Loading (4)
  ✓ Error Handling (3)
  ✓ Data Display - Small Widget (2)
  ✓ Data Display - Large Widget (4)
  ✓ Auto-refresh Behavior (2)
  ✓ TypeScript Type Safety (1)

Test Files  1 passed (1)
     Tests  32 passed (32)
  Start at  10:30:15
  Duration  2.34s
```

---

## Visual Tests

### Purpose

Playwright visual tests verify actual rendered dimensions, overflow behavior, and visual appearance across different scenarios.

### Test File Location

```
frontend/tests/widget-constraints.spec.ts
```

### What It Tests

**Small Widget (170×170px Square):**
- ✅ Exact dimensions (170×170px)
- ✅ 1:1 aspect ratio
- ✅ 16px padding
- ✅ 24px border radius
- ✅ Overflow hidden
- ✅ No scrollbars
- ✅ Content within boundaries

**Large Widget (360×170px Wide Rectangle):**
- ✅ Exact dimensions (360×170px)
- ✅ 2.1:1 aspect ratio
- ✅ 16px padding
- ✅ 24px border radius
- ✅ Overflow hidden
- ✅ No scrollbars
- ✅ Content within boundaries

**Consistent Styling:**
- ✅ Both widgets have same padding
- ✅ Both widgets have same border radius
- ✅ Both widgets have overflow hidden

**Visual Regression:**
- ✅ Small widget snapshot
- ✅ Large widget snapshot

**Responsive Behavior:**
- ✅ Maintains dimensions on different screen sizes

**Loading & Error States:**
- ✅ Loading state maintains dimensions
- ✅ Error state maintains dimensions

### Running Visual Tests

```bash
cd frontend

# Run all visual tests
npm run test:visual

# Run in headed mode (see browser)
npm run test:visual -- --headed

# Run specific test
npm run test:visual -- -g "has exact dimensions"

# Update snapshots
npm run test:visual -- --update-snapshots

# Debug mode
npm run test:visual -- --debug
```

### Prerequisites

**Backend must be running:**
```bash
# In separate terminal
docker-compose up backend
```

**Frontend must be running:**
```bash
# In separate terminal
cd frontend && npm run dev
```

### Example Output

```
Running 24 tests using 3 workers

  ✓ [chromium] › widget-constraints.spec.ts:15:1 › Small Widget › has exact dimensions (1.2s)
  ✓ [chromium] › widget-constraints.spec.ts:30:1 › Small Widget › has 1:1 aspect ratio (0.9s)
  ✓ [chromium] › widget-constraints.spec.ts:45:1 › Small Widget › has 16px padding (0.8s)
  ✓ [chromium] › widget-constraints.spec.ts:65:1 › Small Widget › has 24px border radius (0.7s)
  ✓ [chromium] › widget-constraints.spec.ts:80:1 › Small Widget › has overflow hidden (0.6s)
  ✓ [chromium] › widget-constraints.spec.ts:95:1 › Small Widget › does not show scrollbars (0.8s)
  ✓ [chromium] › widget-constraints.spec.ts:110:1 › Small Widget › content does not overflow (1.1s)

  ... (17 more tests)

  24 passed (34.5s)
```

---

## Pre-Commit Hooks

Automatically run validation before commits to catch issues early.

### Setup with Husky

```bash
cd frontend

# Install husky
npm install --save-dev husky

# Initialize husky
npx husky install

# Add pre-commit hook
npx husky add .husky/pre-commit "npm run validate:widgets"
```

### Manual Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/sh

echo "🔍 Validating widget constraints..."

npm run validate:widgets

if [ $? -ne 0 ]; then
  echo "❌ Widget validation failed. Commit aborted."
  echo "Fix the errors above before committing."
  exit 1
fi

echo "✅ Widget validation passed!"
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## CI/CD Integration

### GitHub Actions Example

Create `.github/workflows/widget-tests.yml`:

```yaml
name: Widget Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Validate Widget Constraints
        run: |
          node scripts/validate-widgets.js

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: Run unit tests
        run: cd frontend && npm run test:widgets

  visual-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: Install Playwright
        run: cd frontend && npx playwright install --with-deps

      - name: Start services
        run: docker-compose up -d

      - name: Wait for services
        run: sleep 10

      - name: Run visual tests
        run: cd frontend && npm run test:visual

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

---

## Troubleshooting

### Validation Script Fails

**Issue**: Script can't find Widget.tsx

```bash
❌ Widget.tsx not found at: /path/to/Widget.tsx
```

**Solution**: Run from project root, not from scripts/ directory

```bash
# Wrong
cd scripts && ./validate-widgets.js

# Correct
./scripts/validate-widgets.js
# or
npm run validate:widgets
```

---

### Unit Tests Fail

**Issue**: Module not found errors

```
Error: Cannot find module '@/lib/api'
```

**Solution**: Ensure Vite path aliases are configured in `vite.config.ts`:

```typescript
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
});
```

---

### Visual Tests Fail

**Issue**: Widgets not found

```
Error: locator.boundingBox: Target closed
```

**Solution**: Ensure backend and frontend are running:

```bash
# Terminal 1: Start backend
docker-compose up backend

# Terminal 2: Start frontend
cd frontend && npm run dev

# Terminal 3: Run tests
cd frontend && npm run test:visual
```

---

### Snapshot Mismatch

**Issue**: Visual regression detected

```
Error: Screenshot comparison failed
```

**Solution**: Review changes and update snapshots if intentional:

```bash
# Review the diff
cd frontend/playwright-report && open index.html

# Update snapshots (if changes are correct)
npm run test:visual -- --update-snapshots
```

---

## Best Practices

### 1. Run Validation First

Always run the quick validation script before running slower tests:

```bash
npm run validate:widgets && npm run test:widgets && npm run test:visual
```

### 2. Use Watch Mode During Development

Keep tests running while developing:

```bash
npm run test:widgets -- --watch
```

### 3. Visual Tests on Clean State

Always start visual tests with a clean database state:

```bash
docker-compose down -v
docker-compose up -d
npm run test:visual
```

### 4. Update Snapshots Carefully

Only update snapshots when you've intentionally changed the visual appearance:

```bash
# Review changes first
git diff frontend/tests/__screenshots__/

# Update if correct
npm run test:visual -- --update-snapshots

# Commit new snapshots
git add frontend/tests/__screenshots__/
git commit -m "Update widget visual snapshots"
```

---

## Summary

✅ **Validation Script**: Quick static analysis (< 1 second)
✅ **Unit Tests**: Component behavior testing (< 30 seconds)
✅ **Visual Tests**: Actual rendering verification (~ 2 minutes)
✅ **Pre-Commit Hooks**: Automatic validation before commits
✅ **CI/CD**: Automated testing on every push

**Testing pyramid ensures**:
- Widgets meet Apple standards
- No visual regressions
- Consistent behavior across changes
- Marketplace submission requirements met

---

**Questions?** See [Widget Design Guide](WIDGET_DESIGN_GUIDE.md) for specifications or [API Reference](API.md) for backend integration.
