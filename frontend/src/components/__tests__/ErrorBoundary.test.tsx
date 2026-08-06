/**
 * A render crash must not cost the whole screen.
 *
 * The deployed app showed a completely blank pane. A list endpoint returned a
 * body without its list, the client passed `undefined` into state, and a
 * `.filter` during render threw. React unmounts the entire tree on an uncaught
 * render error, so one missing field cost the whole product — and the only
 * trace was a console message inside a cross-origin iframe nobody would look at.
 *
 * The specific bug is fixed at the source; this holds the line for the next one.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ErrorBoundary } from '../ErrorBoundary';

function Boom() {
  throw new Error("Cannot read properties of undefined (reading 'filter')");
  // eslint-disable-next-line no-unreachable
  return null;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it('shows something a person can act on instead of a blank page', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/didn’t load/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /try again/i })).toBeTruthy();
  });

  it('answers the first thing anyone would fear: was my mail touched', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/nothing[\s\S]*was sent, filed or changed/i)).toBeTruthy();
  });

  it('renders children untouched when nothing throws', () => {
    render(
      <ErrorBoundary>
        <p>the app</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('the app')).toBeTruthy();
  });
});
