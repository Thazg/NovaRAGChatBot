import { useRef, useState, useEffect, useMemo } from 'react';
import { Settings as SettingsIcon, Monitor, User, Info, Upload, Keyboard, Globe, Shield, Trash2, Heart, Code, Cpu, Database, FileText, Loader2, ExternalLink, AlertTriangle, Activity } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { useChatStore } from '../../store/useChatStore';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '../ui/sheet';
import { ScrollArea } from '../ui/scroll-area';
import { Input } from '../ui/input';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '../../lib/utils';
import { api, type Document, type HealthStatus, type ReadinessStatus } from '../../services/api';

export const SettingsDrawer = () => {
  const { theme, setTheme, avatar, setAvatar, displayName, setDisplayName, settingsOpen, setSettingsOpen, customInstructions, setCustomInstructions, characterStyle, setCharacterStyle, nickname, setNickname, developerMode, setDeveloperMode, language, setLanguage } = useChatStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeSection, setActiveSection] = useState('general');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [summarizingFile, setSummarizingFile] = useState<string | null>(null);
  const [summaryResult, setSummaryResult] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [systemInfo, setSystemInfo] = useState<HealthStatus | null>(null);
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);
  const languages: Array<{ id: 'auto' | 'english' | 'vietnamese'; label: string }> = [
    { id: 'auto', label: 'Auto' },
    { id: 'english', label: 'English' },
    { id: 'vietnamese', label: 'Vietnamese' },
  ];

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const sections = useMemo(() => {
    const all = [
      { id: 'general', icon: Globe, label: 'General' },
      { id: 'appearance', icon: Monitor, label: 'Appearance' },
      { id: 'profile', icon: User, label: 'Profile' },
      { id: 'personalization', icon: Heart, label: 'Personalization' },
      { id: 'privacy', icon: Shield, label: 'Privacy & Data' },
      { id: 'shortcuts', icon: Keyboard, label: 'Shortcuts' },
      { id: 'storage', icon: Database, label: 'Storage' },
      ...(developerMode ? [{ id: 'system', icon: Cpu, label: 'System' }] : []),
      { id: 'developer', icon: Code, label: 'Developer' },
      { id: 'about', icon: Info, label: 'About' },
    ];
    return isMobile ? all.filter(s => s.id !== 'shortcuts') : all;
  }, [isMobile, developerMode]);

  useEffect(() => {
    if (settingsOpen && activeSection === 'storage') {
      setLoadingDocs(true);
      api.getDocuments()
        .then(setDocuments)
        .catch(() => setDocuments([]))
        .finally(() => setLoadingDocs(false));
    }
  }, [settingsOpen, activeSection]);

  useEffect(() => {
    if (!developerMode && activeSection === 'system') setActiveSection('general');
  }, [activeSection, developerMode]);

  useEffect(() => {
    if (settingsOpen && activeSection === 'system') {
      api.healthCheck().then(setSystemInfo).catch(() => setSystemInfo(null));
      api.readinessCheck().then(setReadiness).catch(() => setReadiness(null));
    }
  }, [activeSection, settingsOpen]);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > 2 * 1024 * 1024) {
        toast.error('Avatar must be smaller than 2 MB');
        return;
      }
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatar(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
      <SheetTrigger asChild>
        <Button aria-label="Open settings" variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground group">
          <SettingsIcon className="h-5 w-5 transition-transform group-hover:rotate-45 duration-300" />
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full sm:max-w-2xl p-0 border-l border-border/50 bg-background/95 backdrop-blur-xl">
        <SheetHeader className="px-4 md:px-6 pt-4 md:pt-6 pb-3 md:pb-4 border-b border-border/50 text-left">
          <SheetTitle className="text-lg md:text-xl font-medium tracking-tight">Settings</SheetTitle>
        </SheetHeader>

        <div className="flex h-[calc(100dvh-49px)] md:h-[calc(100dvh-64px)] overflow-hidden">
          {/* Sidebar Navigation */}
          <div className="w-52 border-r border-border/50 p-4 hidden sm:block shrink-0">
            <nav className="space-y-1">
              {sections.map((section) => {
                const Icon = section.icon;
                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
                      activeSection === section.id
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {section.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Content Area */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            {/* Mobile section tabs */}
            <div className="sm:hidden px-4 pt-2.5 pb-1 overflow-x-auto scrollbar-none shrink-0">
              <div className="flex gap-1 min-w-0 border-b border-border/20 pb-2">
                {sections.map((section) => {
                  const Icon = section.icon;
                  const isActive = activeSection === section.id;
                  return (
                    <button
                      key={section.id}
                      onClick={() => setActiveSection(section.id)}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap shrink-0 relative",
                        isActive
                          ? "text-primary"
                          : "text-muted-foreground/70 hover:text-foreground"
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {section.label}
                      {isActive && (
                        <span className="absolute bottom-[-9px] left-1/2 -translate-x-1/2 w-8 h-0.5 bg-primary rounded-full" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
            <ScrollArea className="flex-1 min-w-0 px-4 md:px-6 pt-1 md:pt-2 pb-8 md:pb-12">
            <div className="space-y-4 md:space-y-6 w-full">
              
              {/* General */}
              {activeSection === 'general' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Globe className="h-4 w-4" />
                    General
                  </div>
                  <div className="space-y-3 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="space-y-2">
                      <label className="text-xs font-medium text-muted-foreground">Response Language</label>
                      <div className="grid grid-cols-3 gap-2">
                        {languages.map((l) => (
                          <button
                            key={l.id}
                            onClick={() => setLanguage(l.id)}
                            className={`px-3 py-2 rounded-xl text-sm font-medium transition-all ${
                              language === l.id
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'bg-background border border-border/40 text-muted-foreground hover:border-border/70'
                            }`}
                          >
                            {l.label}
                          </button>
                        ))}
                      </div>
                      <p className="text-[10px] text-muted-foreground/50">Auto detects your question's language. Force English or Vietnamese to override.</p>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Appearance (with Animations merged) */}
              {activeSection === 'appearance' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Monitor className="h-4 w-4" />
                    Appearance
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {(['light', 'dark', 'system'] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setTheme(t)}
                        className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                          theme === t 
                            ? 'bg-primary text-primary-foreground shadow-sm' 
                            : 'bg-muted/50 hover:bg-muted text-muted-foreground'
                        }`}
                      >
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Profile */}
              {activeSection === 'profile' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <User className="h-4 w-4" />
                    Profile
                  </div>
                  <div className="space-y-4 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="flex items-center gap-4">
                      <div className="relative">
                        <div className="h-16 w-16 rounded-full overflow-hidden border-2 border-border/50 bg-muted flex items-center justify-center shrink-0">
                          {avatar ? <img src={avatar} alt="Avatar" className="h-full w-full object-cover" /> : <User className="h-8 w-8 text-muted-foreground" />}
                        </div>
                        <Button 
                          size="icon" 
                          className="absolute -bottom-2 -right-2 h-7 w-7 rounded-full shadow-sm"
                          onClick={() => fileInputRef.current?.click()}
                        >
                          <Upload className="h-3 w-3" />
                        </Button>
                        <input 
                          type="file" 
                          ref={fileInputRef} 
                          className="hidden" 
                          accept="image/*" 
                          onChange={handleAvatarChange}
                        />
                      </div>
                      <div className="flex-1 space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">Display Name</label>
                        <Input 
                          value={displayName} 
                          onChange={(e) => setDisplayName(e.target.value)}
                          className="h-9 rounded-lg"
                        />
                      </div>
                    </div>
                    {avatar && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full rounded-xl text-xs gap-1.5 text-destructive"
                        onClick={() => { setAvatar(null); toast.success('Avatar removed'); }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove Avatar
                      </Button>
                    )}
                  </div>
                </motion.div>
              )}



              {/* Personalization */}
              {activeSection === 'personalization' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Heart className="h-4 w-4" />
                    Personalization
                  </div>
                  <div className="space-y-4 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="space-y-2">
                      <label className="text-xs font-medium text-muted-foreground">Character Style</label>
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { id: 'warm', label: 'Warm', desc: 'Caring, affectionate tone' },
                          { id: 'enthusiastic', label: 'Enthusiastic', desc: 'Energetic, excited' },
                          { id: 'professional', label: 'Professional', desc: 'Formal, polished' },
                          { id: 'concise', label: 'Concise', desc: 'Direct, to the point' },
                          { id: 'friendly', label: 'Friendly', desc: 'Casual, approachable' },
                          { id: 'custom', label: 'Custom', desc: 'Use your instructions' },
                        ].map((c) => (
                          <button
                            key={c.id}
                            onClick={() => setCharacterStyle(c.id)}
                            className={cn(
                              'px-3 py-2.5 rounded-xl text-left transition-all',
                              characterStyle === c.id
                                ? 'bg-primary/10 border border-primary/30 text-primary'
                                : 'bg-background border border-border/40 text-muted-foreground hover:border-border/70'
                            )}
                          >
                            <p className="text-[13px] font-medium">{c.label}</p>
                            <p className="text-[10px] text-muted-foreground/60 mt-0.5">{c.desc}</p>
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="pt-3 border-t border-border/30 space-y-3">
                      <label className="text-xs font-medium text-muted-foreground">Nickname</label>
                      <Input
                        value={nickname}
                        onChange={(e) => setNickname(e.target.value)}
                        placeholder="What should I call you?"
                        className="h-9 rounded-lg"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-xs font-medium text-muted-foreground">Custom Instruction</label>
                      <textarea
                        value={customInstructions}
                        onChange={(e) => {
                          setCustomInstructions(e.target.value);
                          if (e.target.value && characterStyle !== 'custom') {
                            setCharacterStyle('custom');
                          }
                        }}
                        placeholder="Additional behaviour, style, tone preferences"
                        className="w-full min-h-[100px] rounded-xl bg-background border border-border/50 px-3 py-2.5 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-primary/40"
                      />
                      <p className="text-[10px] text-muted-foreground/50">These instructions will be sent with every message.</p>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Privacy & Data */}
              {activeSection === 'privacy' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Shield className="h-4 w-4" />
                    Privacy & Data
                  </div>
                  <div className="space-y-3 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <Button variant="outline" className="w-full rounded-xl justify-start text-sm h-9 gap-2" onClick={() => {
                      useChatStore.getState().clearAllConversations();
                      toast.success('All conversations cleared');
                    }}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                      <span>Clear All Conversations</span>
                    </Button>
                    <div className="pt-2 border-t border-border/30 space-y-2">
                      <AnimatePresence>
                        {!confirmDelete ? (
                          <motion.div key="btn" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            <Button
                              variant="outline"
                              className="w-full rounded-xl justify-start text-sm h-9 gap-2 border-destructive/30 hover:border-destructive/60 text-destructive"
                              onClick={() => setConfirmDelete(true)}
                            >
                              <AlertTriangle className="h-4 w-4" />
                              <span>Delete Account</span>
                            </Button>
                          </motion.div>
                        ) : (
                          <motion.div
                            key="confirm"
                            initial={{ opacity: 0, y: -5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -5 }}
                            className="space-y-2 p-3 rounded-xl bg-destructive/10 border border-destructive/20"
                          >
                            <p className="text-xs font-medium text-destructive">This will permanently delete your account and all data.</p>
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                variant="destructive"
                                className="flex-1 h-8 text-xs"
                                disabled={deletingAccount}
                                onClick={async () => {
                                  setDeletingAccount(true);
                                  try {
                                    await api.deleteAccount();
                                    toast.success('Account deleted');
                                    useChatStore.getState().logout();
                                  } catch (err: unknown) {
                                    toast.error(err instanceof Error ? err.message : 'Failed to delete account');
                                  } finally {
                                    setDeletingAccount(false);
                                    setConfirmDelete(false);
                                  }
                                }}
                              >
                                {deletingAccount ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                                {deletingAccount ? 'Deleting...' : 'Confirm Delete'}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="flex-1 h-8 text-xs"
                                onClick={() => setConfirmDelete(false)}
                              >
                                Cancel
                              </Button>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Shortcuts */}
              {activeSection === 'shortcuts' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Keyboard className="h-4 w-4" />
                    Keyboard Shortcuts
                  </div>
                  <div className="space-y-2 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">New Chat</span>
                      <kbd className="px-2 py-1 rounded bg-background border border-border/50 text-xs">Ctrl + N</kbd>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Global Search</span>
                      <kbd className="px-2 py-1 rounded bg-background border border-border/50 text-xs">Ctrl + K</kbd>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Focus Input</span>
                      <kbd className="px-2 py-1 rounded bg-background border border-border/50 text-xs">Ctrl + /</kbd>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Stop Generation</span>
                      <kbd className="px-2 py-1 rounded bg-background border border-border/50 text-xs">Esc</kbd>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Storage */}
              {activeSection === 'storage' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Database className="h-4 w-4" />
                    Storage
                  </div>
                  <div className="space-y-3 p-4 bg-muted/20 rounded-xl border border-border/50">
                    {loadingDocs ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : (
                      <>
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">Uploaded Files</span>
                            <span className="font-mono text-xs text-foreground">{documents.length}</span>
                          </div>
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">Total Size</span>
                            <span className="font-mono text-xs text-foreground">
                              {documents.reduce((s, d) => s + d.size, 0) > 1048576
                                ? `${(documents.reduce((s, d) => s + d.size, 0) / 1048576).toFixed(1)} MB`
                                : `${(documents.reduce((s, d) => s + d.size, 0) / 1024).toFixed(0)} KB`}
                            </span>
                          </div>
                        </div>
                        {documents.length > 0 && (
                          <div className="pt-2 space-y-1.5 max-h-40 overflow-y-auto">
                            {documents.map((doc) => (
                              <div key={doc.id} className="flex items-center gap-2 text-xs text-muted-foreground/70">
                                <FileText className="h-3 w-3 shrink-0" />
                                <button
                                  onClick={async () => {
                                    setSummarizingFile(doc.name);
                                    setSummaryResult(null);
                                    try {
                                      const res = await api.summarizeDocument(doc.name);
                                      setSummaryResult(res.summary);
                                    } catch {
                                      toast.error('Failed to summarize');
                                    } finally {
                                      setSummarizingFile(null);
                                    }
                                  }}
                                  className="truncate flex-1 text-left hover:text-primary transition-colors"
                                >
                                  {doc.name}
                                </button>
                                <span className="shrink-0">{doc.size > 1024 ? `${(doc.size / 1024).toFixed(0)} KB` : `${doc.size} B`}</span>
                                {summarizingFile === doc.name ? (
                                  <Loader2 className="h-3 w-3 animate-spin shrink-0" />
                                ) : (
                                  <button
                                    onClick={async () => {
                                      setSummarizingFile(doc.name);
                                      setSummaryResult(null);
                                      try {
                                        const res = await api.summarizeDocument(doc.name);
                                        setSummaryResult(res.summary);
                                      } catch {
                                        toast.error('Failed to summarize');
                                      } finally {
                                        setSummarizingFile(null);
                                      }
                                    }}
                                    className="text-[10px] text-primary/70 hover:text-primary shrink-0 ml-1"
                                  >
                                    Summarize
                                  </button>
                                )}
                                {doc.source_url && (
                                  <a
                                    href={doc.source_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 ml-1 text-[10px] text-blue-400/60 hover:text-blue-400 transition-colors"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <ExternalLink className="h-2.5 w-2.5 inline" />
                                  </a>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {summaryResult && (
                          <div className="pt-2 border-t border-border/30">
                            <p className="text-[11px] font-medium text-muted-foreground mb-1">Summary:</p>
                            <p className="text-xs text-foreground/80 leading-relaxed">{summaryResult}</p>
                            <button
                              onClick={() => setSummaryResult(null)}
                              className="text-[10px] text-muted-foreground/50 hover:text-muted-foreground mt-1"
                            >
                              Dismiss
                            </button>
                          </div>
                        )}
                        <div className="pt-3 border-t border-border/30 space-y-2">
                          <Button variant="outline" className="w-full rounded-xl justify-start text-sm h-9 gap-2" onClick={async () => {
                            try {
                              const result = await api.clearAllDocuments();
                              setDocuments([]);
                              toast.success(`Deleted ${result.deleted} file(s)`);
                            } catch {
                              toast.error('Failed to clear files');
                            }
                          }}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                            <span>Delete All Files</span>
                          </Button>
                        </div>
                      </>
                    )}
                    <div className="pt-2 border-t border-border/30">
                      <p className="text-[10px] text-muted-foreground/50">Uploaded documents are stored on the server.</p>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Developer Mode */}
              {activeSection === 'developer' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Code className="h-4 w-4" />
                    Developer Mode
                  </div>
                  <div className="space-y-3 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-sm font-medium text-foreground">Enable Developer Mode</label>
                        <p className="text-[11px] text-muted-foreground/60 mt-0.5">Show backend, system, and debug tools</p>
                      </div>
                      <input
                        type="checkbox"
                        className="accent-primary h-4 w-4 rounded-sm"
                        checked={developerMode}
                        onChange={(e) => setDeveloperMode(e.target.checked)}
                      />
                    </div>
                    {developerMode && (
                      <div className="pt-3 border-t border-border/30 space-y-2">
                        <p className="text-xs text-muted-foreground/70">Additional sections are now visible in the sidebar navigation.</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
                          <Cpu className="h-3 w-3" />
                          <span>System — Model info, diagnostics</span>
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}



              {/* System (developer only) */}
              {activeSection === 'system' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Cpu className="h-4 w-4" />
                    System
                  </div>
                  <div className="space-y-3 p-4 bg-muted/20 rounded-xl border border-border/50">
                    <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background/70 p-3">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "grid h-7 w-7 place-items-center rounded-lg",
                          readiness?.ready ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500",
                        )}>
                          <Activity className="h-3.5 w-3.5" />
                        </span>
                        <div>
                          <p className="text-xs font-semibold text-foreground">AI readiness</p>
                          <p className="text-[10px] text-muted-foreground">{readiness?.message || 'Checking provider…'}</p>
                        </div>
                      </div>
                      <span className={cn(
                        "rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-wide",
                        readiness?.ready ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500",
                      )}>
                        {readiness?.ready ? 'Ready' : 'Checking'}
                      </span>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">AI Provider</label>
                      <div className="text-sm font-mono p-2 bg-background rounded-md border text-foreground">
                        {systemInfo?.llm_provider === 'groq'
                          ? `Groq (${systemInfo.groq_model || 'configured model'})`
                          : systemInfo?.llm_provider === 'ollama'
                            ? `Ollama (${systemInfo.model || 'local model'})`
                            : 'Checking…'}
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-lg border border-border/40 bg-background/55 p-2">
                        <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Version</p>
                        <p className="mt-1 font-mono text-xs text-foreground">v{systemInfo?.version || '—'}</p>
                      </div>
                      <div className="rounded-lg border border-border/40 bg-background/55 p-2">
                        <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Environment</p>
                        <p className="mt-1 truncate font-mono text-xs capitalize text-foreground">{systemInfo?.environment || '—'}</p>
                      </div>
                      <div className="rounded-lg border border-border/40 bg-background/55 p-2">
                        <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Uptime</p>
                        <p className="mt-1 font-mono text-xs text-foreground">{systemInfo?.uptime_seconds != null ? `${Math.floor(systemInfo.uptime_seconds)}s` : '—'}</p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-foreground">Retrieval Top-K</label>
                      <span className="text-xs font-mono text-muted-foreground">5</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-foreground">Context Window</label>
                      <span className="text-xs font-mono text-muted-foreground">4096</span>
                    </div>
                    <div className="pt-2 border-t border-border/30 space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">RAG Pipeline</label>
                      <div className="flex gap-1.5 flex-wrap">
                        {(systemInfo?.retrieval === 'hybrid'
                          ? ['BM25', 'Semantic vectors', 'RRF fusion', 'Context builder', 'Prompt assembly']
                          : ['BM25 lexical search', 'Query expansion', 'Context builder', 'Prompt assembly']
                        ).map((step) => (
                          <span key={step} className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-[10px] font-medium">{step}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* About */}
              {activeSection === 'about' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                    <Info className="h-4 w-4" />
                    About
                  </div>
                  <div className="p-4 bg-muted/20 rounded-xl border border-border/50 text-center space-y-1">
                    <h4 className="font-bold text-sm tracking-widest text-foreground">NOVA AI AGENT</h4>
                    <p className="text-xs text-muted-foreground">Version 2.0.0</p>
                    <p className="text-[10px] text-muted-foreground/60 mt-2">Premium Enterprise RAG Platform</p>
                    <div className="pt-4 border-t border-border/30 mt-4">
                      <p className="text-xs text-muted-foreground">Built with React, TypeScript, and Framer Motion</p>
                    </div>
                  </div>
                </motion.div>
              )}
              
            </div>
          </ScrollArea>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};
