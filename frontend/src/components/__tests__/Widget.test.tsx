import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Widget from '../Widget';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  getWidgetData: vi.fn(),
  toggleTask: vi.fn(),
}));

// Canonical dimensions per size. The widget is built on the UI kit's
// WidgetContainer, which enforces these via INLINE STYLE (width/height/overflow)
// + the p-4 / rounded-3xl classes + a data-widget-size attribute.
const DIMS = {
  small: { w: '170px', h: '170px' },
  medium: { w: '360px', h: '170px' },
  large: { w: '360px', h: '360px' },
} as const;

const SIZES = ['small', 'medium', 'large'] as const;

const mockSmall = {
  open_count: 3,
  top_priority: 'high' as const,
  top_task: 'Ship the release',
  top_task_id: 't1',
  last_updated: 'just now',
};

const mockList = {
  open_count: 3,
  done_today: 1,
  top_priority: 'urgent' as const,
  tasks: [
    { id: 't1', title: 'Ship the release', priority: 'urgent' as const, done: false },
    { id: 't2', title: 'Review the PR', priority: 'high' as const, done: false },
    { id: 't3', title: 'Water the plants', priority: 'low' as const, done: false },
  ],
  last_updated: 'just now',
};

const dataFor = (size: (typeof SIZES)[number]) => (size === 'small' ? mockSmall : mockList);

function expectCanonical(el: Element | null, size: keyof typeof DIMS) {
  expect(el).toBeInTheDocument();
  const e = el as HTMLElement;
  expect(e.style.width).toBe(DIMS[size].w);
  expect(e.style.height).toBe(DIMS[size].h);
  expect(e.style.overflow).toBe('hidden');
  expect(e).toHaveClass('p-4');
  expect(e).toHaveClass('rounded-3xl');
}

describe('Widget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('canonical dimensions + style invariants (all 3 sizes)', () => {
    it.each(SIZES)('renders %s at exact dims, p-4, rounded-3xl, overflow hidden', async (size) => {
      vi.mocked(api.getWidgetData).mockResolvedValue(dataFor(size) as any);
      const { container } = render(<Widget size={size} />);
      await waitFor(() => {
        expectCanonical(container.querySelector(`[data-widget-size="${size}"]`), size);
      });
    });

    it.each(SIZES)('loading state keeps %s dimensions', (size) => {
      vi.mocked(api.getWidgetData).mockImplementation(() => new Promise(() => {}));
      const { container } = render(<Widget size={size} />);
      const el = container.querySelector('.animate-pulse') as HTMLElement;
      expect(el).toBeInTheDocument();
      expect(el.style.width).toBe(DIMS[size].w);
      expect(el.style.height).toBe(DIMS[size].h);
    });
  });

  describe('data loading', () => {
    it.each(SIZES)('requests data for size=%s', async (size) => {
      vi.mocked(api.getWidgetData).mockResolvedValue(dataFor(size) as any);
      render(<Widget size={size} />);
      await waitFor(() => expect(api.getWidgetData).toHaveBeenCalledWith(size));
    });

    it('defaults to medium when no size prop is given', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockList as any);
      render(<Widget />);
      await waitFor(() => expect(api.getWidgetData).toHaveBeenCalledWith('medium'));
    });
  });

  describe('content', () => {
    it('small shows the open-task count', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockSmall as any);
      render(<Widget size="small" />);
      await waitFor(() => {
        expect(screen.getByText('3')).toBeInTheDocument();
        expect(screen.getByText(/open task/)).toBeInTheDocument();
      });
    });

    it('large lists task titles', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockList as any);
      render(<Widget size="large" />);
      await waitFor(() => {
        expect(screen.getByText('Ship the release')).toBeInTheDocument();
        expect(screen.getByText('Review the PR')).toBeInTheDocument();
      });
    });
  });

  describe('error handling', () => {
    it.each(SIZES)('error state keeps %s dimensions', async (size) => {
      vi.mocked(api.getWidgetData).mockRejectedValue(new Error('boom'));
      const { container } = render(<Widget size={size} />);
      await waitFor(() => {
        const el = container.querySelector(`[data-widget-size="${size}"]`) as HTMLElement;
        expect(el).toBeInTheDocument();
        expect(el.style.width).toBe(DIMS[size].w);
        expect(el.style.height).toBe(DIMS[size].h);
      });
    });
  });

  describe('auto-refresh', () => {
    it('refetches every 30s', async () => {
      vi.useFakeTimers();
      vi.mocked(api.getWidgetData).mockResolvedValue(mockSmall as any);
      render(<Widget size="small" />);
      await vi.waitFor(() => expect(api.getWidgetData).toHaveBeenCalledTimes(1));
      vi.advanceTimersByTime(30000);
      await vi.waitFor(() => expect(api.getWidgetData).toHaveBeenCalledTimes(2));
      vi.useRealTimers();
    });
  });
});
