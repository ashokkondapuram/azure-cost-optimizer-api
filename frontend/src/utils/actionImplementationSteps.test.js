import {
  resolveActionImplementationSteps,
} from './actionImplementationSteps';

describe('resolveActionImplementationSteps', () => {
  it('returns playbook steps for known action types', () => {
    const action = { action_type: 'resize_down' };
    const steps = resolveActionImplementationSteps(action, []);
    expect(steps.length).toBeGreaterThan(2);
    expect(steps[0]).toMatch(/CPU and memory utilization/i);
  });

  it('falls back to investigate playbook for unknown action types', () => {
    const action = { action_type: 'buy_reservation' };
    const steps = resolveActionImplementationSteps(action, []);
    expect(steps.length).toBeGreaterThan(2);
    expect(steps[0]).toMatch(/stable monthly spend/i);
  });
});
