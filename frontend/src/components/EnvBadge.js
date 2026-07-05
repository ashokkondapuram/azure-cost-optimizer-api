import React from 'react';
import { Shield, FlaskConical, Code2 } from 'lucide-react';

const ENV_CONFIG = {
  prod: { label: 'Production', className: 'prod', Icon: Shield },
  staging: { label: 'Staging', className: 'staging', Icon: FlaskConical },
  dev: { label: 'Dev', className: 'dev', Icon: Code2 },
};

export default function EnvBadge({ env }) {
  const cfg = ENV_CONFIG[env] || ENV_CONFIG.dev;
  const { label, className, Icon } = cfg;

  return (
    <span className={`env-badge env-badge--${className}`}>
      <Icon className="env-badge__icon" size={11} aria-hidden="true" />
      <span className="env-badge__dot" aria-hidden="true" />
      {label}
    </span>
  );
}
