import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Widget from '../Widget';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  getWidgetData: vi.fn(),
  clearCategory: vi.fn(),
  clearCategoryAll: vi.fn(),
  toApiError: (e: unknown) => ({ message: String(e) }),
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

const mockData = {
  urgent_count: 2,
  needs_reply_count: 1,
  // Thread-level open loops — the glance is loop closure, not mail arrival.
  open_loops: 3,
  owed_count: 1,
  waiting_count: 1,
  cold_count: 1,
  all_clear: false,
  last_scan: 'just now',
  top_alerts: [
    { id: 'a1', subject: 'Budget sign-off needed', sender: 'dana@acme.com', tier: 'urgent' as const, reason: 'From your manager', deep_link: 'https://mail.google.com/#a1' },
    { id: 'a2', subject: 'Invoice due in 2 days', sender: 'billing@vendor.com', tier: 'needs_reply' as const, reason: 'Payment due', deep_link: 'https://mail.google.com/#a2' },
  ],
  cleanup: { promo: 142, social: 38, spam: 11 },
  slack_configured: true,
};

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
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
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
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget size={size} />);
      await waitFor(() => expect(api.getWidgetData).toHaveBeenCalledWith(size));
    });

    it('defaults to medium when no size prop is given', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget />);
      await waitFor(() => expect(api.getWidgetData).toHaveBeenCalledWith('medium'));
    });
  });

  describe('content', () => {
    it('small shows open loops, not just mail that arrived', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget size="small" />);
      await waitFor(() => {
        // 2 urgent + 1 needs-reply + 3 open loops
        expect(screen.getByText('6')).toBeInTheDocument();
        expect(screen.getByText(/open loops/)).toBeInTheDocument();
      });
    });

    it('small surfaces the worst state present, not the most common', async () => {
      // At 170px there's room for one qualifier, so it must be the thing that
      // costs most to miss — a customer going quiet beats unread mail.
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget size="small" />);
      await waitFor(() => expect(screen.getByText('1 going cold')).toBeInTheDocument());
    });

    it('falls back gracefully when the backend sends no loop fields', async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { open_loops, owed_count, waiting_count, cold_count, ...legacy } = mockData as any;
      vi.mocked(api.getWidgetData).mockResolvedValue(legacy);
      render(<Widget size="small" />);
      await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
    });

    it('large lists flagged emails + junk counts', async () => {
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget size="large" />);
      await waitFor(() => {
        expect(screen.getByText('Budget sign-off needed')).toBeInTheDocument();
        expect(screen.getByText('Invoice due in 2 days')).toBeInTheDocument();
        expect(screen.getByText('142')).toBeInTheDocument();
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
      vi.mocked(api.getWidgetData).mockResolvedValue(mockData as any);
      render(<Widget size="small" />);
      await vi.waitFor(() => expect(api.getWidgetData).toHaveBeenCalledTimes(1));
      vi.advanceTimersByTime(30000);
      await vi.waitFor(() => expect(api.getWidgetData).toHaveBeenCalledTimes(2));
      vi.useRealTimers();
    });
  });
});

describe('safety', () => {
  it('never sends email from the glance surface', () => {
    // The widget has no undo and a small tap target. Anything that mails a
    // third party must go through a sheet where the recipient is visible.
    // Static tripwire so a future "quick approve" can't land here quietly.
    // vitest runs from frontend/, and import.meta.url under jsdom doesn't
    // resolve to a usable filesystem path.
    const src = readFileSync(resolve(process.cwd(), 'src/components/Widget.tsx'), 'utf8');
    expect(src).not.toMatch(/sendReply|sendNudge|approveAndSend|\bsendFollowUp\b/);
  });
});
