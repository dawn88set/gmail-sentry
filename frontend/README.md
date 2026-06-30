# Clarity Agentic App - Frontend

React + TypeScript + Vite frontend for managing AI agents, workflows, and triggers.

## Features

- **Dashboard**: View agents, workflows, and execution statistics
- **Widget Component**: 2 sizes (small, large) for Clarity Platform embedding
- **Trigger Manager**: User-configurable triggers with dynamic form generation
- **Dark Mode**: Full dark mode support
- **Responsive**: Mobile-friendly design

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (port 3200)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Environment Variables

Create `.env` file:

```bash
VITE_API_URL=http://localhost:8000
```

## Project Structure

```
src/
├── components/
│   ├── Layout.tsx        # App layout with navigation
│   └── Widget.tsx        # Widget component (3 sizes)
├── pages/
│   ├── Dashboard.tsx     # Main dashboard
│   └── TriggerManager.tsx # Trigger management UI
├── lib/
│   ├── api.ts           # API client
│   └── utils.ts         # Utility functions
├── App.tsx              # Main app component
└── main.tsx             # Entry point
```

## Key Components

### Widget Component

Displays app statistics in 2 sizes optimized for Clarity Platform:

```tsx
import Widget from '@/components/Widget';

// Small (170×170px SQUARE) - Quick glance: Primary metric + action button
// Apple standard: 16px padding (p-4), 24px border radius (rounded-3xl)
<Widget size="small" />

// Large (360×170px WIDE RECTANGLE) - Detailed view: Stats grid + recent activity + actions
// Apple standard: 16px padding (p-4), 24px border radius (rounded-3xl)
<Widget size="large" />
```

⚠️ **Note**: Only TWO widget sizes exist (Apple standards). See [Widget Design Guide](../docs/WIDGET_DESIGN_GUIDE.md) for complete specifications.

### Dashboard

- Lists all registered agents and workflows
- Shows execution statistics
- Execute agents and workflows manually

### Trigger Manager

- Browse trigger templates
- Create user-configured trigger instances
- **Dynamic form generation** from config_fields
- Pause/resume/delete triggers
- View execution statistics

## Dark Mode

Dark mode is automatically detected from system preferences and can be toggled manually. Preference is saved to localStorage.

## API Integration

All backend communication goes through `src/lib/api.ts`:

```typescript
import { listAgents, createTrigger, getWidgetData } from '@/lib/api';

// List agents
const agents = await listAgents();

// Create trigger
await createTrigger('daily-review', 'My Review', {
  time: '09:00',
  timezone: 'America/New_York'
});

// Get widget data
const data = await getWidgetData('large');
```

## Building for Production

```bash
# Build
npm run build

# Output in dist/
ls dist/
```

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **React Router** - Routing
- **Axios** - HTTP client
- **Lucide React** - Icons
