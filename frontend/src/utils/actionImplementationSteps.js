/** Resolve ordered implementation steps for a proposed optimization action. */

const ACTION_PLAYBOOK_STEPS = {
  resize_down: [
    'Review 14–30 day CPU and memory utilization in Azure Monitor',
    'Confirm a maintenance window and rollback SKU with the application owner',
    'Resize the VM to the recommended SKU in Azure Portal or your IaC pipeline',
    'Monitor CPU, memory, and application latency for 48 hours after the change',
  ],
  downgrade_disk: [
    'Confirm no active restore, backup, or replication dependency on the current disk tier',
    'Take a snapshot if the workload needs a rollback path',
    'Change disk SKU or size during a maintenance window',
    'Validate application I/O and latency after the downgrade',
  ],
  buy_reservation: [
    'Confirm stable monthly spend for this resource over the past 30–90 days',
    'Compare 1-year vs 3-year reservation and savings plan options in Cost Management',
    'Purchase the reservation with the correct scope, region, and SKU',
    'Track reservation utilization in Cost Management after purchase',
  ],
  decommission: [
    'Confirm the resource is unused and list downstream dependencies',
    'Export configuration, backups, or data retention requirements',
    'Deallocate or delete the resource in a controlled change window',
    'Verify recurring charges stop in the next billing cycle',
  ],
  investigate: [
    'Open cost and utilization metrics for this resource in Azure Monitor',
    'Compare spend and utilization against peer resources in the subscription',
    'Document findings, then approve or reject the proposed action in Action centre',
  ],
  manual_review: [
    'Review SLA, dependency, and performance constraints with the application owner',
    'Validate blast radius and rollback plan before any change',
    'Approve, defer, or reject the action in Action centre with notes',
  ],
  keep: [],
};

/** Action-type playbook steps for proposed optimization actions. */
export function resolveActionImplementationSteps(action) {
  const playbook = ACTION_PLAYBOOK_STEPS[action?.action_type];
  if (playbook?.length) return [...playbook];
  return ACTION_PLAYBOOK_STEPS.investigate;
}
