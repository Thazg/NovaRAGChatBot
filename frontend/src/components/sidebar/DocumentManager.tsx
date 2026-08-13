import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Database, ExternalLink, File, FolderOpen, HardDrive, MessageSquareText, Plus, RefreshCw, Search, Trash2, Upload } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { toast } from 'sonner';
import { api } from '../../services/api';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../store/useChatStore';

interface Document {
  id: string;
  name: string;
  type: 'pdf' | 'txt' | 'docx';
  size: string;
  uploadedAt: number;
  status: 'indexed' | 'processing' | 'failed';
  indexed: boolean;
  chunks: number;
  source_url?: string;
}

const FILE_TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  pdf: { bg: 'bg-red-500/15', text: 'text-red-400' },
  txt: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  docx: { bg: 'bg-violet-500/15', text: 'text-violet-400' },
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

export const DocumentManager = ({
  onUploadComplete,
  onSelectDocument,
}: {
  onUploadComplete?: () => void;
  onSelectDocument?: () => void;
}) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);
  const selectedDocument = useChatStore((state) => state.selectedDocument);
  const setSelectedDocument = useChatStore((state) => state.setSelectedDocument);
  const setSidebarActiveTab = useChatStore((state) => state.setSidebarActiveTab);

  const loadDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const docs = await api.getDocuments();
      const formattedDocs: Document[] = docs.map((doc) => ({
        id: doc.id,
        name: doc.name,
        type: doc.name.endsWith('.pdf')
          ? 'pdf'
          : doc.name.endsWith('.txt') || doc.name.endsWith('.md') || doc.name.endsWith('.py') || doc.name.endsWith('.ipynb')
          ? 'txt'
          : 'docx',
        size: formatFileSize(doc.size),
        uploadedAt: Date.now(),
        status: doc.indexed ? 'indexed' : 'processing',
        indexed: doc.indexed ?? false,
        chunks: doc.chunks ?? 0,
        source_url: doc.source_url
      }));
      setDocuments(formattedDocs);
      const currentSelection = useChatStore.getState().selectedDocument;
      if (currentSelection && !formattedDocs.some((document) => document.id === currentSelection.id)) {
        setSelectedDocument(null);
      }
    } catch (error) {
      console.error('Failed to load documents:', error);
      toast.error('Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, [setSelectedDocument]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const uploadResult = await api.uploadDocument(file);
      const job = uploadResult.job_id
        ? await api.waitForIndexJob(uploadResult.job_id)
        : null;
      await loadDocuments();

      if (uploadResult.indexed || job?.result?.indexed) {
        toast.success(`${uploadResult.filename} indexed (${job?.result?.chunks ?? uploadResult.chunks ?? 0} chunks)`);
        onUploadComplete?.();
      } else {
        toast.error(uploadResult.message || 'Upload succeeded but indexing failed');
      }
    } catch (error) {
      console.error('Failed to upload document:', error);
      toast.error('Failed to upload document');
    } finally {
      setUploading(false);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteDocument(id);
      setDocuments(prev => prev.filter(d => d.id !== id));
      if (selectedDocument?.id === id) setSelectedDocument(null);
      toast.success('Document deleted');
    } catch (error) {
      console.error('Failed to delete document:', error);
      toast.error('Failed to delete document');
    }
  };

  const handleReindex = async () => {
    try {
      toast.info('Re-indexing documents...');
      const result = await api.reindexDocuments();
      if (result.job_id) await api.waitForIndexJob(result.job_id);
      if (!['success', 'queued'].includes(result.status)) throw new Error(result.message || 'Re-indexing failed');
      toast.success('Documents re-indexed');
      await loadDocuments();
    } catch (error) {
      console.error('Failed to re-index:', error);
      toast.error('Re-indexing failed');
    }
  };

  const filteredDocs = documents.filter(doc =>
    doc.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalChunks = documents.reduce((acc, doc) => acc + (doc.chunks || 0), 0);

  const handleAskDocument = (document: Document) => {
    setSelectedDocument({ id: document.id, name: document.name });
    setSidebarActiveTab('conversations');
    onSelectDocument?.();
    window.setTimeout(() => window.document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Message input"]')?.focus(), 0);
    toast.success(`Questions will use ${document.name}`);
  };

  return (
    <div
      ref={dropZoneRef}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className="flex flex-col h-full relative"
    >
      {/* Drag overlay */}
      <AnimatePresence>
        {isDragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 rounded-2xl border-2 border-dashed border-primary/50 bg-primary/10 backdrop-blur-sm flex items-center justify-center"
          >
            <div className="text-center">
              <Upload className="h-8 w-8 text-primary mx-auto mb-2" />
              <p className="text-sm font-semibold text-primary">Drop file here</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header with stats */}
      <div className="pb-3 shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-primary/20 to-violet-500/15 flex items-center justify-center">
              <Database className="h-3.5 w-3.5 text-primary" />
            </div>
            <div>
              <p className="text-[12px] font-semibold text-foreground leading-tight">Knowledge Base</p>
              <p className="text-xs text-muted-foreground/70">{documents.length} docs · {totalChunks} chunks</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 rounded-[10px] text-muted-foreground hover:text-foreground"
              onClick={handleReindex}
              title="Re-index all"
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
            <Button
              size="icon"
              className="h-9 w-9 rounded-[10px] bg-primary text-white shadow-sm hover:bg-primary/90"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}>
                  <RefreshCw className="h-3 w-3" />
                </motion.div>
              ) : (
                <Plus className="h-3 w-3" />
              )}
            </Button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileInput}
            accept=".pdf,.txt,.docx,.md,.markdown,.py,.ipynb"
          />
        </div>

        {/* Search */}
        {documents.length > 3 && (
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground/40" />
            <Input
              placeholder="Filter documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 rounded-[10px] border-border/40 bg-muted/25 pl-8 text-[13px] placeholder:text-muted-foreground/60 focus-visible:ring-1 focus-visible:ring-primary/30"
            />
          </div>
        )}
      </div>

      {/* Document list — scrollable */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-1.5 -mx-1 px-1">
        <AnimatePresence mode="popLayout">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              >
                <RefreshCw className="h-6 w-6 text-muted-foreground/30 mb-3" />
              </motion.div>
              <p className="text-[12px] text-muted-foreground/50">Loading documents...</p>
            </div>
          ) : filteredDocs.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center py-10 text-center"
            >
              <div className="w-14 h-14 rounded-2xl bg-muted/30 flex items-center justify-center mb-3 border border-border/20">
                <FolderOpen className="h-6 w-6 text-muted-foreground/30" />
              </div>
              <p className="text-[13px] text-muted-foreground/50 font-medium">No documents</p>
              <p className="text-[11px] text-muted-foreground/35 mt-1 max-w-[180px]">Upload PDF, TXT, or DOCX files to build your knowledge base</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4 rounded-lg h-8 text-[12px] border-border/30 hover:bg-primary/5 hover:text-primary hover:border-primary/30"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-3 w-3 mr-1.5" />
                Upload file
              </Button>
            </motion.div>
          ) : (
            filteredDocs.map((doc, idx) => {
              const typeStyle = FILE_TYPE_COLORS[doc.type] || FILE_TYPE_COLORS.txt;
              return (
                <motion.div
                  key={doc.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }}
                  transition={{ duration: 0.2, delay: idx * 0.03 }}
                  layout
                  className={cn(
                    "group rounded-[14px] border p-3 transition-colors",
                    selectedDocument?.id === doc.id
                      ? "border-primary/35 bg-primary/10"
                      : "border-border/35 bg-muted/20 hover:border-border/60 hover:bg-muted/35",
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    {/* File icon */}
                    <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center shrink-0", typeStyle.bg)}>
                      <File className={cn("h-4 w-4", typeStyle.text)} />
                    </div>

                    {/* File info */}
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-[13px] font-medium leading-tight text-foreground" title={doc.name}>{doc.name}</p>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className="text-xs font-medium uppercase text-muted-foreground/70">{doc.type}</span>
                        <span className="text-xs text-muted-foreground/45">·</span>
                        <span className="text-xs text-muted-foreground/70">{doc.size}</span>
                        <span className="text-xs text-muted-foreground/45">·</span>
                        <span className="text-xs text-muted-foreground/70">{doc.chunks} chunks</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant={selectedDocument?.id === doc.id ? 'secondary' : 'ghost'}
                        size="sm"
                        className="h-9 rounded-[10px] px-2.5 text-xs"
                        onClick={() => handleAskDocument(doc)}
                        disabled={!doc.indexed}
                        aria-label={`Ask questions about ${doc.name}`}
                      >
                        <MessageSquareText className="h-4 w-4" />
                        <span className="hidden min-[300px]:inline">Ask</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9 rounded-[10px] text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => handleDelete(doc.id)}
                        aria-label={`Delete ${doc.name}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  {/* Status bar */}
                  <div className="flex items-center gap-1.5 mt-2 pt-1.5 border-t border-border/15">
                    {doc.status === 'indexed' ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    ) : doc.status === 'processing' ? (
                      <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
                        <RefreshCw className="h-3 w-3 text-primary" />
                      </motion.div>
                    ) : (
                      <AlertCircle className="h-3 w-3 text-red-400" />
                    )}
                    <span className={cn(
                      "text-xs font-medium",
                      doc.status === 'indexed' ? "text-emerald-400/70" : doc.status === 'processing' ? "text-primary/70" : "text-red-400/70"
                    )}>
                      {doc.status === 'indexed' ? 'Indexed' : doc.status === 'processing' ? 'Processing...' : 'Failed'}
                    </span>
                    {doc.source_url && (
                      <a
                        href={doc.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-auto flex items-center gap-1 text-[10px] text-blue-400/70 hover:text-blue-400 transition-colors"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <ExternalLink className="h-2.5 w-2.5" />
                        Source
                      </a>
                    )}
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>

      {/* Upload progress bar */}
      <AnimatePresence>
        {uploading && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 shrink-0"
          >
            <div className="rounded-lg bg-primary/10 border border-primary/20 p-2.5 flex items-center gap-2.5">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
              >
                <HardDrive className="h-3.5 w-3.5 text-primary" />
              </motion.div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] font-medium text-primary">Uploading & indexing...</p>
                <div className="w-full h-1 bg-primary/20 rounded-full mt-1 overflow-hidden">
                  <motion.div
                    className="h-full bg-primary rounded-full"
                    animate={{ x: ['-100%', '100%'] }}
                    transition={{ repeat: Infinity, duration: 1.5, ease: "easeInOut" }}
                    style={{ width: '40%' }}
                  />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
