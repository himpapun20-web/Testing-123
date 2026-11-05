export type Session = { authenticated: boolean; auth_mode?: string; login_url?: string; user?: { id: string; name: string; email: string; role: string } };
export type Row = Record<string, unknown> & { id: string; created_at?: string; updated_at?: string };
export type ListResult = { items: Row[]; limit: number; offset: number };
export type ProjectReportData = { project: Row; company_name: string; pipe_section_count: number; inspection_count: number; video_count: number };
export type FilenameParseResult = {
  file_name: string; parsed: boolean; error: string | null; inspection_date: string | null; survey_end_date: string | null;
  start_manhole: string | null; finish_manhole: string | null; inspection_direction: 'UPSTREAM' | 'DOWNSTREAM' | null;
  material_code: string | null; pipe_size_mm: string | null; survey_length_m: string | null; filename_location: string | null; source_date_label: string | null;
};
export type SurveyUploadRow = {
  file_name: string; inspection_date: string; survey_end_date: string | null; start_manhole: string; finish_manhole: string;
  inspection_direction: 'UPSTREAM' | 'DOWNSTREAM'; pipe_material_code: string | null; pipe_size_mm: string | null;
  survey_length_m: string; filename_location: string | null; source_date_label: string | null;
};
export type SurveyUploadResult = { count: number; created: Array<{ file_name: string; inspection_id: string; pipe_section_id: string; pipe_id: string; upstream_manhole: string; downstream_manhole: string; inspection_direction: string; inspection_date: string; survey_length_m: string }> };
export type InspectionEventInput = { event_type: string; timestamp_seconds: number; distance_m: number; observation: string; mscc_code: string | null; clock_position: string | null };
export type InspectionEvent = Row & InspectionEventInput & { event_number: number; inspection_id: string; inspection_date: string; inspection_direction: string; inspection_number: number; pipe_id: string; upstream_manhole: string; downstream_manhole: string; video_file_name: string; photo_file_name: string | null; photo_download_url: string | null };
export type DashboardData = {
  totals: { projects: number; pipe_sections: number; inspections: number };
  pipe_sections_by_status: Record<string, number>;
  inspections_by_status: Record<string, number>;
  projects: Array<{ id: string; project_code: string; project_name: string; client_name?: string; location?: string; status: string; report_status: string; pipe_section_count: number; inspection_count: number; report_date?: string }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { credentials: 'include', ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const message = Array.isArray(payload.detail) ? payload.detail.map((item: { msg?: string }) => item.msg).join('; ') : payload.detail;
    throw new Error(String(message || `HTTP ${response.status}`));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  session: () => request<Session>('/api/auth/session'),
  passwordLogin: (email: string, password: string) => request<void>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  setUserPassword: (userId: string, password: string) => request<void>(`/api/auth/users/${userId}/password`, { method: 'PUT', body: JSON.stringify({ password }) }),
  dashboard: () => request<DashboardData>('/api/dashboard'),
  list: (resource: string) => request<ListResult>(`/api/${resource}?limit=200`),
  reportData: (projectId: string) => request<ProjectReportData>(`/api/projects/${projectId}/report-data`),
  projectVideos: (projectId: string) => request<{ items: Row[] }>(`/api/projects/${projectId}/videos`),
  projectSitePlans: (projectId: string) => request<{ items: Row[] }>(`/api/projects/${projectId}/site-plans`),
  uploadSitePlan: (projectId: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<Row>(`/api/projects/${projectId}/site-plans`, { method: 'POST', body });
  },
  filenamePreview: (projectId: string, filenames: string[]) => request<{ items: FilenameParseResult[] }>(`/api/projects/${projectId}/filename-preview`, { method: 'POST', body: JSON.stringify({ filenames }) }),
  uploadSurveyBatch: (projectId: string, files: File[], rows: SurveyUploadRow[], onProgress: (loaded: number, total: number) => void) => {
    const body = new FormData();
    for (const file of files) body.append('files', file);
    body.append('metadata_json', JSON.stringify(rows));
    return new Promise<SurveyUploadResult>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/projects/${projectId}/survey-batch`);
      xhr.withCredentials = true;
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.upload.addEventListener('progress', (event) => {
        onProgress(event.loaded, event.lengthComputable ? event.total : files.reduce((total, file) => total + file.size, 0));
      });
      xhr.addEventListener('load', () => {
        let payload: unknown;
        try {
          payload = JSON.parse(xhr.responseText);
        } catch {
          reject(new Error(xhr.status >= 200 && xhr.status < 300 ? 'The upload response was not valid JSON.' : xhr.statusText || `HTTP ${xhr.status}`));
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : undefined;
          const message = Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg).join('; ') : detail;
          reject(new Error(String(message || `HTTP ${xhr.status}`)));
          return;
        }
        resolve(payload as SurveyUploadResult);
      });
      xhr.addEventListener('error', () => reject(new Error('The video upload failed because the network connection was interrupted.')));
      xhr.addEventListener('abort', () => reject(new Error('The video upload was cancelled.')));
      xhr.send(body);
    });
  },
  projectEvents: (projectId: string) => request<{ items: InspectionEvent[] }>(`/api/projects/${projectId}/events`),
  createEvent: (inspectionId: string, data: InspectionEventInput) => request<InspectionEvent>(`/api/inspections/${inspectionId}/events`, { method: 'POST', body: JSON.stringify(data) }),
  updateEvent: (eventId: string, data: InspectionEventInput) => request<InspectionEvent>(`/api/events/${eventId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  removeEvent: (eventId: string) => request<void>(`/api/events/${eventId}`, { method: 'DELETE' }),
  create: (resource: string, data: Record<string, unknown>) => request<Row>(`/api/${resource}`, { method: 'POST', body: JSON.stringify(data) }),
  update: (resource: string, id: string, data: Record<string, unknown>) => request<Row>(`/api/${resource}/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  remove: (resource: string, id: string) => request<void>(`/api/${resource}/${id}`, { method: 'DELETE' }),
};
