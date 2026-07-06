import React, { useState } from 'react';
import { Plus, Trash2, Save, Play } from 'lucide-react';

const FIELDS     = ['CPU avg %', 'Memory avg %', 'Disk IOPS', 'VM SKU', 'Environment tag', 'Owner tag', 'Days running', 'Cost/month'];
const OPERATORS  = ['<', '<=', '>', '>=', '=', '!=', 'contains', 'not contains'];
const ACTIONS    = ['Propose resize', 'Propose deallocate', 'Propose delete', 'Add tag', 'Send alert', 'Snooze 7d'];

function ConditionRow({ cond, index, onChange, onDelete }) {
  return (
    <div className="rule-condition-row">
      {index > 0 && <span className="rule-condition-row__and">AND</span>}
      <select value={cond.field} onChange={e => onChange(index, 'field', e.target.value)}>
        {FIELDS.map(f => <option key={f}>{f}</option>)}
      </select>
      <select value={cond.op} onChange={e => onChange(index, 'op', e.target.value)}>
        {OPERATORS.map(o => <option key={o}>{o}</option>)}
      </select>
      <input value={cond.value} placeholder="Value…"
        onChange={e => onChange(index, 'value', e.target.value)} />
      <button type="button" className="btn btn-sm btn-ghost" onClick={() => onDelete(index)} title="Remove condition">
        <Trash2 size={12} />
      </button>
    </div>
  );
}

export default function PolicyRuleBuilder({ onSave }) {
  const [name, setName]       = useState('');
  const [scope, setScope]     = useState('all');
  const [action, setAction]   = useState(ACTIONS[0]);
  const [saved, setSaved]     = useState(false);
  const [conditions, setConds] = useState([
    { field: FIELDS[0], op: '<', value: '10' },
  ]);

  const addCond = () => setConds(prev => [...prev, { field: FIELDS[0], op: '<', value: '' }]);
  const delCond = (i) => setConds(prev => prev.filter((_, idx) => idx !== i));
  const updateCond = (i, key, val) => setConds(prev => prev.map((c, idx) => idx === i ? { ...c, [key]: val } : c));

  const handleSave = () => {
    if (!name) return;
    onSave?.({ name, scope, conditions, action });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="rule-builder">
      <div className="rule-builder__header">
        <div className="rule-builder__field">
          <label className="rule-builder__label">Rule name</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Flag idle VMs" />
        </div>
        <div className="rule-builder__field">
          <label className="rule-builder__label">Scope</label>
          <select value={scope} onChange={e => setScope(e.target.value)}>
            <option value="all">All resources</option>
            <option value="vm">Virtual Machines</option>
            <option value="aks">AKS Clusters</option>
            <option value="disk">Disks</option>
            <option value="dev">Dev environment only</option>
          </select>
        </div>
      </div>

      <div className="rule-builder__section">
        <div className="rule-builder__section-label">IF all conditions are true:</div>
        <div className="rule-builder__conditions">
          {conditions.map((c, i) => (
            <ConditionRow key={i} cond={c} index={i} onChange={updateCond} onDelete={delCond} />
          ))}
          <button type="button" className="btn btn-sm btn-ghost rule-builder__add-cond" onClick={addCond}>
            <Plus size={12} /> Add condition
          </button>
        </div>
      </div>

      <div className="rule-builder__section">
        <div className="rule-builder__section-label">THEN:</div>
        <select value={action} onChange={e => setAction(e.target.value)}>
          {ACTIONS.map(a => <option key={a}>{a}</option>)}
        </select>
      </div>

      <div className="rule-builder__actions">
        <button type="button" className="btn btn-sm btn-ghost">
          <Play size={13} /> Test rule
        </button>
        <button type="button" className={`btn btn-sm btn-primary${saved ? ' btn-saved' : ''}`} onClick={handleSave}>
          <Save size={13} /> {saved ? 'Saved!' : 'Save Rule'}
        </button>
      </div>
    </div>
  );
}
