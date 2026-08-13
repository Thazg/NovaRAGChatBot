import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Check,
  ChevronRight,
  Copy,
  Database,
  Download,
  ExternalLink,
  FileText,
  HardDrive,
  Info,
  KeyRound,
  Keyboard,
  Languages,
  Laptop,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  MessageSquare,
  MonitorSmartphone,
  Moon,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  UserRound,
  WandSparkles,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '../ui/sheet';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../store/useChatStore';
import { api, type Document, type HealthStatus, type ReadinessStatus } from '../../services/api';

type SectionId = 'general' | 'profile' | 'personalization' | 'knowledge' | 'privacy' | 'system' | 'about';

const sections: Array<{
  id: SectionId;
  label: string;
  description: string;
  icon: typeof SlidersHorizontal;
}> = [
  { id: 'general', label: 'General', description: 'Language, theme & shortcuts', icon: SlidersHorizontal },
  { id: 'profile', label: 'Profile', description: 'Identity & account security', icon: UserRound },
  { id: 'personalization', label: 'Personalization', description: 'Tone and response behavior', icon: Sparkles },
  { id: 'knowledge', label: 'Knowledge base', description: 'Documents, summaries & index', icon: Database },
  { id: 'privacy', label: 'Privacy & data', description: 'Export, retention & account', icon: ShieldCheck },
  { id: 'system', label: 'System', description: 'AI readiness & diagnostics', icon: Activity },
  { id: 'about', label: 'About Nova', description: 'Product and privacy details', icon: Info },
];

const toneOptions = [
  { id: 'professional', label: 'Professional', description: 'Clear, structured and polished' },
  { id: 'concise', label: 'Concise', description: 'Short answers with minimal filler' },
  { id: 'friendly', label: 'Friendly', description: 'Natural and approachable' },
  { id: 'warm', label: 'Warm', description: 'Supportive and considerate' },
  { id: 'enthusiastic', label: 'Enthusiastic', description: 'Energetic and motivating' },
  { id: 'custom', label: 'Custom', description: 'Follow your instructions below' },
] as const;

const languageOptions = [
  { id: 'auto', label: 'Auto detect', detail: 'Match each question' },
  { id: 'english', label: 'English', detail: 'Always answer in English' },
  { id: 'vietnamese', label: 'Tiếng Việt', detail: 'Luôn trả lời tiếng Việt' },
] as const;

const themeOptions = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Laptop },
] as const;

const formatBytes = (bytes: number) => {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const formatUptime = (seconds?: number) => {
  if (seconds == null) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
};

const SettingsCard = ({ children, className }: { children: ReactNode; className?: string }) => (
  <div className={cn(
    'nova-settings-card min-w-0 max-w-full rounded-[14px] border border-border/55 bg-card/90 shadow-sm',
    className,
  )}>
    {children}
  </div>
);

const SectionHeading = ({
  icon: Icon,
  eyebrow,
  title,
  description,
}: {
  icon: typeof SlidersHorizontal;
  eyebrow: string;
  title: string;
  description: string;
}) => (
  <div className="flex items-start gap-3.5">
    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
      <Icon className="h-[18px] w-[18px]" />
    </div>
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary/75">{eyebrow}</p>
      <h2 className="mt-1 text-xl font-semibold tracking-tight text-foreground">{title}</h2>
      <p className="mt-1 max-w-xl text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  </div>
);

const CardHeader = ({ title, description, action }: { title: string; description?: string; action?: ReactNode }) => (
  <div className="flex items-start justify-between gap-4 border-b border-border/40 px-4 py-4 sm:px-5">
    <div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {description && <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>}
    </div>
    {action}
  </div>
);

const Metric = ({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Activity }) => (
  <div className="rounded-[12px] border border-border/45 bg-background/55 p-3.5">
    <div className="flex items-center gap-2 text-muted-foreground">
      <Icon className="h-3.5 w-3.5" />
      <span className="text-[10px] font-bold uppercase tracking-[0.12em]">{label}</span>
    </div>
    <p className="mt-2 truncate font-mono text-sm font-semibold text-foreground">{value}</p>
  </div>
);

const Toggle = ({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onClick={() => onChange(!checked)}
    className={cn(
      'relative h-6 w-11 shrink-0 rounded-full border transition-colors',
      checked ? 'border-primary bg-primary' : 'border-border bg-muted',
    )}
  >
    <span className={cn(
      'absolute top-0.5 grid h-5 w-5 place-items-center rounded-full bg-white shadow-sm transition-transform',
      checked ? 'translate-x-[19px]' : 'translate-x-0.5',
    )}>
      {checked && <Check className="h-3 w-3 text-primary" />}
    </span>
  </button>
);

export const SettingsDrawer = () => {
  const {
    theme,
    setTheme,
    avatar,
    setAvatar,
    displayName,
    setDisplayName,
    settingsOpen,
    setSettingsOpen,
    customInstructions,
    setCustomInstructions,
    characterStyle,
    setCharacterStyle,
    nickname,
    setNickname,
    developerMode,
    setDeveloperMode,
    language,
    setLanguage,
    username,
    savePreferences,
    syncPreferences,
    clearAllConversations,
    logout,
    setSelectedDocument,
    setSidebarActiveTab,
  } = useChatStore();

  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [activeSection, setActiveSection] = useState<SectionId>('general');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docsError, setDocsError] = useState('');
  const [summary, setSummary] = useState<{ filename: string; content: string } | null>(null);
  const [summarizingFile, setSummarizingFile] = useState<string | null>(null);
  const [deletingDocument, setDeletingDocument] = useState<string | null>(null);
  const [confirmClearDocuments, setConfirmClearDocuments] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [preferenceSaveState, setPreferenceSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const lastSavedPreferencesRef = useRef('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [confirmClearChats, setConfirmClearChats] = useState(false);
  const [clearingChats, setClearingChats] = useState(false);
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [systemInfo, setSystemInfo] = useState<HealthStatus | null>(null);
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);
  const [loadingSystem, setLoadingSystem] = useState(false);

  const totalSize = useMemo(() => documents.reduce((sum, document) => sum + document.size, 0), [documents]);
  const totalChunks = useMemo(() => documents.reduce((sum, document) => sum + (document.chunks || 0), 0), [documents]);
  const preferenceSnapshot = useMemo(() => JSON.stringify({
    displayName,
    theme,
    language,
    characterStyle,
    nickname,
    customInstructions,
  }), [characterStyle, customInstructions, displayName, language, nickname, theme]);

  const loadDocuments = async () => {
    setLoadingDocs(true);
    setDocsError('');
    try {
      setDocuments(await api.getDocuments());
    } catch (error) {
      setDocsError(error instanceof Error ? error.message : 'Could not load documents');
    } finally {
      setLoadingDocs(false);
    }
  };

  const loadSystem = async (refresh = false) => {
    setLoadingSystem(true);
    try {
      const [health, ready] = await Promise.all([api.healthCheck(), api.readinessCheck(refresh)]);
      setSystemInfo(health);
      setReadiness(ready);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not refresh diagnostics');
    } finally {
      setLoadingSystem(false);
    }
  };

  useEffect(() => {
    if (!settingsOpen) {
      setPreferencesReady(false);
      setPreferenceSaveState('idle');
      return;
    }
    let cancelled = false;
    setPreferencesReady(false);
    void syncPreferences()
      .catch(() => undefined)
      .finally(() => {
        if (cancelled) return;
        const state = useChatStore.getState();
        lastSavedPreferencesRef.current = JSON.stringify({
          displayName: state.displayName,
          theme: state.theme,
          language: state.language,
          characterStyle: state.characterStyle,
          nickname: state.nickname,
          customInstructions: state.customInstructions,
        });
        setPreferencesReady(true);
        setPreferenceSaveState('saved');
      });
    return () => { cancelled = true; };
  }, [settingsOpen, syncPreferences]);

  useEffect(() => {
    if (!settingsOpen || !preferencesReady || preferenceSnapshot === lastSavedPreferencesRef.current) return;
    setPreferenceSaveState('saving');
    const timer = window.setTimeout(async () => {
      try {
        await savePreferences();
        lastSavedPreferencesRef.current = preferenceSnapshot;
        setPreferenceSaveState('saved');
      } catch (error) {
        setPreferenceSaveState('error');
        toast.error(error instanceof Error ? error.message : 'Could not save preferences');
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [preferenceSnapshot, preferencesReady, savePreferences, settingsOpen]);

  useEffect(() => {
    if (settingsOpen && activeSection === 'knowledge') void loadDocuments();
    if (settingsOpen && (activeSection === 'system' || activeSection === 'about')) void loadSystem();
  }, [activeSection, settingsOpen]);

  const handleSettingsOpenChange = (open: boolean) => {
    if (!open && preferencesReady && preferenceSnapshot !== lastSavedPreferencesRef.current) {
      void savePreferences().catch(() => undefined);
    }
    setSettingsOpen(open);
  };

  const handleAvatarChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Choose an image file');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Avatar must be smaller than 2 MB');
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => setAvatar(String(reader.result));
    reader.readAsDataURL(file);
    event.target.value = '';
  };

  const handlePasswordChange = async () => {
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }
    setChangingPassword(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      toast.success('Password updated and other sessions revoked');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not update password');
    } finally {
      setChangingPassword(false);
    }
  };

  const handleSummarize = async (document: Document) => {
    setSummarizingFile(document.id);
    try {
      const result = await api.summarizeDocument(document.name);
      setSummary({ filename: document.name, content: result.summary });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not summarize document');
    } finally {
      setSummarizingFile(null);
    }
  };

  const handleAskDocument = (document: Document) => {
    setSelectedDocument({ id: document.id, name: document.name });
    setSidebarActiveTab('conversations');
    setSettingsOpen(false);
    window.setTimeout(() => window.document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Message input"]')?.focus(), 0);
    toast.success(`Questions will use ${document.name}`);
  };

  const handleDeleteDocument = async (document: Document) => {
    setDeletingDocument(document.id);
    try {
      await api.deleteDocument(document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      toast.success(`${document.name} deleted`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete document');
    } finally {
      setDeletingDocument(null);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      const result = await api.reindexDocuments();
      if (result.job_id) await api.waitForIndexJob(result.job_id);
      await loadDocuments();
      toast.success('Knowledge index rebuilt');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not rebuild index');
    } finally {
      setReindexing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const payload = await api.exportAccountData();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `nova-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success('Account export downloaded');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not export account data');
    } finally {
      setExporting(false);
    }
  };

  const diagnostics = JSON.stringify({ health: systemInfo, readiness }, null, 2);

  const renderGeneral = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={SlidersHorizontal}
        eyebrow="Workspace preferences"
        title="Make Nova feel like yours"
        description="Language and theme sync with your Nova account. Keyboard shortcuts work anywhere in the workspace."
      />

      <SettingsCard>
        <CardHeader title="Response language" description="Choose how Nova answers, independent of document language." />
        <div className="grid gap-2 p-4 sm:grid-cols-3 sm:p-5">
          {languageOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setLanguage(option.id)}
              className={cn(
                'relative rounded-xl border p-3.5 text-left transition-all',
                language === option.id
                  ? 'border-primary/45 bg-primary/10 shadow-[0_12px_28px_-22px_rgba(var(--primary-rgb),0.8)]'
                  : 'border-border/50 bg-background/45 hover:border-primary/25 hover:bg-muted/40',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-foreground">{option.label}</span>
                {language === option.id && <Check className="h-4 w-4 text-primary" />}
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">{option.detail}</p>
            </button>
          ))}
        </div>
      </SettingsCard>

      <SettingsCard>
        <CardHeader title="Appearance" description="The system option follows your operating system preference." />
        <div className="grid grid-cols-3 gap-2 p-4 sm:p-5">
          {themeOptions.map((option) => {
            const Icon = option.icon;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setTheme(option.id)}
                className={cn(
                  'flex flex-col items-center gap-2 rounded-xl border px-3 py-4 text-xs font-semibold transition-all',
                  theme === option.id
                    ? 'border-primary/45 bg-primary/10 text-primary'
                    : 'border-border/50 bg-background/45 text-muted-foreground hover:border-primary/25 hover:text-foreground',
                )}
              >
                <Icon className="h-5 w-5" />
                {option.label}
              </button>
            );
          })}
        </div>
      </SettingsCard>

      <SettingsCard>
        <CardHeader title="Keyboard shortcuts" description="These shortcuts are active and handled by the workspace." />
        <div className="divide-y divide-border/35 px-4 sm:px-5">
          {[
            ['New chat', 'Ctrl / ⌘ + N'],
            ['Global search', 'Ctrl / ⌘ + K'],
            ['Focus message box', 'Ctrl / ⌘ + /'],
            ['Stop generation or close search', 'Esc'],
          ].map(([label, shortcut]) => (
            <div key={label} className="flex items-center justify-between gap-3 py-3.5">
              <div className="flex items-center gap-2.5 text-sm text-foreground/85">
                <Keyboard className="h-4 w-4 text-muted-foreground" />
                {label}
              </div>
              <kbd className="rounded-lg border border-border/60 bg-muted/55 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm">{shortcut}</kbd>
            </div>
          ))}
        </div>
      </SettingsCard>

      <p className="text-right text-xs text-muted-foreground">Changes save automatically to your Nova account.</p>
    </div>
  );

  const renderProfile = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={UserRound}
        eyebrow="Identity & security"
        title="Your Nova profile"
        description="Manage how you appear in the workspace and keep your account protected."
      />

      <SettingsCard className="overflow-hidden">
        <div className="relative border-b border-border/40 bg-gradient-to-br from-primary/14 via-violet-500/6 to-transparent p-5 sm:p-6">
          <div className="pointer-events-none absolute -right-10 -top-16 h-40 w-40 rounded-full bg-primary/15 blur-3xl" />
          <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
            <div className="relative w-fit">
              <div className="grid h-20 w-20 place-items-center overflow-hidden rounded-3xl border border-primary/25 bg-background/70 shadow-xl shadow-primary/10">
                {avatar ? <img src={avatar} alt="Profile avatar" className="h-full w-full object-cover" /> : <UserRound className="h-8 w-8 text-primary" />}
              </div>
              <button
                type="button"
                onClick={() => avatarInputRef.current?.click()}
                className="absolute -bottom-2 -right-2 grid h-8 w-8 place-items-center rounded-xl border border-border bg-card text-primary shadow-lg transition-transform hover:scale-105"
                aria-label="Upload profile avatar"
              >
                <Upload className="h-3.5 w-3.5" />
              </button>
              <input ref={avatarInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-semibold text-foreground">{displayName || username || 'Nova user'}</p>
              <p className="mt-1 truncate text-sm text-muted-foreground">@{username || 'user'}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-border/60 bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground">Private workspace</span>
                <span className="rounded-full border border-border/50 bg-background/55 px-2.5 py-1 text-xs text-muted-foreground">Avatar stays on this device</span>
              </div>
            </div>
          </div>
        </div>
        <div className="space-y-4 p-4 sm:p-5">
          <div className="space-y-2">
            <label htmlFor="display-name" className="text-xs font-semibold text-foreground">Display name</label>
            <Input
              id="display-name"
              value={displayName}
              maxLength={80}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="How should your name appear?"
              className="nova-settings-field h-11 rounded-xl bg-background/65"
            />
            <p className="text-xs text-muted-foreground">Saved automatically and synced across devices.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {avatar && (
              <Button variant="outline" onClick={() => setAvatar(null)} className="rounded-xl text-destructive">
                <Trash2 /> Remove avatar
              </Button>
            )}
          </div>
        </div>
      </SettingsCard>

      <SettingsCard>
        <CardHeader title="Change password" description="Updating your password revokes other refresh sessions while keeping this device signed in." action={<LockKeyhole className="h-4 w-4 text-muted-foreground" />} />
        <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
          <div className="space-y-2 sm:col-span-2">
            <label htmlFor="current-password" className="text-xs font-semibold">Current password</label>
            <Input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} className="nova-settings-field h-11 rounded-xl bg-background/65" />
          </div>
          <div className="space-y-2">
            <label htmlFor="new-password" className="text-xs font-semibold">New password</label>
            <Input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className="nova-settings-field h-11 rounded-xl bg-background/65" />
          </div>
          <div className="space-y-2">
            <label htmlFor="confirm-password" className="text-xs font-semibold">Confirm new password</label>
            <Input id="confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="nova-settings-field h-11 rounded-xl bg-background/65" />
          </div>
          <div className="flex items-center justify-between gap-3 sm:col-span-2">
            <p className="text-[11px] text-muted-foreground">Use at least 8 characters.</p>
            <Button onClick={handlePasswordChange} disabled={changingPassword || !currentPassword || !newPassword || !confirmPassword} className="rounded-xl">
              {changingPassword ? <Loader2 className="animate-spin" /> : <KeyRound />}
              Update password
            </Button>
          </div>
        </div>
      </SettingsCard>
    </div>
  );

  const renderPersonalization = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={Sparkles}
        eyebrow="Response behavior"
        title="Shape every answer"
        description="Your tone and instructions are sent with chat requests and stored with your account."
      />

      <SettingsCard>
        <CardHeader title="Response style" description="Choose a strong default. Custom instructions can refine it further." action={<WandSparkles className="h-4 w-4 text-primary" />} />
        <div className="grid gap-2 p-4 sm:grid-cols-2 sm:p-5">
          {toneOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setCharacterStyle(option.id)}
              className={cn(
                'flex items-start gap-3 rounded-xl border p-3.5 text-left transition-all',
                characterStyle === option.id
                  ? 'border-primary/45 bg-primary/10'
                  : 'border-border/50 bg-background/45 hover:border-primary/25 hover:bg-muted/40',
              )}
            >
              <span className={cn(
                'mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border',
                characterStyle === option.id ? 'border-primary bg-primary text-primary-foreground' : 'border-border',
              )}>
                {characterStyle === option.id && <Check className="h-3 w-3" />}
              </span>
              <span>
                <span className="block text-sm font-semibold text-foreground">{option.label}</span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">{option.description}</span>
              </span>
            </button>
          ))}
        </div>
      </SettingsCard>

      <SettingsCard>
        <CardHeader title="Personal context" description="Keep it useful and avoid adding secrets or sensitive credentials." />
        <div className="space-y-4 p-4 sm:p-5">
          <div className="space-y-2">
            <label htmlFor="nickname" className="text-xs font-semibold">What should Nova call you?</label>
            <Input id="nickname" value={nickname} maxLength={80} onChange={(event) => setNickname(event.target.value)} placeholder="Optional nickname" className="nova-settings-field h-11 rounded-xl bg-background/65" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="custom-instructions" className="text-xs font-semibold">Custom instructions</label>
              <span className="font-mono text-[10px] text-muted-foreground">{customInstructions.length}/4000</span>
            </div>
            <textarea
              id="custom-instructions"
              value={customInstructions}
              maxLength={4000}
              onChange={(event) => {
                setCustomInstructions(event.target.value);
                if (event.target.value && characterStyle !== 'custom') setCharacterStyle('custom');
              }}
              placeholder="Example: Prefer structured answers, cite document names, and explain technical terms briefly."
              className="nova-settings-field min-h-36 w-full resize-y rounded-xl border border-input bg-background/65 px-3.5 py-3 text-sm leading-6 text-foreground outline-none transition-shadow placeholder:text-muted-foreground/55 focus:ring-2 focus:ring-ring/60"
            />
          </div>
          <p className="text-right text-xs text-muted-foreground">Tone and instructions save automatically.</p>
        </div>
      </SettingsCard>
    </div>
  );

  const renderKnowledge = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={Database}
        eyebrow="Grounded knowledge"
        title="Manage your indexed documents"
        description="Review storage, generate a real document summary, remove files, or rebuild the retrieval index."
      />

      <div className="grid grid-cols-3 gap-2.5">
        <Metric label="Documents" value={String(documents.length)} icon={FileText} />
        <Metric label="Chunks" value={String(totalChunks)} icon={BookOpen} />
        <Metric label="Storage" value={formatBytes(totalSize)} icon={HardDrive} />
      </div>

      <SettingsCard>
        <CardHeader
          title="Knowledge base"
          description="Summaries use extracted document chunks; re-indexing restores the corpus from object storage first."
          action={(
            <div className="flex gap-1.5">
              <Button variant="outline" size="icon" className="h-8 w-8 rounded-lg" onClick={() => void loadDocuments()} disabled={loadingDocs} aria-label="Refresh documents">
                <RefreshCw className={cn('h-3.5 w-3.5', loadingDocs && 'animate-spin')} />
              </Button>
              <Button variant="outline" size="sm" className="h-8 rounded-lg text-xs" onClick={handleReindex} disabled={reindexing || !documents.length}>
                {reindexing ? <Loader2 className="animate-spin" /> : <Database />}
                Re-index
              </Button>
            </div>
          )}
        />

        {loadingDocs ? (
          <div className="grid min-h-44 place-items-center p-6 text-muted-foreground">
            <div className="text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin" /><p className="mt-2 text-xs">Loading your documents…</p></div>
          </div>
        ) : docsError ? (
          <div className="m-4 rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive sm:m-5">{docsError}</div>
        ) : !documents.length ? (
          <div className="grid min-h-44 place-items-center p-6 text-center">
            <div><Database className="mx-auto h-7 w-7 text-muted-foreground/35" /><p className="mt-3 text-sm font-semibold">No indexed documents</p><p className="mt-1 text-xs text-muted-foreground">Upload a document from the knowledge base panel to get started.</p></div>
          </div>
        ) : (
          <div className="divide-y divide-border/35 px-4 sm:px-5">
            {documents.map((document) => (
              <div key={document.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-border/45 bg-muted/45 text-primary">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-foreground" title={document.name}>{document.name}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted-foreground">
                    <span>{formatBytes(document.size)}</span><span>•</span><span>{document.chunks || 0} chunks</span><span>•</span>
                    <span className={document.indexed ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}>{document.indexed ? 'Indexed' : 'Processing'}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 sm:justify-end">
                  <Button variant="outline" size="sm" className="h-9 rounded-[10px] text-xs" onClick={() => handleAskDocument(document)} disabled={!document.indexed}>
                    <MessageSquareText className="h-4 w-4" />
                    Ask
                  </Button>
                  <Button variant="outline" size="sm" className="h-8 rounded-lg text-xs" onClick={() => void handleSummarize(document)} disabled={summarizingFile === document.id || !document.indexed}>
                    {summarizingFile === document.id ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Summarize
                  </Button>
                  {document.source_url && (
                    <Button asChild variant="ghost" size="icon" className="h-8 w-8 rounded-lg">
                      <a href={document.source_url} target="_blank" rel="noopener noreferrer" aria-label={`Open source for ${document.name}`}><ExternalLink /></a>
                    </Button>
                  )}
                  <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => void handleDeleteDocument(document)} disabled={deletingDocument === document.id} aria-label={`Delete ${document.name}`}>
                    {deletingDocument === document.id ? <Loader2 className="animate-spin" /> : <Trash2 />}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {documents.length > 0 && (
          <div className="border-t border-border/40 p-4 sm:p-5">
            {!confirmClearDocuments ? (
              <Button variant="outline" onClick={() => setConfirmClearDocuments(true)} className="rounded-xl border-destructive/25 text-destructive hover:bg-destructive/5 hover:text-destructive">
                <Trash2 /> Delete all documents
              </Button>
            ) : (
              <div className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-destructive">Delete all uploaded files and their retrieval index?</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setConfirmClearDocuments(false)} className="rounded-lg">Cancel</Button>
                  <Button variant="destructive" size="sm" className="rounded-lg" onClick={async () => {
                    try {
                      const result = await api.clearAllDocuments();
                      setDocuments([]);
                      setConfirmClearDocuments(false);
                      toast.success(`Deleted ${result.deleted} document${result.deleted === 1 ? '' : 's'}`);
                    } catch (error) {
                      toast.error(error instanceof Error ? error.message : 'Could not delete documents');
                    }
                  }}>Delete all</Button>
                </div>
              </div>
            )}
          </div>
        )}
      </SettingsCard>

      <AnimatePresence>
        {summary && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            <SettingsCard className="overflow-hidden border-primary/20">
              <CardHeader
                title={`Summary · ${summary.filename}`}
                description="Generated from the indexed chunks stored for this document."
                action={<Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={() => setSummary(null)} aria-label="Close summary"><X /></Button>}
              />
              <div className="prose prose-sm max-h-80 max-w-none overflow-y-auto p-4 text-sm dark:prose-invert sm:p-5">
                <ReactMarkdown>{summary.content}</ReactMarkdown>
              </div>
            </SettingsCard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  const renderPrivacy = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={ShieldCheck}
        eyebrow="Privacy controls"
        title="Your data, under your control"
        description="Export a portable copy, clear chat history, or permanently remove the account and its stored data."
      />

      <SettingsCard>
        <CardHeader title="Download your data" description="Creates a JSON export with account metadata, preferences, conversations and document metadata." action={<Download className="h-4 w-4 text-primary" />} />
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Download className="h-4 w-4" /></div>
            <div><p className="text-sm font-semibold">Portable account export</p><p className="mt-0.5 text-[11px] text-muted-foreground">Document binaries are not included.</p></div>
          </div>
          <Button variant="outline" onClick={handleExport} disabled={exporting} className="rounded-xl">
            {exporting ? <Loader2 className="animate-spin" /> : <Download />}
            Export JSON
          </Button>
        </div>
      </SettingsCard>

      <SettingsCard>
        <CardHeader title="Conversation history" description="This removes all conversations from the server and this device. Documents remain untouched." action={<MessageSquare className="h-4 w-4 text-muted-foreground" />} />
        <div className="p-4 sm:p-5">
          {!confirmClearChats ? (
            <Button variant="outline" onClick={() => setConfirmClearChats(true)} className="rounded-xl"><Trash2 /> Clear all conversations</Button>
          ) : (
            <div className="flex flex-col gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-amber-600 dark:text-amber-400">This cannot be undone. Clear every conversation?</p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setConfirmClearChats(false)} className="rounded-lg">Cancel</Button>
                <Button variant="destructive" size="sm" disabled={clearingChats} className="rounded-lg" onClick={async () => {
                  setClearingChats(true);
                  try {
                    await clearAllConversations();
                    setConfirmClearChats(false);
                    toast.success('All conversations cleared');
                  } catch (error) {
                    toast.error(error instanceof Error ? error.message : 'Could not clear conversations');
                  } finally {
                    setClearingChats(false);
                  }
                }}>{clearingChats ? <Loader2 className="animate-spin" /> : <Trash2 />}Clear history</Button>
              </div>
            </div>
          )}
        </div>
      </SettingsCard>

      <SettingsCard className="border-destructive/25">
        <CardHeader title="Danger zone" description="Deleting your account removes conversations, documents, indexes, preferences and active sessions." action={<AlertTriangle className="h-4 w-4 text-destructive" />} />
        <div className="p-4 sm:p-5">
          {!confirmDeleteAccount ? (
            <Button variant="outline" onClick={() => setConfirmDeleteAccount(true)} className="rounded-xl border-destructive/30 text-destructive hover:bg-destructive/5 hover:text-destructive"><Trash2 /> Delete account</Button>
          ) : (
            <div className="space-y-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4">
              <div>
                <p className="text-sm font-semibold text-destructive">Permanently delete this account</p>
                <p className="mt-1 text-xs text-muted-foreground">Type <span className="font-mono font-semibold text-foreground">{username}</span> to confirm.</p>
              </div>
              <Input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} placeholder={username || 'username'} className="nova-settings-field h-10 rounded-xl bg-background/70" />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" className="rounded-lg" onClick={() => { setConfirmDeleteAccount(false); setDeleteConfirmation(''); }}>Cancel</Button>
                <Button variant="destructive" size="sm" className="rounded-lg" disabled={deletingAccount || deleteConfirmation !== username} onClick={async () => {
                  setDeletingAccount(true);
                  try {
                    await api.deleteAccount();
                    await logout();
                    toast.success('Account deleted');
                  } catch (error) {
                    toast.error(error instanceof Error ? error.message : 'Could not delete account');
                  } finally {
                    setDeletingAccount(false);
                  }
                }}>{deletingAccount ? <Loader2 className="animate-spin" /> : <Trash2 />}Delete permanently</Button>
              </div>
            </div>
          )}
        </div>
      </SettingsCard>
    </div>
  );

  const renderSystem = () => {
    const model = systemInfo?.llm_provider === 'groq' ? systemInfo.groq_model : systemInfo?.model;
    const infrastructure = Object.entries(systemInfo?.infrastructure || {});
    return (
      <div className="space-y-5">
        <SectionHeading
          icon={Activity}
          eyebrow="Live diagnostics"
          title="Nova system status"
          description="Every value below comes from the running backend and AI readiness probe."
        />

        <SettingsCard className="overflow-hidden">
          <div className={cn(
            'flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-center sm:justify-between',
            readiness?.ready ? 'border-emerald-500/15 bg-emerald-500/5' : 'border-amber-500/15 bg-amber-500/5',
          )}>
            <div className="flex items-center gap-3">
              <span className={cn('relative grid h-11 w-11 place-items-center rounded-2xl', readiness?.ready ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-amber-500/10 text-amber-700 dark:text-amber-400')}>
                <Activity className="h-5 w-5" />
                <span className={cn('absolute right-0 top-0 h-2.5 w-2.5 rounded-full border-2 border-card', readiness?.ready ? 'bg-emerald-500' : 'bg-amber-500')} />
              </span>
              <div>
                <p className="text-sm font-semibold">{readiness?.ready ? 'All AI services ready' : loadingSystem ? 'Checking Nova services…' : 'Service attention required'}</p>
                <p className="mt-1 text-xs text-muted-foreground">{readiness?.message || 'Waiting for live readiness data.'}</p>
              </div>
            </div>
            <Button variant="outline" size="sm" className="rounded-xl" onClick={() => void loadSystem(true)} disabled={loadingSystem}>
              <RefreshCw className={cn(loadingSystem && 'animate-spin')} /> Run live check
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-2.5 p-4 sm:grid-cols-4 sm:p-5">
            <Metric label="Provider" value={systemInfo?.llm_provider || '—'} icon={Activity} />
            <Metric label="Model" value={model || '—'} icon={WandSparkles} />
            <Metric label="Retrieval" value={systemInfo?.retrieval || '—'} icon={Database} />
            <Metric label="Uptime" value={formatUptime(systemInfo?.uptime_seconds)} icon={MonitorSmartphone} />
          </div>
        </SettingsCard>

        <SettingsCard>
          <CardHeader title="RAG configuration" description="Read-only production configuration reported by the API." />
          <div className="grid grid-cols-2 gap-2.5 p-4 sm:grid-cols-4 sm:p-5">
            <Metric label="Top K" value={String(systemInfo?.rag_config?.top_k ?? '—')} icon={BookOpen} />
            <Metric label="Context" value={systemInfo?.rag_config?.context_window ? `${systemInfo.rag_config.context_window} tokens` : '—'} icon={MessageSquare} />
            <Metric label="Max output" value={systemInfo?.rag_config?.max_tokens ? `${systemInfo.rag_config.max_tokens} tokens` : '—'} icon={WandSparkles} />
            <Metric label="Upload limit" value={systemInfo?.rag_config?.max_upload_bytes ? formatBytes(systemInfo.rag_config.max_upload_bytes) : '—'} icon={Upload} />
          </div>
        </SettingsCard>

        <SettingsCard>
          <CardHeader title="Infrastructure" description="Persistence and worker modes reported by the active deployment." />
          <div className="grid gap-2 p-4 sm:grid-cols-2 sm:p-5">
            {infrastructure.length ? infrastructure.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-3 rounded-xl border border-border/45 bg-background/55 px-3.5 py-3">
                <span className="text-xs capitalize text-muted-foreground">{key.replaceAll('_', ' ')}</span>
                <span className="truncate font-mono text-[11px] font-semibold text-foreground">{String(value)}</span>
              </div>
            )) : <p className="text-xs text-muted-foreground">Diagnostics have not loaded yet.</p>}
          </div>
        </SettingsCard>

        <SettingsCard>
          <div className="flex items-center justify-between gap-4 p-4 sm:p-5">
            <div>
              <p className="text-sm font-semibold">Developer diagnostics</p>
              <p className="mt-1 text-xs text-muted-foreground">Expose raw, non-secret health payloads for troubleshooting.</p>
            </div>
            <Toggle checked={developerMode} onChange={setDeveloperMode} label="Developer diagnostics" />
          </div>
          {developerMode && (
            <div className="border-t border-border/40 p-4 sm:p-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Diagnostic payload</span>
                <Button variant="ghost" size="sm" className="h-8 rounded-lg text-xs" onClick={async () => {
                  await navigator.clipboard.writeText(diagnostics);
                  toast.success('Diagnostics copied');
                }}><Copy /> Copy</Button>
              </div>
              <pre className="max-h-64 overflow-auto rounded-xl border border-border/45 bg-background/75 p-3 text-[10px] leading-5 text-muted-foreground">{diagnostics}</pre>
            </div>
          )}
        </SettingsCard>
      </div>
    );
  };

  const renderAbout = () => (
    <div className="space-y-5">
      <SectionHeading
        icon={Info}
        eyebrow="Nova knowledge OS"
        title="Private knowledge, grounded answers"
        description="Nova turns your uploaded documents into traceable context for private, citation-aware conversations."
      />

      <SettingsCard className="overflow-hidden">
        <div className="relative bg-gradient-to-br from-primary/16 via-violet-500/7 to-sky-500/5 p-6 text-center sm:p-8">
          <div className="pointer-events-none absolute left-1/2 top-0 h-36 w-72 -translate-x-1/2 rounded-full bg-primary/15 blur-3xl" />
          <div className="relative mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-primary/25 bg-background/65 text-primary shadow-xl shadow-primary/10"><Sparkles className="h-6 w-6" /></div>
          <h3 className="relative mt-4 text-xl font-bold tracking-tight">Nova AI Knowledge OS</h3>
          <p className="relative mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
            A private, document-grounded workspace for searchable and citation-aware conversations.
          </p>
          <p className="relative mt-2 text-xs font-medium text-muted-foreground">Version {systemInfo?.version || '2.1.0'} · {systemInfo?.environment || 'workspace'}</p>
        </div>
        <div className="grid gap-2 p-4 sm:grid-cols-3 sm:p-5">
          {[
            { icon: LockKeyhole, title: 'Account isolated', description: 'Documents, indexes and conversations are scoped to your account.' },
            { icon: Database, title: 'Grounded retrieval', description: 'Answers are built from indexed document chunks, not hidden placeholders.' },
            { icon: ShieldCheck, title: 'Data controls', description: 'Export, clear or permanently delete your account data.' },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="rounded-xl border border-border/45 bg-background/50 p-3.5">
                <Icon className="h-4 w-4 text-primary" />
                <p className="mt-2 text-xs font-semibold">{item.title}</p>
                <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{item.description}</p>
              </div>
            );
          })}
        </div>
        <div className="flex flex-col gap-2 border-t border-border/40 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <p className="text-xs text-muted-foreground">React · TypeScript · FastAPI · Hybrid retrieval</p>
          <Button asChild variant="outline" size="sm" className="rounded-xl">
            <a href="https://github.com/Thazg/NovaRAGChatBot" target="_blank" rel="noopener noreferrer">GitHub <ExternalLink /></a>
          </Button>
        </div>
      </SettingsCard>
    </div>
  );

  const content = {
    general: renderGeneral,
    profile: renderProfile,
    personalization: renderPersonalization,
    knowledge: renderKnowledge,
    privacy: renderPrivacy,
    system: renderSystem,
    about: renderAbout,
  }[activeSection];

  const activeMeta = sections.find((section) => section.id === activeSection) || sections[0];
  const ActiveSectionIcon = activeMeta.icon;

  return (
    <Sheet open={settingsOpen} onOpenChange={handleSettingsOpenChange}>
      <SheetContent className="nova-settings-shell w-full overflow-hidden border-l border-border/50 bg-background p-0 sm:max-w-[900px]">
        <SheetHeader className="relative border-b border-border/45 px-5 py-4 text-left sm:px-6 sm:py-5">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/80 to-transparent" />
          <div className="flex items-center gap-3 pr-8">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-primary/20 bg-primary/10 text-primary"><SettingsIcon className="h-4 w-4" /></div>
            <div>
              <SheetTitle className="text-lg tracking-tight">Settings</SheetTitle>
              <SheetDescription className="mt-0.5 flex items-center gap-1.5 text-xs">
                {preferenceSaveState === 'saving' && <Loader2 className="h-3 w-3 animate-spin" />}
                {preferenceSaveState === 'saved' && <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />}
                <span>
                  {preferenceSaveState === 'saving'
                    ? 'Saving changes…'
                    : preferenceSaveState === 'error'
                      ? 'Some preferences could not be saved'
                      : 'Preferences save automatically'}
                </span>
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <div className="flex h-[calc(100dvh-73px)] min-h-0 flex-col sm:flex-row">
          <aside className="nova-settings-sidebar min-w-0 shrink-0 overflow-hidden border-b border-border/45 bg-muted/15 sm:w-60 sm:border-b-0 sm:border-r">
            <div className="flex min-w-0 gap-1.5 overflow-x-auto p-3 sm:block sm:space-y-1 sm:overflow-visible sm:p-4">
              {sections.map((section) => {
                const Icon = section.icon;
                const active = section.id === activeSection;
                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => setActiveSection(section.id)}
                    className={cn(
                      'group box-border flex min-w-[10rem] max-w-full items-center gap-2 overflow-hidden rounded-[10px] px-3 py-2.5 text-left transition-colors sm:w-full sm:min-w-0 sm:gap-3',
                      active
                        ? 'bg-primary/10 text-primary shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.16)]'
                        : 'text-muted-foreground hover:bg-muted/55 hover:text-foreground',
                    )}
                  >
                    <span className={cn('grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors', active ? 'bg-primary text-primary-foreground shadow-sm' : 'bg-background/60 group-hover:bg-background')}>
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold">{section.label}</span>
                      <span className="mt-0.5 hidden truncate text-xs text-muted-foreground sm:block">{section.description}</span>
                    </span>
                    <ChevronRight className={cn('hidden h-3.5 w-3.5 sm:block', active ? 'opacity-70' : 'opacity-0 group-hover:opacity-40')} />
                  </button>
                );
              })}
            </div>
            <div className="hidden border-t border-border/40 p-4 sm:block">
              <div className="rounded-xl border border-border/40 bg-background/45 p-3">
                <div className="flex items-center gap-2">
                  <Languages className="h-3.5 w-3.5 text-primary" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Account sync</span>
                </div>
                <p className="mt-2 text-[11px] leading-5 text-muted-foreground">Profile and response preferences follow your Nova account.</p>
              </div>
            </div>
          </aside>

          <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl p-4 pb-12 sm:p-6 sm:pb-16 lg:p-8">
              <div className="mb-4 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground sm:hidden">
                <ActiveSectionIcon className="h-3.5 w-3.5" /> {activeMeta.label}
              </div>
              <AnimatePresence mode="wait">
                <motion.div key={activeSection} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.2 }}>
                  {content()}
                </motion.div>
              </AnimatePresence>
            </div>
          </main>
        </div>
      </SheetContent>
    </Sheet>
  );
};
