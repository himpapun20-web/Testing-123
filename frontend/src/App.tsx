import { useEffect, useState, type FormEvent } from 'react';
import {
  Activity,
  ArrowRight,
  Building2,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  Files,
  FileText,
  GitBranch,
  LogOut,
  Menu,
  PanelLeftClose,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react';
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { api, type Session } from './lib/api';
import Dashboard from './pages/Dashboard';
import ResourcePage from './pages/ResourcePage';
import ReportPreview from './pages/ReportPreview';
import DefectsPage from './pages/DefectsPage';

const navigation = [
  { to: '/', label: 'Dashboard', icon: Activity, end: true },
  { to: '/projects', label: 'Projects', icon: Files },
  { to: '/pipe-sections', label: 'Pipe Sections', icon: GitBranch },
  { to: '/inspections', label: 'Inspections', icon: ClipboardCheck },
  { to: '/defects', label: 'Defects & Photos', icon: Camera },
  { to: '/assets', label: 'Files & Evidence', icon: Files },
  { to: '/users', label: 'Users & Roles', icon: Users },
  { to: '/company', label: 'Company Profile', icon: Building2 },
];

const resourceForPath: Record<string, string> = {
  '/projects': 'projects',
  '/pipe-sections': 'pipe-sections',
  '/inspections': 'inspections',
  '/assets': 'assets',
  '/users': 'users',
  '/company': 'companies',
};

const roleName: Record<string, string> = {
  ADMIN: 'Administrator',
  PROJECT_MANAGER: 'Project Manager',
  OPERATOR: 'Operator',
  VIEWER: 'Viewer',
  AI_SERVICE: 'AI Service',
};

function SignIn({ mode, onPasswordLogin }: { mode?: string; onPasswordLogin: (email: string, password: string) => Promise<void> }) {
  const [redirecting, setRedirecting] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleContinue = () => {
    setRedirecting(true);
    window.location.assign('/api/auth/login');
  };

  async function submitPasswordLogin(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setPasswordError('');
    try {
      await onPasswordLogin(email, password);
    } catch (error) {
      setPasswordError((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="signin-screen">
      <div className="signin-card">
        <section className="signin-main">
          <div className="signin-brandline">
            <div className="brand-mark signin-brand-mark">CCTV</div>
            <div className="signin-product">
              <strong>Survey</strong>
              <span>Report Automation</span>
            </div>
          </div>

          <div className="signin-copy">
            <div className="eyebrow">{mode === 'password' ? 'SECURE ACCOUNT ACCESS' : 'LOCAL WORKSPACE ACCESS'}</div>
            <h1>{mode === 'password' ? <>Sign in to your<br />reporting workspace.</> : <>Secure project<br />reporting from one place.</>}</h1>
            <p>{mode === 'password' ? 'Enter the email address and password provided by your workspace administrator.' : 'Review pipe sections, validate field evidence and prepare clear engineering reports from one workspace.'}</p>

            {mode === 'password' ? <form className="signin-password-form" onSubmit={(event) => void submitPasswordLogin(event)}>
              <label htmlFor="signin-email">Email address</label>
              <input id="signin-email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
              <label htmlFor="signin-password">Password</label>
              <input id="signin-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
              {passwordError && <div className="signin-form-error" role="alert">{passwordError}</div>}
              <button type="submit" className="button button-primary signin-button" disabled={submitting}>
                <span>{submitting ? 'Signing in…' : 'Sign in'}</span>
                <ArrowRight size={17} />
              </button>
            </form> : <button type="button" onClick={handleContinue} className="button button-primary signin-button" disabled={redirecting}>
              <span>{redirecting ? 'Opening workspace…' : mode === 'local-demo' ? 'Continue as Demo Admin' : 'Sign in with Manus'}</span>
              <ArrowRight size={17} />
            </button>}

            {mode === 'local-demo' && <div className="signin-actions"><div className="credential-pill">Demo account: admin@example.test</div></div>}

            <div className="signin-note">
              <div className="signin-note-icon"><ShieldCheck size={17} /></div>
              <span>
                <strong>{mode === 'password' ? 'Account protected' : mode === 'local-demo' ? 'Local-only access' : 'Verified identity'}</strong>
                <small>{mode === 'password' ? 'Accounts are created by an administrator. New users cannot register themselves.' : mode === 'local-demo' ? 'Built for development and trusted localhost usage only.' : 'Your identity and project permissions are protected.'}</small>
              </span>
            </div>
          </div>

          <footer className="signin-footer">
            <span>CCTV SURVEY REPORT AUTOMATION</span>
            <span>ENGINEERING WORKFLOW · A4 OUTPUT</span>
          </footer>
        </section>

        <aside className="signin-aside">
          <div className="signin-aside-top">
            <span><i /> EVIDENCE WORKFLOW</span>
            <span className="signin-aside-count">01 <b>/</b> 03</span>
          </div>

          <div className="signin-diagram" aria-hidden="true">
            <div className="diagram-heading"><span>FROM FIELD DATA</span><span>TO REPORT</span></div>
            <div className="diagram-track"><span /></div>
            <div className="diagram-steps">
              <div className="diagram-step">
                <div className="diagram-icon"><GitBranch size={19} /></div>
                <strong>Pipe section</strong>
                <small>Filename parsed</small>
              </div>
              <div className="diagram-step diagram-step-active">
                <div className="diagram-icon"><Camera size={19} /></div>
                <strong>Video evidence</strong>
                <small>Frame linked</small>
              </div>
              <div className="diagram-step">
                <div className="diagram-icon"><FileText size={19} /></div>
                <strong>Report</strong>
                <small>Ready to review</small>
              </div>
            </div>
            <div className="diagram-foot">
              <span><CheckCircle2 size={14} /> Reviewer-controlled</span>
              <span>TRACEABLE BY SECTION</span>
            </div>
          </div>

          <div className="signin-aside-copy">
            <div className="eyebrow">ONE CLEAR EVIDENCE TRAIL</div>
            <h2>Every section.<br />Every frame.<br />In its place.</h2>
            <p>Filename-led pipe records, reviewer notes and genuine video stills stay together for report production.</p>
            <div className="signin-feature-tags">
              <span>Batch upload</span>
              <span>Manual review</span>
              <span>PDF output</span>
            </div>
          </div>

          <div className="signin-aside-footer"><span>PIPE SURVEY OPERATIONS</span><span>01 — EVIDENCE</span></div>
        </aside>
      </div>
    </main>
  );
}

function Layout({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const location = useLocation();
  const [compact, setCompact] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const title = navigation.find((item) => item.to === location.pathname)?.label
    || (location.pathname.startsWith('/report/') ? 'Project Report' : 'CCTV Survey');

  return (
    <div className={`app-shell ${compact ? 'nav-compact' : ''} ${mobileOpen ? 'mobile-nav-open' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark small-mark">CCTV</div>
          <div className="brand-text"><strong>SURVEY</strong><span>REPORT SYSTEM</span></div>
          <button className="mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={18} /></button>
        </div>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} title={compact ? label : undefined} onClick={() => setMobileOpen(false)}>
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="phase-card">
          <div className="phase-index">01</div>
          <div><strong>Survey & Reporting</strong><span>Import, review and generate</span></div>
        </div>
        <div className="sidebar-foot"><span>Environment</span><b><i /> Development</b></div>
      </aside>

      {mobileOpen && <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}

      <main className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button collapse-button" aria-label="Collapse navigation" title="Collapse navigation" onClick={() => setCompact(!compact)}><PanelLeftClose size={17} /></button>
            <button className="icon-button mobile-menu" aria-label="Open navigation" title="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></button>
            <span className="breadcrumb"><span>Workspace</span><b>/</b><strong>{title}</strong></span>
          </div>
          <div className="topbar-user">
            <div className="user-avatar">{session.user?.name?.slice(0, 1) || 'U'}</div>
            <div className="user-lines"><strong>{session.user?.name}</strong><span>{roleName[session.user?.role || ''] || session.user?.role}</span></div>
            <button className="icon-button logout-button" title="Sign out" aria-label="Sign out" onClick={onLogout}><LogOut size={16} /></button>
          </div>
        </header>
        <div className="content-wrap"><Outlet /></div>
        <footer className="app-footer"><span>CCTV SURVEY REPORT AUTOMATION</span><span>PROJECT DATA · HTML + PDF</span></footer>
      </main>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    api.session()
      .then(setSession)
      .catch(() => setSession({ authenticated: false }))
      .finally(() => setChecking(false));
  }, []);

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    window.location.assign('/');
  }

  async function passwordLogin(email: string, password: string) {
    await api.passwordLogin(email, password);
    setSession(await api.session());
  }

  if (checking) return <div className="boot-screen"><span className="loader" />Checking sign-in…</div>;
  if (!session?.authenticated) return <SignIn mode={session?.auth_mode} onPasswordLogin={passwordLogin} />;

  return (
    <Routes>
      <Route element={<Layout session={session} onLogout={() => void logout()} />}>
        <Route path="/" element={<Dashboard />} />
        {Object.entries(resourceForPath).map(([path, resource]) => (
          <Route key={path} path={path} element={<ResourcePage resource={resource} role={session.user?.role || 'VIEWER'} />} />
        ))}
        <Route path="/defects" element={<DefectsPage role={session.user?.role || 'VIEWER'} />} />
        <Route path="/report/:projectId" element={<ReportPreview canGenerate={['ADMIN', 'PROJECT_MANAGER'].includes(session.user?.role || '')} canUpload={['ADMIN', 'PROJECT_MANAGER', 'OPERATOR'].includes(session.user?.role || '')} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
