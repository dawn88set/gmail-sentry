# Widget Design Guide

**Complete guide for building beautiful, functional widgets for Clarity Platform**

---

## Table of Contents

1. [Widget Philosophy](#widget-philosophy)
2. [The Two Widget Sizes](#the-two-widget-sizes)
3. [Layout Principles](#layout-principles)
4. [Visual Design System](#visual-design-system)
5. [Component Patterns](#component-patterns)
6. [Performance Requirements](#performance-requirements)
7. [Loading & Error States](#loading--error-states)
8. [AI Code Generator Instructions](#ai-code-generator-instructions)
9. [Testing Checklist](#testing-checklist)

---

## Widget Philosophy

### Why Widgets Exist

Widgets are inspired by **Apple Widgets**: glanceable, actionable, and beautiful. They answer the fundamental question: **"Is everything okay?"** in under 2 seconds.

**Key Principles:**
- **Widget-First Mindset**: 90% of user interactions happen through widgets
- **Glanceable Information**: Critical data visible without clicking
- **Immediate Action**: Common tasks completable from the widget
- **Always Visible**: Widgets are on the dashboard 24/7

### The Widget-First Model

```
Traditional App:
User types URL → Page loads → User performs action → Closes tab

Clarity App:
User sees widget on dashboard → Gets status at a glance → Takes action if needed
```

**This changes everything** about how you design your app.

---

## The Two Widget Sizes

### ⚠️ CRITICAL: Only TWO Widget Sizes Exist

**NO medium size!** The platform supports exactly two sizes:

### Small Widget: 170×170px (1:1 ratio - SQUARE)

**Purpose**: Quick glance at status
**Use Case**: User scans their dashboard grid of 10-20 widgets
**User Question**: "Is everything okay with this app?"
**View Time**: 2 seconds

**What to show:**
- ✅ 1 primary metric (large number)
- ✅ 1-2 status indicators (icons/colors)
- ✅ 0-1 action buttons
- ❌ NO lists
- ❌ NO multiple stats
- ❌ NO complex layouts

**Example Use Cases:**
- "5 urgent emails" + Draft button
- "12 day streak" + Start workout button
- "3 tasks due today" + View button

### Large Widget: 360×170px (2.1:1 ratio - WIDE RECTANGLE)

**Purpose**: Detailed monitoring and immediate action
**Use Case**: User actively manages the app
**User Question**: "What needs my attention right now?"
**View Time**: 10-30 seconds

**What to show:**
- ✅ 3-5 key metrics (stats grid)
- ✅ 3-5 recent items (list view)
- ✅ 2-4 quick action buttons
- ✅ Interactive elements
- ❌ NO complete history (link to full app)
- ❌ NO complex configuration (link to full app)

**Example Use Cases:**
- Email dashboard with top 3 urgent emails + quick actions
- Task list with priorities + completion tracking
- Workout progress with exercise list + start button

### Size Comparison

```
┌─────────────────────┐  ┌──────────────────────────────────────────────┐
│   Small Widget      │  │         Large Widget (360×170)               │
│    (170×170)        │  │ ──────────────────────────────────────────── │
│      SQUARE         │  │                                              │
│                     │  │ [12 Active] [95% Success] [42 Total]         │
│    [Icon]  42       │  │                                              │
│   urgent emails     │  │ Recent: ✓ Email workflow - 2m ago           │
│                     │  │         ✓ Task analysis - 5m ago            │
│   Success: 95%      │  │                                              │
│                     │  │ [Archive] [Snooze] [✨ Draft Replies]       │
│ [Draft All Replies] │  │                                              │
└─────────────────────┘  └──────────────────────────────────────────────┘
     Apple-style              Apple-style wide widget
     small widget
```

---

## Layout Principles

### Critical Layout Rules

These rules are **non-negotiable** for both widget sizes:

#### Rule 1: Always Fill Container Exactly

```typescript
// ✅ CORRECT
<div className="w-full h-full flex flex-col overflow-hidden">
  {/* Widget content */}
</div>

// ❌ WRONG - Fixed dimensions
<div className="w-[300px] h-[150px]">  {/* Breaks in different containers */}
```

#### Rule 2: Prevent Overflow with Flexbox

```typescript
// ✅ CORRECT - Flexible content area
<div className="w-full h-full flex flex-col p-4">
  <div className="flex-1 min-h-0">  {/* min-h-0 prevents overflow */}
    {/* Scrollable content if needed */}
  </div>
  <button className="flex-shrink-0">  {/* Fixed at bottom */}
    Action
  </button>
</div>

// ❌ WRONG - Fixed heights
<div className="h-[400px]">  {/* Don't use fixed heights! */}
  <div className="h-[300px]">  {/* Don't use fixed heights! */}
```

#### Rule 3: Use Constant 16px Padding (Apple Standard)

```typescript
// ✅ CORRECT - Consistent 16px padding across all widget sizes
<div className="w-full h-full p-4 rounded-3xl overflow-hidden">  {/* p-4 = 16px, rounded-3xl = 24px */}

// ❌ WRONG - Variable padding breaks consistency
<div className="p-2">  {/* 8px - Too tight */}
<div className="p-6">  {/* 24px - Too spacious */}
<div className="p-[12%]">  {/* Proportional - Inconsistent across sizes */}
```

#### Rule 4: Always Set overflow: hidden

```typescript
// ✅ CORRECT - Prevents scrollbars
<div className="w-full h-full overflow-hidden">
// OR
<div style={{ overflow: 'hidden' }}>

// ❌ WRONG - Can cause scrollbars
<div className="w-full h-full">  {/* No overflow control */}
```

### Small Widget Layout Pattern

```typescript
export default function Widget({ size }: { size: 'small' | 'large' }) {
  if (size === 'small') {
    return (
      <div className="w-[170px] h-[170px] flex flex-col p-4 overflow-hidden rounded-3xl">
        {/* Header: Icon/Brand */}
        <div className="flex justify-center mb-auto">
          <div className="bg-gradient-to-br from-blue-500 to-indigo-500 p-3 rounded-2xl">
            <Icon className="w-6 h-6 text-white" />
          </div>
        </div>

        {/* Middle: Primary Metric - THE HERO */}
        <div className="flex-1 flex flex-col items-center justify-center">
          <span className="text-5xl font-bold leading-none">{count}</span>
          <p className="text-sm text-muted-foreground mt-2">description</p>
          <div className="flex items-center gap-1 mt-1">
            <TrendingUp className="w-4 h-4 text-green-500" />
            <span className="text-xs text-muted-foreground">{secondaryStat}</span>
          </div>
        </div>

        {/* Bottom: Primary Action Button */}
        <button className="w-full bg-gradient-to-r from-blue-500 to-indigo-500 text-white py-3 rounded-xl text-base font-semibold flex items-center justify-center gap-2 mt-auto active:scale-95 transition-transform">
          <Icon className="w-5 h-5" />
          Action Label
        </button>
      </div>
    )
  }

  // Large widget implementation...
}
```

### Large Widget Layout Pattern

```typescript
if (size === 'large') {
  return (
    <div className="w-[360px] h-[170px] flex flex-row p-4 overflow-hidden rounded-3xl">
      {/* Header: App Name + Key Metric */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Icon className="h-5 w-5 text-primary" />
          App Name
        </h3>
        <span className="text-sm text-muted-foreground">Last updated: 2m ago</span>
      </div>

      {/* Stats Grid - Fixed height */}
      <div className="grid grid-cols-3 gap-4 mb-4 flex-shrink-0">
        <StatCard label="Active" value={12} />
        <StatCard label="Success" value="95%" />
        <StatCard label="Total" value={42} />
      </div>

      {/* Recent Activity - Flexible height */}
      <div className="flex-1 min-h-0 mb-3 overflow-hidden">
        <h4 className="text-sm font-semibold mb-2">Recent Activity</h4>
        <div className="space-y-2 overflow-y-auto max-h-full">
          {items.slice(0, 5).map(item => (
            <ItemCard key={item.id} {...item} />
          ))}
        </div>
      </div>

      {/* Quick Actions - Fixed at bottom */}
      <div className="flex gap-2 flex-shrink-0">
        <button className="flex-1 py-2.5 rounded-xl">Secondary</button>
        <button className="flex-1 py-2.5 rounded-xl">Secondary</button>
        <button className="flex-1 bg-gradient-to-r from-blue-500 to-indigo-500 text-white py-2.5 rounded-xl">
          Primary
        </button>
      </div>
    </div>
  )
}
```

---

## Visual Design System

### Typography Scale

**Small Widget Typography:**
```typescript
// Primary metric (the hero number)
className="text-5xl font-bold"  // 48px - Dominates the widget

// Label text
className="text-sm text-muted-foreground"  // 14px - Describes the metric

// Secondary info
className="text-xs text-muted-foreground"  // 12px - Supporting details
```

**Large Widget Typography:**
```typescript
// Section headers
className="text-lg font-semibold"  // 18px - Clear organization

// Primary metrics
className="text-3xl font-bold"  // 30px - Multiple hero numbers

// Item titles
className="text-sm font-medium"  // 14px - Readable list items

// Item subtitles
className="text-xs text-muted-foreground"  // 12px - Supporting info

// Labels/metadata
className="text-[10px] text-muted-foreground"  // 10px - Compact labels
```

### Spacing Rhythm

**Small Widget Spacing (170×170px SQUARE):**
```typescript
// Outer padding (Apple standard)
p-4        // 16px - Consistent across all widgets

// Gaps between elements
gap-2      // 8px - Tight grouping
gap-3      // 12px - Standard spacing

// Button padding
py-2.5 px-4  // 10px/16px - Mobile touch target (≥44px height)
py-3 px-6    // 12px/24px - Prominent action button

// Border radius (Apple standard)
rounded-3xl  // 24px - Apple-style rounded corners
```

**Large Widget Spacing (360×170px WIDE RECTANGLE):**
```typescript
// Outer padding (Apple standard)
p-4         // 16px - Consistent across all widgets

// Section gaps
gap-3       // 12px - Between major sections
gap-4       // 16px - More separation

// Item spacing
space-y-2   // 8px - Between list items
space-y-3   // 12px - Between grouped items

// Grid gaps
gap-4       // 16px - Stats grid columns

// Border radius (Apple standard)
rounded-3xl  // 24px - Apple-style rounded corners
```

### Color System

#### Theme Detection (REQUIRED)

```typescript
// ALWAYS detect system theme
const [theme, setTheme] = useState<'light' | 'dark'>('light')

useEffect(() => {
  const checkTheme = () => {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    setTheme(isDark ? 'dark' : 'light')
  }

  checkTheme()
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', checkTheme)
  return () => mediaQuery.removeEventListener('change', checkTheme)
}, [])

const isDark = theme === 'dark'
const bgColor = isDark ? 'bg-gray-900' : 'bg-white'
const textColor = isDark ? 'text-white' : 'text-gray-900'
const subtleText = isDark ? 'text-gray-400' : 'text-gray-600'
const cardBg = isDark ? 'bg-gray-800' : 'bg-gray-50'
```

#### Brand Colors (Choose ONE)

```typescript
// Pick one gradient pair that matches your app's identity
const brandColors = {
  red: 'from-red-500 to-pink-500',
  orange: 'from-orange-500 to-red-500',
  blue: 'from-blue-500 to-indigo-500',
  green: 'from-green-500 to-emerald-500',
  purple: 'from-purple-500 to-pink-500',
  teal: 'from-teal-500 to-cyan-500'
}

// Use consistently throughout your widget
<div className={`bg-gradient-to-br ${brandColors.blue}`}>
```

#### Status Colors (Universal)

```typescript
// Success
text-green-500           // Icons
text-green-600           // Text in light mode
bg-green-100/20          // Subtle backgrounds

// Warning
text-amber-500           // Icons
text-amber-600           // Text in light mode
bg-amber-100/20          // Subtle backgrounds

// Error
text-red-500             // Icons
text-red-600             // Text in light mode
bg-red-100/20            // Subtle backgrounds

// Neutral/Info
text-gray-400            // Subtle elements
text-gray-600            // Regular text
```

### Elevation & Depth

```typescript
// Card backgrounds (within widgets)
className={isDark ? 'bg-gray-800' : 'bg-gray-50'}

// Subtle borders
className="border border-gray-200 dark:border-gray-800"

// Hover states
hover:bg-gray-100 dark:hover:bg-gray-800

// Active states (mobile)
active:scale-95 transition-transform
```

---

## Component Patterns

### Pattern 1: Icon + Metric (Small Widget Hero)

```typescript
<div className="flex items-center gap-2">
  {/* Brand icon container */}
  <div className="bg-gradient-to-br from-blue-500 to-indigo-500 p-3 rounded-2xl shadow-lg">
    <Mail className="w-6 h-6 text-white" />
  </div>

  {/* Metric */}
  <div>
    <span className="text-5xl font-bold leading-none">{42}</span>
    <p className="text-sm text-muted-foreground mt-1">unread emails</p>
  </div>
</div>
```

### Pattern 2: Stats Grid (Large Widget)

```typescript
<div className="grid grid-cols-3 gap-4">
  {[
    { label: 'Active Triggers', value: 12 },
    { label: 'Success Rate', value: '95%' },
    { label: 'Total Executions', value: 42 }
  ].map(stat => (
    <div key={stat.label} className={`rounded-lg p-3 ${cardBg}`}>
      <p className="text-xs text-muted-foreground">{stat.label}</p>
      <p className="text-2xl font-bold mt-1">{stat.value}</p>
    </div>
  ))}
</div>
```

### Pattern 3: Item List with Status (Large Widget)

```typescript
<div className="space-y-2">
  {items.slice(0, 5).map(item => (
    <div
      key={item.id}
      className={`flex items-center gap-3 p-2 rounded-lg ${cardBg}`}
    >
      {/* Status indicator */}
      <div className={cn(
        'h-2 w-2 rounded-full',
        item.status === 'completed' ? 'bg-green-500' : 'bg-red-500'
      )} />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{item.title}</p>
        <p className="text-xs text-muted-foreground truncate">{item.subtitle}</p>
      </div>

      {/* Metadata */}
      <span className="text-xs text-muted-foreground flex-shrink-0">
        {item.time}
      </span>
    </div>
  ))}
</div>
```

### Pattern 4: Primary Action Button

```typescript
<button
  onClick={handleAction}
  disabled={isProcessing}
  className="w-full bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed text-white py-2.5 px-4 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform"
>
  {isProcessing ? (
    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
  ) : (
    <>
      <Sparkles className="w-4 h-4" />
      {actionLabel}
    </>
  )}
</button>
```

### Pattern 5: Progress Indicator

```typescript
// Linear progress bar
<div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
  <div
    className="bg-gradient-to-r from-blue-500 to-indigo-500 h-2 rounded-full transition-all duration-500"
    style={{ width: `${progress}%` }}
  />
</div>

// Circular progress ring
<div className="relative w-12 h-12">
  <svg className="w-12 h-12 transform -rotate-90">
    {/* Background circle */}
    <circle
      cx="24" cy="24" r="20"
      stroke={isDark ? '#374151' : '#e5e7eb'}
      strokeWidth="3"
      fill="none"
    />
    {/* Progress circle */}
    <circle
      cx="24" cy="24" r="20"
      stroke="#3b82f6"
      strokeWidth="3"
      fill="none"
      strokeDasharray={`${2 * Math.PI * 20}`}
      strokeDashoffset={`${2 * Math.PI * 20 * (1 - progress / 100)}`}
      strokeLinecap="round"
    />
  </svg>
  <div className="absolute inset-0 flex items-center justify-center">
    <span className="text-xs font-bold">{Math.round(progress)}%</span>
  </div>
</div>
```

### Pattern 6: Empty State

```typescript
<div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
  <CheckCircle className="w-6 h-6 text-green-500" />
  <div className="text-center">
    <p className="text-sm font-medium">All caught up!</p>
    <p className="text-xs mt-1">No items need your attention</p>
  </div>
</div>
```

---

## Performance Requirements

### API Response Times

**Small Widget:**
- Target: < 200ms
- Maximum: 300ms
- Why: Users scan 10-20 widgets quickly

**Large Widget:**
- Target: < 500ms
- Maximum: 1000ms
- Why: More data, but still needs to feel instant

### Data Optimization

```typescript
// Backend endpoint
@app.get("/api/widget")
async def get_widget_data(
    size: str = "large",
    user_id: str = Depends(get_current_user)
):
    if size == "small":
        # ✅ Minimal data - fast response
        return {
            "active_count": count_active(user_id),
            "success_rate": calculate_rate(user_id),
            "status": "healthy"  # or "attention_needed"
        }
    else:  # large
        # ✅ Detailed but limited data
        return {
            "active_count": count_active(user_id),
            "total_executions": count_total(user_id),
            "success_rate": calculate_rate(user_id),
            "recent_items": get_recent(user_id, limit=5),  # ✅ Limit results!
            "alerts": get_urgent_alerts(user_id, limit=3)   # ✅ Only urgent!
        }
```

### Real-Time Updates

```typescript
// ALWAYS implement 30-second refresh
useEffect(() => {
  fetchData()
  const interval = setInterval(fetchData, 30000)  // 30 seconds
  return () => clearInterval(interval)
}, [size])

// For critical updates, use shorter intervals
useEffect(() => {
  fetchData()
  const interval = setInterval(fetchData, 10000)  // 10 seconds for urgent apps
  return () => clearInterval(interval)
}, [size])
```

### Caching Strategy

```typescript
// Backend caching for expensive queries
from functools import lru_cache
from datetime import datetime, timedelta

# Cache widget data for 30 seconds
_widget_cache = {}

def get_widget_data_cached(user_id: str, size: str):
    cache_key = f"{user_id}:{size}"
    now = datetime.now()

    if cache_key in _widget_cache:
        cached_data, cached_time = _widget_cache[cache_key]
        if now - cached_time < timedelta(seconds=30):
            return cached_data

    # Compute fresh data
    data = compute_widget_data(user_id, size)
    _widget_cache[cache_key] = (data, now)
    return data
```

---

## Loading & Error States

### Loading State

```typescript
if (loading) {
  return (
    <div className="w-full h-full flex items-center justify-center bg-card overflow-hidden">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
    </div>
  )
}
```

### Error State

```typescript
if (error) {
  return (
    <div className="w-full h-full flex items-center justify-center p-4 bg-card overflow-hidden">
      <div className="text-center">
        <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-2" />
        <p className="text-sm font-medium text-foreground mb-1">Unable to load widget</p>
        <p className="text-xs text-muted-foreground mb-3">{error.message}</p>
        <button
          onClick={retry}
          className="text-xs text-primary hover:underline"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
```

### Empty State

```typescript
if (!data || data.items.length === 0) {
  return (
    <div className="w-full h-full flex items-center justify-center overflow-hidden">
      <div className="text-center">
        <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
        <p className="text-sm font-medium">All caught up!</p>
        <p className="text-xs text-muted-foreground mt-1">
          No items need your attention right now
        </p>
      </div>
    </div>
  )
}
```

---

## AI Code Generator Instructions

### For LLMs Generating Widget Code

When generating widget code, follow these instructions **exactly**:

#### 1. Size Detection

```typescript
// ALWAYS use exactly TWO sizes
type WidgetSize = 'small' | 'large'  // ⚠️ NO 'medium'!

interface WidgetProps {
  size?: WidgetSize;
  className?: string;
}

export default function Widget({ size = 'large', className }: WidgetProps) {
  // Implementation
}
```

#### 2. Layout Strategy

**Small Widget (170×170px - SQUARE): Vertical Stack**
```typescript
if (size === 'small') {
  return (
    <div className="w-full h-full flex flex-col p-4 overflow-hidden">
      {/* Top: Icon/Brand */}
      <div className="flex justify-center mb-auto">
        <BrandIcon />
      </div>

      {/* Middle: Primary Metric (THE HERO) */}
      <div className="flex-1 flex flex-col items-center justify-center">
        <span className="text-5xl font-bold">{primaryMetric}</span>
        <p className="text-sm text-muted">{label}</p>
      </div>

      {/* Bottom: Action Button */}
      <button className="w-full py-3 rounded-xl mt-auto">
        Action
      </button>
    </div>
  )
}
```

**Large Widget (360×170px - WIDE RECTANGLE): Horizontal Layout**
```typescript
if (size === 'large') {
  return (
    <div className="w-full h-full flex flex-col p-4 overflow-hidden rounded-3xl">
      {/* Header: App name */}
      <h3 className="flex items-center gap-2 mb-3 flex-shrink-0">
        <Icon /> App Name
      </h3>

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-4 mb-4 flex-shrink-0">
        {stats.map(stat => <StatCard {...stat} />)}
      </div>

      {/* Recent Items (flexible height) */}
      <div className="flex-1 min-h-0 mb-3">
        {items.slice(0, 5).map(item => <ItemCard {...item} />)}
      </div>

      {/* Actions */}
      <div className="flex gap-2 flex-shrink-0">
        <button>Action 1</button>
        <button>Action 2</button>
      </div>
    </div>
  )
}
```

#### 3. Data Display Priority

**Small Widget: Show ONLY Critical Data**
```typescript
// ✅ Correct priorities
Priority 1: Primary metric (one big number)
Priority 2: Status indicator (color/icon)
Priority 3: One action button

// ❌ Do NOT include
- Lists of items
- Multiple stats
- Complex layouts
- Detailed information
```

**Large Widget: Show Actionable Overview**
```typescript
// ✅ Correct priorities
Priority 1: Key stats (2-4 metrics in grid)
Priority 2: Recent activity (3-5 items max)
Priority 3: Quick actions (2-4 buttons)

// ✅ Goal: Enable action without opening full app
// ❌ Do NOT include complete history (link to full app instead)
```

#### 4. Mobile-First Considerations

```typescript
// Touch targets: Minimum 44px height
className="py-2.5"  // ✅ 10px + ~34px content ≈ 54px total

// Text truncation: Prevent overflow
className="truncate"  // ✅ Single line
className="line-clamp-2"  // ✅ Two lines

// Hover + Active states for mobile
className="hover:bg-gray-100 active:scale-95 transition-transform"

// Icon sizes: Appropriate for touch
className="w-4 h-4"  // ✅ Buttons, small icons
className="w-6 h-6"  // ✅ Prominent icons
className="w-8 h-8"  // ✅ Hero icons (small widget)
```

#### 5. Theme Support (MANDATORY)

```typescript
// ALWAYS detect and support system theme
function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    const checkTheme = () => {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      setTheme(isDark ? 'dark' : 'light')
    }

    checkTheme()
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', checkTheme)
    return () => mediaQuery.removeEventListener('change', checkTheme)
  }, [])

  return theme
}

// Use in component
const theme = useTheme()
const isDark = theme === 'dark'
const bgColor = isDark ? 'bg-gray-900' : 'bg-white'
const textColor = isDark ? 'text-white' : 'text-gray-900'
```

#### 6. Real-Time Updates (REQUIRED)

```typescript
// ALWAYS implement automatic refresh
useEffect(() => {
  fetchData()  // Initial load
  const interval = setInterval(fetchData, 30000)  // Refresh every 30s
  return () => clearInterval(interval)
}, [size])  // Re-fetch when size changes
```

#### 7. Error Handling

```typescript
// ALWAYS handle three states
const [data, setData] = useState(null)
const [loading, setLoading] = useState(true)
const [error, setError] = useState(null)

// Show loading spinner
if (loading) return <LoadingState />

// Show error message with retry
if (error) return <ErrorState error={error} onRetry={fetchData} />

// Show empty state if no data
if (!data || data.items.length === 0) return <EmptyState />

// Render widget
return <WidgetContent data={data} />
```

---

## Testing Checklist

### Visual Testing

- [ ] **Exact Size**: Looks perfect at 170×170px (small square) and 360×170px (large wide rectangle)
- [ ] **Apple Standards**: 16px padding (p-4) and 24px border radius (rounded-3xl) on all widgets
- [ ] **No Scrollbars**: overflow-hidden prevents scrollbars in both sizes
- [ ] **No Overflow**: All text truncates gracefully, no content cut off
- [ ] **Touch Targets**: All buttons ≥ 44px height for mobile
- [ ] **Theme Support**: Light and dark mode both look great
- [ ] **Responsive Icons**: Icons scale appropriately with layout
- [ ] **Loading State**: Spinner displays centered and themed
- [ ] **Error State**: Error message is clear with retry option
- [ ] **Empty State**: Empty state is encouraging, not alarming

### Functional Testing

- [ ] **API Performance**: Small widget < 200ms, Large widget < 500ms
- [ ] **Real-Time Updates**: Data refreshes every 30 seconds automatically
- [ ] **Actions Work**: All buttons trigger correct functions
- [ ] **No Console Errors**: No React warnings or errors in console
- [ ] **Network Failure**: Handles network failures gracefully
- [ ] **Size Prop**: Correctly switches between small and large layouts
- [ ] **Data Limits**: Lists limited to 5 items max (performance)

### Accessibility Testing

- [ ] **Semantic HTML**: Uses proper heading hierarchy
- [ ] **Button Labels**: All buttons have clear text or aria-labels
- [ ] **Color Contrast**: Text meets WCAG AA standards (4.5:1)
- [ ] **Focus States**: Keyboard navigation works
- [ ] **Screen Reader**: Content reads logically

### Cross-Browser Testing

- [ ] **Chrome**: Tested on latest Chrome
- [ ] **Safari**: Tested on latest Safari
- [ ] **Firefox**: Tested on latest Firefox
- [ ] **Mobile**: Tested on iOS and Android

---

## Examples from Production Apps

### Example 1: Email Widget (InboxZero Pattern)

**Small Widget:**
```typescript
<div className="w-full h-full flex flex-col p-[12%] overflow-hidden">
  {/* Icon */}
  <div className="flex justify-center mb-auto">
    <div className="bg-gradient-to-br from-red-500 to-pink-500 p-[10%] rounded-2xl">
      <Mail className="w-6 h-6 text-white" />
    </div>
  </div>

  {/* Metric */}
  <div className="flex-1 flex flex-col items-center justify-center">
    <span className="text-5xl font-bold">{urgentCount}</span>
    <p className="text-sm text-muted mt-2">urgent emails</p>
    <div className="flex items-center gap-1 mt-1">
      <TrendingUp className="w-4 h-4 text-green-500" />
      <span className="text-xs text-muted">95% response</span>
    </div>
  </div>

  {/* Action */}
  <button className="w-full bg-gradient-to-r from-red-500 to-pink-500 text-white py-3 rounded-xl">
    <Sparkles className="w-5 h-5" />
    Draft Replies
  </button>
</div>
```

**Large Widget:**
```typescript
<div className="w-full h-full flex flex-col p-3 overflow-hidden">
  {/* Header with stats */}
  <div className="flex items-center gap-2 mb-2 flex-shrink-0">
    <div className="bg-gradient-to-br from-red-500 to-pink-500 p-2 rounded-lg">
      <Mail className="w-4 h-4 text-white" />
    </div>
    <div className="flex-1">
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold">{urgentCount}</span>
        <span className="text-xs text-muted">urgent</span>
      </div>
      <div className="flex items-center gap-1">
        <TrendingUp className="w-2.5 h-2.5 text-green-500" />
        <span className="text-[10px] text-green-500">95% response rate</span>
      </div>
    </div>
  </div>

  {/* Email list */}
  <div className="flex-1 min-h-0 mb-2 flex flex-col gap-1 overflow-y-auto">
    {emails.slice(0, 3).map(email => (
      <div className="px-2 py-1.5 bg-card rounded-lg">
        <p className="text-[11px] font-medium truncate">{email.from}</p>
        <p className="text-[9px] text-muted truncate">{email.subject}</p>
      </div>
    ))}
  </div>

  {/* Actions */}
  <div className="flex gap-2 flex-shrink-0">
    <button className="flex-1 py-2.5 bg-secondary rounded-xl">Archive</button>
    <button className="flex-1 bg-gradient-to-r from-red-500 to-pink-500 text-white py-2.5 rounded-xl">
      <Sparkles className="w-3 h-3" />
      Draft
    </button>
  </div>
</div>
```

### Example 2: Fitness Widget (Progress Ring Pattern)

**Small Widget:**
```typescript
<div className="w-full h-full flex flex-col p-3 overflow-hidden">
  {/* Center: Streak metric */}
  <div className="flex-1 flex flex-col items-center justify-center">
    <div className="flex items-center gap-1.5 mb-1">
      <Flame className="w-7 h-7 text-orange-500" />
      <span className="text-5xl font-bold">{streakDays}</span>
    </div>
    <p className="text-sm text-muted">day streak</p>
    <div className="flex items-center gap-1 mt-2">
      <CheckCircle className="w-3.5 h-3.5 text-green-500" />
      <span className="text-xs text-muted">{thisWeek}/{weeklyGoal} this week</span>
    </div>
  </div>

  {/* Action */}
  <button className="w-full bg-gradient-to-r from-orange-500 to-red-500 text-white py-2.5 rounded-xl">
    <Play className="w-4 h-4" />
    Start Workout
  </button>
</div>
```

**Large Widget:**
```typescript
<div className="w-full h-full flex items-center justify-between p-4 gap-4 overflow-hidden">
  {/* Left: Icon + Streak */}
  <div className="flex items-center gap-3">
    <div className="bg-gradient-to-br from-orange-500 to-red-500 p-2.5 rounded-xl">
      <Dumbbell className="w-5 h-5 text-white" />
    </div>
    <div>
      <div className="flex items-center gap-1">
        <Flame className="w-4 h-4 text-orange-500" />
        <span className="text-xl font-bold">{streakDays}</span>
      </div>
      <span className="text-[10px] text-muted">{thisWeek}/{weeklyGoal} this week</span>
    </div>
  </div>

  {/* Middle: Progress ring + workout */}
  <div className="flex items-center gap-3">
    <CircularProgress value={progress} />
    <div>
      <p className="text-sm font-medium">{workoutName}</p>
      <p className="text-[10px] text-muted">{exerciseCount} exercises</p>
    </div>
  </div>

  {/* Right: Start button */}
  <button className="bg-gradient-to-r from-orange-500 to-red-500 text-white px-5 py-3 rounded-xl">
    <Play className="w-4 h-4" />
    Start
  </button>
</div>
```

---

**This guide enables both human developers and AI code generators to build beautiful, functional widgets that users love. Follow these patterns for consistency and quality across the Clarity Platform.**
