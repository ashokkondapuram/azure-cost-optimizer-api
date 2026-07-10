import React, { useState } from 'react';
import { Bell, Slack, Mail, MessageSquare, Plus, Trash2, CheckCircle2, AlertTriangle, Send } from 'lucide-react';
import PageHeader from '../components/PageHeader';

const CHANNEL_TYPES = [
  { key: 'slack',  label: 'Slack',         Icon: Slack,         placeholder: 'https://hooks.slack.com/services/…' },
  { key: 'teams',  label: 'Microsoft Teams', Icon: MessageSquare, placeholder: 'https://outlook.office.com/webhook/…' },
  { key: 'email',  label: 'Email',          Icon: Mail,          placeholder: 'ops-team@corp.com' },
];

const EVENTS = ['Budget alert (80%)', 'Budget exceeded (100%)', 'Critical finding', 'Action executed', 'Action failed', 'Weekly digest', 'Drift detected'];

function ChannelCard({ ch, onDelete, onTest, onToggleEvent }) {
  const TypeMeta = CHANNEL_TYPES.find(t => t.key === ch.type);
  const Icon = TypeMeta?.Icon || Bell;
  return (
    <div className={`notif-card notif-card--${ch.type}${ch.status === 'ok' ? ' notif-card--ok' : ch.status === 'error' ? ' notif-card--error' : ''}`}>
      <div className="notif-card__head">
        <div className="notif-card__icon-wrap"><Icon size={16} /></div>
        <div>
          <div className="notif-card__name">{ch.name}</div>
          <div className="notif-card__url">{ch.url}</div>
        </div>
        <div className="notif-card__status">
          {ch.status === 'ok'    && <span className="badge badge-ok"><CheckCircle2 size={11} /> Connected</span>}
          {ch.status === 'error' && <span className="badge badge-critical"><AlertTriangle size={11} /> Error</span>}
          {ch.status === 'idle'  && <span className="badge">Not tested</span>}
        </div>
        <div className="notif-card__actions">
          <button className="btn btn-sm btn-ghost" onClick={() => onTest(ch.id)} title="Send test"><Send size={12} /></button>
          <button className="btn btn-sm btn-ghost" onClick={() => onDelete(ch.id)} title="Remove"><Trash2 size={12} /></button>
        </div>
      </div>
      <div className="notif-card__events">
        <div className="notif-card__events-label">Notify on:</div>
        <div className="notif-card__event-list">
          {EVENTS.map(ev => (
            <label key={ev} className="notif-event-toggle">
              <input type="checkbox" checked={ch.events?.includes(ev)} onChange={() => onToggleEvent(ch.id, ev)} />
              {ev}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function NotificationChannels() {
  const [channels, setChannels] = useState([
    { id: 1, type: 'slack', name: 'ops-alerts', url: 'https://hooks.slack.com/services/T0…', status: 'ok', events: ['Critical finding', 'Budget alert (80%)', 'Action failed'] },
    { id: 2, type: 'email', name: 'finance-team', url: 'finance@corp.com', status: 'idle', events: ['Weekly digest', 'Budget exceeded (100%)'] },
  ]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ type: 'slack', name: '', url: '', events: [] });

  const addChannel = () => {
    if (!form.name || !form.url) return;
    setChannels(prev => [...prev, { id: Date.now(), ...form, status: 'idle' }]);
    setForm({ type: 'slack', name: '', url: '', events: [] });
    setShowForm(false);
  };

  const deleteChannel  = (id) => setChannels(prev => prev.filter(c => c.id !== id));
  const testChannel    = (id) => setChannels(prev => prev.map(c => c.id === id ? { ...c, status: 'ok' } : c));
  const toggleEvent    = (id, ev) => setChannels(prev => prev.map(c =>
    c.id === id ? { ...c, events: c.events?.includes(ev) ? c.events.filter(e => e !== ev) : [...(c.events||[]), ev] } : c
  ));

  return (
    <div className="page-shell notif-channels-page">
      <PageHeader
        title="Notification channels"
        subtitle="Configure Slack, Teams, and email webhooks for alerts and digests"
        iconKey="notificationsNav"
        iconRoute="/notifications"
      >
        <button className="btn btn-primary btn-sm" onClick={() => setShowForm(s => !s)}><Plus size={13} /> Add Channel</button>
      </PageHeader>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.25rem' }}>
          <div className="card-section-head"><Bell size={14} /><h3>New Notification Channel</h3></div>
          <div className="notif-form">
            <div className="notif-form__row">
              <div className="sched-form__field">
                <label>Type</label>
                <select value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value }))}>
                  {CHANNEL_TYPES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </div>
              <div className="sched-form__field">
                <label>Name / label</label>
                <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. ops-slack" />
              </div>
              <div className="sched-form__field" style={{ flex: 2 }}>
                <label>Webhook URL / Email</label>
                <input value={form.url} onChange={e => setForm(p => ({ ...p, url: e.target.value }))} placeholder={CHANNEL_TYPES.find(t => t.key === form.type)?.placeholder} />
              </div>
            </div>
            <div className="sched-form__actions">
              <button className="btn btn-sm btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-sm btn-primary" onClick={addChannel}>Save Channel</button>
            </div>
          </div>
        </div>
      )}

      <div className="notif-channel-list">
        {channels.length === 0 && <div className="empty-state"><Bell size={28} /><p>No channels configured yet.</p></div>}
        {channels.map(ch => <ChannelCard key={ch.id} ch={ch} onDelete={deleteChannel} onTest={testChannel} onToggleEvent={toggleEvent} />)}
      </div>
    </div>
  );
}
