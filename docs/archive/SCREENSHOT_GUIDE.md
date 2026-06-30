# Widget Screenshot Capture Guide

This guide explains how to capture the required widget screenshots for Clarity Marketplace submission.

## Overview

Per CLAUDE.md requirements, the Smart Email Filter app requires **exactly 2 widget screenshots**:
- `widget-small.png` (300×150px approximate)
- `widget-large.png` (600×400px approximate)

These screenshots are **CRITICAL** because they are the primary interface users see in the Clarity Marketplace dashboard.

## Prerequisites

1. **App must be running** with all services healthy:
   ```bash
   docker-compose up -d
   docker ps  # Verify all containers are healthy
   ```

2. **Sample data must exist** in database:
   ```bash
   # Verify sample emails exist
   curl -s -H "Authorization: Bearer test-user" "http://localhost:8000/api/widget?size=small"
   # Should return: important_emails_today: 5, detection_accuracy: "100%"
   ```

3. **Frontend must be accessible**:
   ```bash
   curl -s http://localhost:3200/
   # Should return 200 OK
   ```

## Capturing Screenshots

### Method 1: Browser Developer Tools (Recommended)

#### Step 1: Access Widget Page
1. Open browser: http://localhost:3200
2. Navigate to the page displaying the widgets
3. Ensure widgets are fully loaded with real email data showing

#### Step 2: Capture Small Widget (300×150px)
1. Open browser DevTools (F12 or Right-click → Inspect)
2. Use element inspector to select the small widget container
3. In DevTools:
   - Set device toolbar to custom size: 300px × 150px
   - Or use element screenshot feature
4. Take screenshot showing:
   - ✅ "Important Today" count (should show 5)
   - ✅ "Accuracy" percentage (should show 100%)
   - ✅ "Last checked" timestamp
   - ✅ Alert indicator if important emails exist
5. Save as: `./screenshots/widget-small.png`

**Expected Visual Elements:**
- Blue gradient background (from-blue-50 to-indigo-50)
- Mail icon with "Smart Email Filter" title
- Large number showing important email count (orange if >0)
- Detection accuracy percentage in green
- Last checked timestamp at bottom

#### Step 3: Capture Large Widget (600×400px)
1. Switch to large widget view
2. Set viewport to at least 600px × 400px
3. Take screenshot showing:
   - ✅ Stats grid with 3 cards (Important Today, Emails Processed, Accuracy)
   - ✅ List of 5 recent important emails with:
     - Urgency indicator dots (red/orange/yellow/green)
     - Sender names (ceo@company.com, legal@company.com, etc.)
     - Subject lines
     - Importance scores
     - Urgency level badges (Critical, High, Medium, Low)
   - ✅ Last checked timestamp and "View All" button
4. Save as: `./screenshots/widget-large.png`

**Expected Visual Elements:**
- Same blue gradient background theme
- 3-column stats grid at top
- "Recent Important Emails" section with 5 emails
- Each email showing urgency dot, sender, subject, score, and badge
- Footer with last checked time and "View All" button

### Method 2: Browser Screenshot Extensions

Use browser extensions like:
- **Firefox**: Built-in screenshot tool (Shift+Ctrl+S)
- **Chrome**: Full Page Screen Capture extension
- **Safari**: Cmd+Shift+4 for area selection

Steps:
1. Navigate to http://localhost:3200
2. Use extension to capture specific widget area
3. Crop to exact widget dimensions
4. Save with proper filenames

### Method 3: Automated Puppeteer Script (Advanced)

If you need consistent, repeatable screenshots:

```javascript
// screenshot-capture.js
const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();

  await page.goto('http://localhost:3200');

  // Small widget
  await page.setViewport({ width: 300, height: 150 });
  const smallWidget = await page.$('.widget-small'); // Adjust selector
  await smallWidget.screenshot({ path: './screenshots/widget-small.png' });

  // Large widget
  await page.setViewport({ width: 600, height: 400 });
  const largeWidget = await page.$('.widget-large'); // Adjust selector
  await largeWidget.screenshot({ path: './screenshots/widget-large.png' });

  await browser.close();
})();
```

## Screenshot Quality Checklist

Before saving screenshots, verify:

### Content Requirements
- [ ] Shows **real email data**, not empty states or placeholders
- [ ] All text is readable (no blurry text)
- [ ] Colors are accurate (blue gradient, urgency color dots)
- [ ] Icons are crisp (Mail, AlertCircle, TrendingUp, etc.)
- [ ] No browser UI visible (address bar, bookmarks, etc.)

### Technical Requirements
- [ ] Format: PNG (not JPEG)
- [ ] Background: Matches app theme (blue gradient)
- [ ] Dimensions: Approximate to specified sizes (doesn't need to be exact)
- [ ] File size: Reasonable (<500KB per screenshot)
- [ ] Location: `./screenshots/` directory in project root

### Data Validation
- [ ] Small widget shows: 5 important emails, 100% accuracy
- [ ] Large widget shows: All 5 sample emails with correct urgency levels
- [ ] Email subjects match database:
  - "Q4 Board Meeting - Action Required" (critical)
  - "Contract Review Needed - Deadline Friday" (high)
  - "Security Incident - Investigation Update" (high)
  - "Annual Review Schedule - Next Week" (medium)
  - "Team Meeting Reminder - Tomorrow 2pm" (low)

## Verification

After capturing screenshots:

1. **Check files exist:**
   ```bash
   ls -lh ./screenshots/
   # Should show widget-small.png and widget-large.png
   ```

2. **Verify file sizes:**
   ```bash
   file ./screenshots/*.png
   # Should show PNG image data
   ```

3. **Visual review:**
   - Open each screenshot in image viewer
   - Confirm they match expected dimensions
   - Verify all UI elements are visible and clear

4. **Marketplace compliance:**
   - Screenshots accurately represent the app's functionality
   - Show email intelligence features (not infrastructure)
   - Demonstrate the widget-first design philosophy

## Best Practices (from app-config.json)

Per the app configuration:
- ✅ Use high-quality screenshots (2x resolution recommended)
- ✅ Show the widget in action with realistic data
- ❌ Avoid screenshots with obvious test/placeholder data
- ✅ Widget screenshots are PRIMARY - users see these in marketplace
- ✅ Ensure good lighting and contrast for visibility

## Troubleshooting

### Issue: Widgets Show Empty State
**Solution:** Run the database seeding script to create sample emails:
```bash
docker-compose exec -T backend python -c "
from backend.database import SessionLocal
from backend.models import ProcessedEmail
from datetime import datetime, timedelta
import uuid

# [Sample email creation code from previous execution]
"
```

### Issue: Widget Not Displaying Correctly
**Solution:**
1. Check frontend container is healthy: `docker ps`
2. Rebuild frontend: `docker-compose build frontend && docker-compose up -d frontend`
3. Clear browser cache and reload

### Issue: Screenshots Too Small/Large
**Solution:** Screenshots don't need to be exactly 300×150px or 600×400px. They should be **approximately** those dimensions and show the complete widget interface.

### Issue: Wrong Data Shown
**Solution:** Verify backend is returning email intelligence data:
```bash
curl -s -H "Authorization: Bearer test-user" "http://localhost:8000/api/widget?size=large" | python3 -m json.tool
```
Should show `important_emails_today`, `detection_accuracy`, and `recent_important_emails` array.

## Final Checklist

Before submitting to Clarity Marketplace:

- [ ] `./screenshots/widget-small.png` exists
- [ ] `./screenshots/widget-large.png` exists
- [ ] Both screenshots show real email intelligence data
- [ ] app-config.json captions match widget contents
- [ ] Screenshots demonstrate widget-first design
- [ ] All visual elements are clear and readable
- [ ] No placeholder or test data visible

## References

- **CLAUDE.md** (lines 8-132): Widget-first design philosophy and requirements
- **app-config.json** (lines 232-289): Screenshot configuration and instructions
- **Widget Component**: `frontend/src/components/Widget.tsx`
- **Widget API**: `backend/main.py` lines 107-190

---

**Remember**: These screenshots are what users see FIRST in the Clarity Marketplace. They must accurately represent your app's value proposition - showing important email intelligence, not infrastructure metrics!
