import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, Loader2, AlertCircle, RefreshCw, LogOut } from 'lucide-react';
import { api, type Document } from '../../services/api';
import heroImage from '../../assets/hero.png';
import { useChatStore } from '../../store/useChatStore';

export const UploadGate = ({ onContinue }: { onContinue: () => void }) => {
  const [, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logout = useChatStore((s) => s.logout);

  const loadDocs = useCallback(async () => {
    setLoadError('');
    setLoading(true);
    try {
      const docs = await api.getDocuments();
      setDocuments(docs);
      if (docs.length > 0) {
        onContinue();
      }
    } catch {
      setDocuments([]);
      setLoadError('Nova could not load your workspace. Check the connection and try again.');
    } finally {
      setLoading(false);
    }
  }, [onContinue]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError('');
    setUploading(true);
    try {
      const result = await api.uploadDocument(file);
      if (result.job_id) await api.waitForIndexJob(result.job_id);
      await loadDocs();
    } catch (uploadError) {
      setUploadError(uploadError instanceof Error ? uploadError.message : 'Upload failed. Please try again.');
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="nova-shell nova-upload-shell fixed inset-0 z-50 h-[100dvh] w-screen overflow-y-auto bg-background"
      >
        <div className="nova-grid" />
        <div className="nova-viewport-center">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28 }}
            className="nova-panel nova-upload-panel relative flex w-full max-w-lg flex-col items-center overflow-hidden rounded-[20px] px-6 py-7 text-center sm:px-9 sm:py-9"
          >
            <div className="absolute inset-x-16 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent" />
            {loading && !uploading && !loadError ? (
              <div className="grid min-h-[280px] place-items-center">
                <div>
                  <div className="mx-auto grid h-12 w-12 place-items-center rounded-[14px] bg-primary/10 text-primary">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                  <h1 className="mt-5 text-2xl font-semibold tracking-tight">Opening your workspace</h1>
                  <p className="mt-2 text-sm text-muted-foreground">Checking your indexed documents…</p>
                </div>
              </div>
            ) : (
              <>
                <div className="flex h-20 w-24 items-center justify-center">
                  <img src={heroImage} alt="Nova knowledge layers" className="h-full w-full object-contain" />
                </div>
                <h1 className="mt-4 text-2xl font-semibold tracking-tight">
                  {loadError ? 'Workspace unavailable' : 'Add your first document'}
                </h1>
                <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
                  {loadError
                    ? 'Nova could not connect to your document workspace.'
                    : 'Upload a document to create a private, searchable knowledge base.'}
                </p>

                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  className="hidden"
                  accept=".pdf,.md,.markdown,.rst,.txt,.py,.docx,.ipynb"
                />

                {loadError ? (
                  <div className="mt-6 w-full max-w-sm rounded-[14px] border border-destructive/25 bg-destructive/5 p-4 text-left">
                    <div className="flex items-start gap-3 text-sm text-destructive">
                      <AlertCircle className="mt-0.5 h-[18px] w-[18px] shrink-0" />
                      <p className="flex-1 leading-5">{loadError}</p>
                    </div>
                    <button onClick={loadDocs} className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-[10px] border border-border bg-background px-4 text-sm font-semibold text-foreground transition-colors hover:bg-muted">
                      <RefreshCw className="h-4 w-4" /> Try again
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    aria-label="Upload a document"
                    className="nova-upload-dropzone mt-6 flex w-full max-w-sm items-center gap-3 rounded-[14px] border border-dashed border-primary/40 bg-primary/10 p-4 text-left transition-colors hover:bg-primary/15 disabled:cursor-wait disabled:opacity-70"
                  >
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-primary text-primary-foreground">
                      {uploading ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : <Upload className="h-[18px] w-[18px]" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-foreground">{uploading ? 'Uploading and indexing…' : 'Choose a document'}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">PDF, DOCX, Markdown, TXT, Python or notebook</p>
                    </div>
                  </button>
                )}

                {uploadError && (
                  <div className="mt-4 flex w-full max-w-sm items-start gap-2.5 rounded-[12px] border border-destructive/20 bg-destructive/5 p-3 text-left text-xs text-destructive">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="leading-5">{uploadError}</span>
                  </div>
                )}
              </>
            )}

            <div className="mt-6 w-full border-t border-border/45 pt-4">
              <button onClick={logout} className="inline-flex h-10 items-center gap-2 rounded-[10px] px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
                <LogOut className="h-4 w-4" /> Sign out
              </button>
            </div>
          </motion.div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
