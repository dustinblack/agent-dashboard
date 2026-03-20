/**
 * Render tests for the StatusIndicator component.
 * Verifies correct label text for each agent status.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusIndicator from '../StatusIndicator';

describe('StatusIndicator', () => {
  it('renders "Working" for working status', () => {
    render(<StatusIndicator status="working" />);
    expect(screen.getByText('Working')).toBeInTheDocument();
  });

  it('renders "Permission" for waiting_permission status', () => {
    render(<StatusIndicator status="waiting_permission" />);
    expect(screen.getByText('Permission')).toBeInTheDocument();
  });

  it('renders "Idle" for idle status', () => {
    render(<StatusIndicator status="idle" />);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });

  it('renders "Live" for unknown/undefined status', () => {
    render(<StatusIndicator />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });
});
