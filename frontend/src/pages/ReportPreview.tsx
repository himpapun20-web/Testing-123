import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Camera, CheckCircle2, ClipboardCheck, Download, ExternalLink, Files, GitBranch, RefreshCw, Upload, X } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { api, type ProjectReportData, type SurveyUploadRow } from '../lib/api';
import SitePlanUploader from '../components/SitePlanUploader';

type Props = { canGenerate: boolean; canUpload: boolean };
type ReviewRow = SurveyUploadRow & { parsed: boolean; parse_error: string | null };
const shown = (value: unknown) => value === null || value === undefined || value === '' ? 'Not provided' : String(value);
const formatBytes = (bytes: number) => bytes < 1024 * 1024
  ? bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`
  : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

export default function ReportPreview({ canGenerate, canUpload }: Props) {
  const { projectId } = useParams();
  const [summary, setSummary] = useState<ProjectReportData | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ loaded: number; total: number } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [iframeKey, setIframeKey] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([]);
  const [parsing, setParsing] = useState(false);

  async function loadSummary() {
    if (!projectId) return;
    setLoading(true); setError('');
    try { setSummary(await api.reportData(projectId)); } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }
  useEffect(() => { void loadSummary(); }, [projectId, refreshKey]);
  const project = summary?.project;
  const htmlUrl = projectId ? `/api/projects/${projectId}/report.html?refresh=${iframeKey}` : '';
  const pdfUrl = projectId ? `/api/projects/${projectId}/report.pdf` : '';
  const ready = useMemo(() => reviewRows.length > 0 && reviewRows.every((row) => row.inspection_date && row.start_manhole.trim() && row.finish_manhole.trim() && row.survey_length_m !== ''), [reviewRows]);
  const uploadPercent = uploadProgress?.total ? Math.min(100, Math.round(uploadProgress.loaded / uploadProgress.total * 100)) : 0;

  async function selectFiles(files: File[]) {
    if (files.length > 50) { setError('Select no more than 50 videos in one batch.'); return; }
    setSelectedFiles(files); setReviewRows([]); setError(''); setNotice('');
    if (!projectId || !files.length) return;
    setParsing(true);
    try {
      const result = await api.filenamePreview(projectId, files.map((file) => file.name));
      setReviewRows(result.items.map((item) => ({
        file_name: item.file_name,
        inspection_date: item.inspection_date || '',
        survey_end_date: item.survey_end_date && item.survey_end_date !== item.inspection_date ? item.survey_end_date : null,
        start_manhole: item.start_manhole || '',
        finish_manhole: item.finish_manhole || '',
        inspection_direction: item.inspection_direction || 'DOWNSTREAM',
        pipe_material_code: item.material_code || '',
        pipe_size_mm: item.pipe_size_mm || '',
        survey_length_m: item.survey_length_m || '',
        filename_location: item.filename_location || null,
        source_date_label: item.source_date_label || null,
        parsed: item.parsed,
        parse_error: item.error,
      })));
    } catch (e) { setError((e as Error).message); }
    finally { setParsing(false); }
  }
  function removeSelectedFile(index: number) {
    if (uploading) return;
    setSelectedFiles((previous) => previous.filter((_, fileIndex) => fileIndex !== index));
    setReviewRows((previous) => previous.filter((_, rowIndex) => rowIndex !== index));
    setError('');
  }
  function changeRow(index: number, key: keyof SurveyUploadRow, value: string) {
    setReviewRows((previous) => previous.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value || null, parsed: false, parse_error: null } : row));
  }
  async function uploadBatch() {
    if (!projectId || !ready || selectedFiles.length !== reviewRows.length) return;
    setUploading(true); setError(''); setNotice('');
    setUploadProgress({ loaded: 0, total: selectedFiles.reduce((total, file) => total + file.size, 0) });
    const payload: SurveyUploadRow[] = reviewRows.map(({ parsed: _parsed, parse_error: _parseError, ...row }) => ({ ...row, survey_end_date: row.survey_end_date || null, pipe_material_code: row.pipe_material_code || null, pipe_size_mm: row.pipe_size_mm || null, filename_location: row.filename_location || null, source_date_label: row.source_date_label || null }));
    try {
      const result = await api.uploadSurveyBatch(projectId, selectedFiles, payload, (loaded, total) => setUploadProgress({ loaded, total }));
      setNotice(`${result.count} CCTV video file${result.count === 1 ? '' : 's'} uploaded. Separate inspection records were created and the project survey dates were updated.`);
      setSelectedFiles([]); setReviewRows([]);
      setRefreshKey((value) => value + 1); setIframeKey((value) => value + 1);
    } catch (e) { setError((e as Error).message); }
    finally { setUploading(false); setUploadProgress(null); }
  }
  function refreshReport() { setRefreshKey((key) => key + 1); setIframeKey((key) => key + 1); }
  if (!projectId) return <div className="alert alert-error">A project identifier is required.</div>;

  return <div className="page-stack report-preview-page">
    <section className="page-heading"><div><div className="eyebrow">PROJECT REPORT / SAVED SURVEY DATA</div><h1>Generate project report</h1><p>Review filename-derived data, upload the CCTV survey files, record defect events and generate this project's English report.</p></div><div className="heading-actions"><Link className="button button-quiet" to="/"><ArrowLeft size={15} /> Dashboard</Link><button className="button button-quiet" onClick={refreshReport} disabled={loading}><RefreshCw size={15} /> Refresh report</button>{canGenerate ? <a className="button button-primary" href={pdfUrl}><Download size={15} /> Generate / download PDF</a> : <span className="status-pill">PDF generation requires a Project Manager</span>}</div></section>
    {error && <div className="alert alert-error">{error}</div>}{notice && <div className="alert alert-success">{notice}</div>}
    {loading ? <div className="empty-state">Loading project data…</div> : project && <>
      <section className="panel report-project-card"><div className="panel-heading"><div><div className="eyebrow">{shown(project.project_code)}</div><h2>{shown(project.project_name)}</h2><p>{shown(project.client_name)} · {shown(project.location)} · Report date: {shown(project.report_date)}</p></div><span className={`status-pill status-${String(project.report_status || '').toLowerCase()}`}>{shown(project.report_status).replaceAll('_', ' ')}</span></div>
        <div className="report-steps"><Link className="report-step" to="/projects"><PencilIcon /><span><strong>Project details</strong><small>Client, location, report date and TV reference</small></span><b>{project.client_name && project.report_date ? 'Entered' : 'Review'}</b></Link><Link className="report-step" to="/pipe-sections"><GitBranch size={16} /><span><strong>Pipe sections</strong><small>Filename-derived endpoints, length and material</small></span><b>{summary?.pipe_section_count ?? 0}</b></Link><Link className="report-step" to="/inspections"><ClipboardCheck size={16} /><span><strong>Inspections & videos</strong><small>Video records and parsed survey metadata</small></span><b>{summary?.inspection_count ?? 0} · {summary?.video_count ?? 0} videos</b></Link><Link className="report-step" to={`/defects?project_id=${projectId}`}><Camera size={16} /><span><strong>Defect timeline & photos</strong><small>Enter a timestamp, distance, description and clock/code</small></span><b>Open</b></Link><div className="report-step report-step-static"><Files size={16} /><span><strong>Report output</strong><small>English HTML preview and A4 PDF</small></span><b><CheckCircle2 size={15} /> Ready to generate</b></div></div>
      </section>
      {canUpload && <section className="panel batch-panel"><div className="panel-heading"><div><div className="eyebrow">CCTV FILE IMPORT / MULTI-SELECT</div><h2>Upload survey videos</h2><p>Choose up to 50 files. Parsed data is reviewed and editable before upload.</p></div><label className="button button-primary"><Upload size={15} /> Select video files<input type="file" multiple accept="video/*,.mp4,.mov,.m4v,.mkv,.avi,.mpeg,.mpg,.webm,.ts,.vob" hidden disabled={uploading || parsing} onChange={(event) => { void selectFiles(Array.from(event.target.files || [])); event.currentTarget.value = ''; }} /></label></div>
        <div className="batch-format">Supported filename pattern: <code>YYYY-M-D[^D] [Location] StartNode to FinishNode (US|DS)(Material)(Diameter) Lengthm CCTV.mp4</code>. US = Upstream; DS = Downstream. Example: <code>2026-10-27 RWSP-B2-02 to GNB (US)(DI)(150) 0.87m CCTV.mp4</code>. Repeated filenames are retained as separate recordings.</div>
        {parsing && <div className="empty-state">Reading file names…</div>}
        {!!selectedFiles.length && !parsing && <>
          <div className="batch-summary">
            {selectedFiles.length} selected file{selectedFiles.length === 1 ? '' : 's'} · {reviewRows.filter((item) => item.parsed).length} parsed automatically · Edit any field or remove a video before saving.
          </div>
          {uploading && uploadProgress && <div className="upload-progress" role="status">
            <div className="upload-progress-label">
              <strong>{uploadProgress.total > 0 && uploadProgress.loaded >= uploadProgress.total ? 'Upload sent; saving records…' : 'Uploading video files…'}</strong>
              <span>{uploadPercent}% · {formatBytes(uploadProgress.loaded)} of {formatBytes(uploadProgress.total)}</span>
            </div>
            <div className="upload-progress-track" role="progressbar" aria-label="Video upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uploadPercent}>
              <span style={{ width: `${uploadPercent}%` }} />
            </div>
          </div>}
          <div className="table-scroll batch-table-wrap">
            <table className="batch-table">
              <thead><tr><th>Video file</th><th>Survey date</th><th>End date (optional)</th><th>Start manhole</th><th>Finish manhole</th><th>Direction</th><th>Material</th><th>Diameter (mm)</th><th>Length (m)</th><th>Filename location</th><th>Remove</th></tr></thead>
              <tbody>{reviewRows.map((row, index) => <tr key={`${row.file_name}-${index}`}>
                <td className="batch-file"><strong>{row.file_name}</strong><span className={row.parsed ? 'parse-ok' : 'parse-review'}>{row.parsed ? 'Parsed — review values' : row.parse_error || 'Manual correction required'}</span></td>
                <td><input disabled={uploading} type="date" value={row.inspection_date} onChange={(event) => changeRow(index, 'inspection_date', event.target.value)} /></td>
                <td><input disabled={uploading} type="date" value={row.survey_end_date || ''} onChange={(event) => changeRow(index, 'survey_end_date', event.target.value)} /></td>
                <td><input disabled={uploading} value={row.start_manhole} onChange={(event) => changeRow(index, 'start_manhole', event.target.value)} /></td>
                <td><input disabled={uploading} value={row.finish_manhole} onChange={(event) => changeRow(index, 'finish_manhole', event.target.value)} /></td>
                <td><select disabled={uploading} value={row.inspection_direction} onChange={(event) => changeRow(index, 'inspection_direction', event.target.value)}><option value="UPSTREAM">Upstream (US)</option><option value="DOWNSTREAM">Downstream (DS)</option></select></td>
                <td><input disabled={uploading} value={row.pipe_material_code || ''} onChange={(event) => changeRow(index, 'pipe_material_code', event.target.value)} /></td>
                <td><input disabled={uploading} type="number" min="1" step="any" value={row.pipe_size_mm || ''} onChange={(event) => changeRow(index, 'pipe_size_mm', event.target.value)} /></td>
                <td><input disabled={uploading} type="number" min="0" step="any" value={row.survey_length_m} onChange={(event) => changeRow(index, 'survey_length_m', event.target.value)} /></td>
                <td><input disabled={uploading} value={row.filename_location || ''} onChange={(event) => changeRow(index, 'filename_location', event.target.value)} /></td>
                <td><button type="button" className="icon-button batch-remove-button" disabled={uploading} aria-label={`Remove ${row.file_name} from upload`} title="Remove from upload" onClick={() => removeSelectedFile(index)}><X size={15} /></button></td>
              </tr>)}</tbody>
            </table>
          </div>
          <div className="batch-actions">
            <span className="muted">Inspection sequence numbers are assigned automatically. No operator, camera, vehicle, weather, legal-status or inspection-time fields are required.</span>
            <button className="button button-primary" disabled={!ready || uploading} onClick={() => void uploadBatch()}><Upload size={15} /> {uploading ? 'Uploading…' : `Upload ${selectedFiles.length} ${selectedFiles.length === 1 ? 'video' : 'videos'}`}</button>
          </div>
        </>}
      </section>}
      <SitePlanUploader projectId={projectId} canUpload={canUpload} onUploaded={() => { setRefreshKey((key) => key + 1); setIframeKey((key) => key + 1); }} />
      <section className="panel report-preview-panel"><div className="panel-heading"><div><div className="eyebrow">HTML PREVIEW / PROJECT-SPECIFIC</div><h2>Preview the generated report</h2></div><a className="button button-quiet button-small" href={htmlUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open HTML</a></div><div className="report-frame"><iframe key={iframeKey} title="Project CCTV survey report HTML preview" src={htmlUrl} /></div></section>
      <p className="footnote">The report reflects saved project data. Video contents are not analyzed automatically; defect events, descriptions, clock positions and optional MSCC5 codes are entered by an authorized reviewer.</p>
    </>}
  </div>;
}

function PencilIcon() { return <span className="step-icon">Project</span>; }
