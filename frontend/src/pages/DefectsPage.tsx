import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Camera, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, type InspectionEvent, type InspectionEventInput, type Row } from '../lib/api';

type Props = { role: string };
const formatVideoTime = (seconds: number) => { const n = Math.max(0, Math.floor(seconds)); return `${String(Math.floor(n / 3600)).padStart(2, '0')}:${String(Math.floor((n % 3600) / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`; };
const display = (value: unknown) => value === null || value === undefined || value === '' ? 'Not provided' : String(value);
const emptyForm = { inspection_id: '', event_type: 'DEFECT', timestamp_seconds: '', distance_m: '', observation: '', mscc_code: '', clock_position: '' };

export default function DefectsPage({ role }: Props) {
  const [search] = useSearchParams();
  const canWrite = ['ADMIN', 'PROJECT_MANAGER', 'OPERATOR'].includes(role);
  const [projects, setProjects] = useState<Row[]>([]);
  const [pipes, setPipes] = useState<Row[]>([]);
  const [inspections, setInspections] = useState<Row[]>([]);
  const [projectId, setProjectId] = useState(search.get('project_id') || '');
  const [events, setEvents] = useState<InspectionEvent[]>([]);
  const [editing, setEditing] = useState<InspectionEvent | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadReferences() {
    setLoading(true); setError('');
    try {
      const [projectList, pipeList, inspectionList] = await Promise.all([api.list('projects'), api.list('pipe-sections'), api.list('inspections')]);
      setProjects(projectList.items); setPipes(pipeList.items); setInspections(inspectionList.items);
      const initialProject = search.get('project_id') || projectId || String(projectList.items[0]?.id || '');
      if (!projectId && initialProject) setProjectId(initialProject);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }
  async function loadEvents(id = projectId) {
    if (!id) { setEvents([]); return; }
    try { setEvents((await api.projectEvents(id)).items); } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void loadReferences(); }, []);
  useEffect(() => { void loadEvents(projectId); }, [projectId]);

  const pipeById = useMemo(() => new Map(pipes.map((pipe) => [String(pipe.id), pipe])), [pipes]);
  const projectInspections = inspections.filter((inspection) => String(pipeById.get(String(inspection.pipe_section_id))?.project_id || '') === projectId && Boolean(inspection.video_asset_id));
  const inspectionById = useMemo(() => new Map(projectInspections.map((inspection) => [String(inspection.id), inspection])), [projectInspections]);
  const selectedInspection = inspectionById.get(form.inspection_id);
  const selectedPipe = selectedInspection ? pipeById.get(String(selectedInspection.pipe_section_id)) : undefined;

  function openNew() { setEditing(null); setForm({ ...emptyForm, inspection_id: String(projectInspections[0]?.id || '') }); setError(''); setNotice(''); }
  function openEdit(event: InspectionEvent) {
    setEditing(event);
    setForm({ inspection_id: event.inspection_id, event_type: event.event_type.replaceAll(' ', '_').toUpperCase(), timestamp_seconds: String(event.timestamp_seconds), distance_m: String(event.distance_m), observation: event.observation, mscc_code: event.mscc_code || '', clock_position: event.clock_position || '' });
    setError(''); setNotice('');
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setSaving(true); setError(''); setNotice('');
    const payload: InspectionEventInput = { event_type: form.event_type, timestamp_seconds: Number(form.timestamp_seconds), distance_m: Number(form.distance_m), observation: form.observation.trim(), mscc_code: form.mscc_code.trim() || null, clock_position: form.clock_position.trim() || null };
    try {
      if (editing) await api.updateEvent(editing.id, payload);
      else await api.createEvent(form.inspection_id, payload);
      setNotice('Event saved. A still frame was extracted from the selected CCTV video at the recorded time.');
      setEditing(null); setForm(emptyForm); await loadEvents();
    } catch (err) { setError((err as Error).message); }
    finally { setSaving(false); }
  }
  async function remove(event: InspectionEvent) {
    if (!window.confirm(`Delete event ${event.event_number} and its extracted frame?`)) return;
    try { await api.removeEvent(event.id); setNotice('Event and frame deleted.'); await loadEvents(); } catch (err) { setError((err as Error).message); }
  }

  const sectionLength = Number(selectedPipe?.survey_length_m || selectedInspection?.preset_length_m || 0);
  const orderedEvents = [...events].sort((a, b) => Number(a.distance_m) - Number(b.distance_m) || a.event_number - b.event_number);
  return <div className="page-stack">
    <section className="page-heading"><div><div className="eyebrow">APPENDIX III / EVIDENCE LOG</div><h1>Defect timeline & photos</h1><p>Record an event at a video timestamp and section distance. The server captures a genuine still from that CCTV file.</p></div><div className="heading-actions"><label className="form-field inline-field">Project<select value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">Select a project</option>{projects.map((project) => <option key={String(project.id)} value={String(project.id)}>{String(project.project_name)} · {String(project.project_code)}</option>)}</select></label><button className="button button-quiet" onClick={() => void loadEvents()}><RefreshCw size={15} /> Refresh</button>{canWrite && <button className="button button-primary" disabled={!projectInspections.length} onClick={openNew}><Camera size={15} /> Add event</button>}</div></section>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {loading ? <div className="empty-state">Loading survey evidence…</div> : !projectInspections.length ? <section className="panel empty-state">No imported CCTV inspections with linked video are available for this project. <Link to={projectId ? `/report/${projectId}` : '/'}>Open a project report to upload video files.</Link></section> : <>
      <section className="panel evidence-panel"><div className="panel-heading"><div><div className="eyebrow">TIMELINE / SAVED EVENTS</div><h2>{projectInspections.length} video inspection{projectInspections.length === 1 ? '' : 's'} · {orderedEvents.length} event{orderedEvents.length === 1 ? '' : 's'}</h2></div></div>
        <div className="table-scroll"><table><thead><tr><th>Pipe / Inspection</th><th>Video Time</th><th>Distance (m)</th><th>Event</th><th>Clock</th><th>MSCC5 Code</th><th>Description</th>{canWrite && <th>Actions</th>}</tr></thead><tbody>{orderedEvents.map((event) => <tr key={event.id}><td><strong>{event.pipe_id}</strong><span className="table-sub">Inspection {event.inspection_number} · {display(event.inspection_date)} · {event.inspection_direction}</span></td><td className="mono">{formatVideoTime(Number(event.timestamp_seconds))}</td><td>{event.distance_m}</td><td>{event.event_type.replaceAll('_', ' ')}</td><td>{display(event.clock_position)}</td><td className="mono">{display(event.mscc_code)}</td><td>{event.observation}</td>{canWrite && <td><button className="icon-button" title="Edit event" aria-label="Edit event" onClick={() => openEdit(event)}><Pencil size={15} /></button><button className="icon-button danger" title="Delete event" aria-label="Delete event" onClick={() => void remove(event)}><Trash2 size={15} /></button></td>}</tr>)}{!orderedEvents.length && <tr><td colSpan={canWrite ? 8 : 7} className="empty-state">No events recorded yet.</td></tr>}</tbody></table></div>
      </section>
      <section className="panel evidence-panel"><div className="panel-heading"><div><div className="eyebrow">SECTION PROFILE</div><h2>Distance timeline</h2></div></div><div className="timeline-list">{projectInspections.map((inspection) => { const pipe = pipeById.get(String(inspection.pipe_section_id)); const list = orderedEvents.filter((event) => event.inspection_id === inspection.id); const length = Number(pipe?.survey_length_m || inspection.preset_length_m || 0); return <article className="inspection-timeline" key={String(inspection.id)}><header><strong>{String(pipe?.pipe_id || 'Pipe')} · Inspection {String(inspection.inspection_number)}</strong><span>{display(inspection.inspection_date)} · {String(inspection.inspection_direction).replaceAll('_', ' ')} · {length || '—'} m</span></header>{list.length ? <div className="timeline-row"><div className="timeline-rail"><span className="rail-end">0 m</span><div className="rail-line">{list.map((event) => { const position = length > 0 ? Math.min(100, Math.max(0, Number(event.distance_m) / length * 100)) : 0; return <i key={event.id} className="rail-marker" style={{ top: `${position}%` }} title={`${event.distance_m} m · ${formatVideoTime(Number(event.timestamp_seconds))}`} />; })}</div><span className="rail-end">{length || '—'} m</span></div><div className="timeline-event-list">{list.map((event) => <article className="timeline-event-card" key={event.id}><div className="event-image">{event.photo_download_url ? <img src={event.photo_download_url} alt={`Extracted frame for ${event.event_type} at ${formatVideoTime(Number(event.timestamp_seconds))}`} /> : <span>No extracted frame</span>}</div><div className="event-card-copy"><div className="eyebrow">{event.event_type.replaceAll('_', ' ')} · {formatVideoTime(Number(event.timestamp_seconds))} · {event.distance_m} m</div><h3>{event.observation}</h3><p>Clock position: {display(event.clock_position)} · MSCC5 code: {display(event.mscc_code)}</p><span className="small muted">Video: {event.video_file_name}</span></div></article>)}</div></div> : <div className="empty-state">No observations recorded for this inspection.</div>}</article>; })}</div></section>
    </>}
    {canWrite && form.inspection_id && <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setEditing(null); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="event-title"><header className="modal-header"><div><div className="eyebrow">VIDEO EVENT / FRAME EXTRACTION</div><h2 id="event-title">{editing ? 'Edit inspection event' : 'Add inspection event'}</h2></div><button className="icon-button" aria-label="Close" onClick={() => setEditing(null)}>×</button></header>{error && <div className="alert alert-error">{error}</div>}<form onSubmit={(e) => void submit(e)}><div className="form-grid"><div className="form-field form-wide"><label htmlFor="inspection_id">Inspection / CCTV video *</label><select id="inspection_id" required value={form.inspection_id} disabled={Boolean(editing)} onChange={(e) => setForm({ ...form, inspection_id: e.target.value })}>{projectInspections.map((inspection) => { const pipe = pipeById.get(String(inspection.pipe_section_id)); return <option key={String(inspection.id)} value={String(inspection.id)}>{String(pipe?.pipe_id || 'Pipe')} · #{String(inspection.inspection_number)} · {display(inspection.inspection_date)} · {String((inspection as Row).video_asset_id || '')}</option>; })}</select></div><div className="form-field"><label htmlFor="event_type">Event type *</label><select id="event_type" value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })}><option value="DEFECT">Defect</option><option value="START_NODE">Start Node</option><option value="WATER_LEVEL">Water Level</option><option value="GENERAL_PHOTO">General Photo</option><option value="FINISH_NODE">Finish Node</option><option value="SITE_PHOTO">Site Photo</option></select></div><div className="form-field"><label htmlFor="timestamp_seconds">Video time (seconds) *</label><input id="timestamp_seconds" type="number" min="0" max="86400" step="0.001" required value={form.timestamp_seconds} onChange={(e) => setForm({ ...form, timestamp_seconds: e.target.value })} placeholder="Example: 57.5" /></div><div className="form-field"><label htmlFor="distance_m">Distance along pipe (m) *</label><input id="distance_m" type="number" min="0" max={sectionLength || 100000} step="0.01" required value={form.distance_m} onChange={(e) => setForm({ ...form, distance_m: e.target.value })} /></div><div className="form-field"><label htmlFor="clock_position">Clock position</label><input id="clock_position" value={form.clock_position} onChange={(e) => setForm({ ...form, clock_position: e.target.value })} placeholder="Example: 3 o'clock" /></div><div className="form-field"><label htmlFor="mscc_code">MSCC5 code (optional)</label><input id="mscc_code" value={form.mscc_code} onChange={(e) => setForm({ ...form, mscc_code: e.target.value })} placeholder="Enter code if known" /></div><div className="form-field form-wide"><label htmlFor="observation">Defect / event description *</label><textarea id="observation" minLength={1} maxLength={2000} required rows={4} value={form.observation} onChange={(e) => setForm({ ...form, observation: e.target.value })} placeholder="Describe the observed pipe condition." /></div></div><div className="alert alert-info">The server will extract an actual still frame from this CCTV video at the entered time. An invalid video time or unreadable file will be rejected; no sample image is substituted.</div><footer className="modal-footer"><span className="muted">Frame extraction uses video seconds and does not perform AI defect detection.</span><div><button type="button" className="button button-quiet" onClick={() => setEditing(null)}>Cancel</button><button type="submit" className="button button-primary" disabled={saving}>{saving ? 'Extracting frame…' : 'Save event & frame'}</button></div></footer></form></section></div>}
  </div>;
}
