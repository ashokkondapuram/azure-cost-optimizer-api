import React, { useState } from 'react';
import { Clock, Plus, Trash2, Play, CheckCircle, Calendar } from 'lucide-react';
import PageHeader from '../components/PageHeader';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);
const ACTIONS = ['Deallocate dev VMs', 'Right-size underutil VMs', 'Delete orphaned disks', 'Scale down AKS node pools', 'Apply safe tag fixes', 'Send weekly digest'];
const SCOPES  = ['All resources', 'Dev environment only', 'Staging environment', 'Non-prod', 'Tagged: auto-schedule=true'];

const MOCK_SCHEDULES = [
  { id: 1, name: 'Nightly dev shutdown', action: ACTIONS[0], days: ['Mon','Tue','Wed','Thu','Fri'], time: '19:00', scope: SCOPES[1], enabled: true, lastRun: '2026-07-04 19:00', nextRun: '2026-07-07 19:00' },
  { id: 2, name: 'Weekly digest',        action: ACTIONS[5], days: ['Mon'],                         time: '08:00', scope: SCOPES[0], enabled: true, lastRun: '2026-06-30 08:00', nextRun: '2026-07-07 08:00' },
];

function ScheduleCard({ s, onToggle, onDelete }) {
  return (
    <div className={`schedule-card${s.enabled ? '' : ' schedule-card--disabled'}`}>
      <div className="schedule-card__head">
        <span className="schedule-card__name">{s.name}</span>
        <div className="schedule-card__controls">
          <button className={`toggle-pill${s.enabled ? ' toggle-pill--on' : ''}`} onClick={() => onToggle(s.id)}>
            {s.enabled ? 'Enabled' : 'Disabled'}
          </button>
          <button className="btn btn-sm btn-ghost" onClick={() => onDelete(s.id)} title="Delete"><Trash2 size={12} /></button>
        </div>
      </div>
      <div className="schedule-card__body">
        <div className="schedule-card__row"><Play size={12} /> <strong>Action:</strong> {s.action}</div>
        <div className="schedule-card__row"><Calendar size={12} /> <strong>Days:</strong> {s.days.join(', ')}</div>
        <div className="schedule-card__row"><Clock size={12} /> <strong>Time:</strong> {s.time} UTC</div>
        <div className="schedule-card__row"><CheckCircle size={12} /> <strong>Scope:</strong> {s.scope}</div>
      </div>
      <div className="schedule-card__footer">
        <span className="schedule-card__meta">Last run: {s.lastRun}</span>
        <span className="schedule-card__meta schedule-card__meta--next">Next: {s.nextRun}</span>
      </div>
    </div>
  );
}

export default function AutoScheduler() {
  const [schedules, setSchedules] = useState(MOCK_SCHEDULES);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', action: ACTIONS[0], days: [], time: '19:00', scope: SCOPES[0] });

  const toggleDay = (day) => setForm(p => ({
    ...p,
    days: p.days.includes(day) ? p.days.filter(d => d !== day) : [...p.days, day],
  }));

  const saveSchedule = () => {
    if (!form.name || !form.days.length) return;
    setSchedules(prev => [...prev, { id: Date.now(), ...form, enabled: true, lastRun: '—', nextRun: 'Calculated on save' }]);
    setForm({ name: '', action: ACTIONS[0], days: [], time: '19:00', scope: SCOPES[0] });
    setShowForm(false);
  };

  const toggleSchedule = (id) => setSchedules(prev => prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s));
  const deleteSchedule = (id) => setSchedules(prev => prev.filter(s => s.id !== id));

  return (
    <div className="page-shell auto-scheduler-page">
      <PageHeader
        title="Auto scheduler"
        subtitle="Schedule safe optimization actions to run automatically in maintenance windows"
        iconKey="autoScheduler"
        iconRoute="/auto-scheduler"
      >
        <button className="btn btn-primary btn-sm" onClick={() => setShowForm(s => !s)}><Plus size={13} /> New Schedule</button>
      </PageHeader>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.25rem' }}>
          <div className="card-section-head"><Clock size={14} /><h3>New Maintenance Schedule</h3></div>
          <div className="sched-form">
            <div className="sched-form__row">
              <div className="sched-form__field">
                <label>Schedule name</label>
                <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Nightly dev shutdown" />
              </div>
              <div className="sched-form__field">
                <label>Action</label>
                <select value={form.action} onChange={e => setForm(p => ({ ...p, action: e.target.value }))}>
                  {ACTIONS.map(a => <option key={a}>{a}</option>)}
                </select>
              </div>
              <div className="sched-form__field">
                <label>Scope</label>
                <select value={form.scope} onChange={e => setForm(p => ({ ...p, scope: e.target.value }))}>
                  {SCOPES.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div className="sched-form__field">
                <label>Time (UTC)</label>
                <select value={form.time} onChange={e => setForm(p => ({ ...p, time: e.target.value }))}>
                  {HOURS.map(h => <option key={h}>{h}</option>)}
                </select>
              </div>
            </div>
            <div className="sched-form__days">
              <label>Run on days:</label>
              <div className="day-picker">
                {DAYS.map(d => (
                  <button key={d} type="button"
                    className={`day-btn${form.days.includes(d) ? ' day-btn--active' : ''}`}
                    onClick={() => toggleDay(d)}>{d}</button>
                ))}
              </div>
            </div>
            <div className="sched-form__actions">
              <button className="btn btn-sm btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-sm btn-primary" onClick={saveSchedule}>Save Schedule</button>
            </div>
          </div>
        </div>
      )}

      <div className="schedule-list">
        {schedules.length === 0 && (
          <div className="empty-state"><Clock size={28} /><p>No schedules yet. Create one to automate safe actions.</p></div>
        )}
        {schedules.map(s => <ScheduleCard key={s.id} s={s} onToggle={toggleSchedule} onDelete={deleteSchedule} />)}
      </div>
    </div>
  );
}
