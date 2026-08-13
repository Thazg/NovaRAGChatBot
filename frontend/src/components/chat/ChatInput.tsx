import React, { useRef, useEffect, useState } from 'react';
import { FileText, Loader2, Mic, Paperclip, Send, Square, X } from 'lucide-react';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../store/useChatStore';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import { api } from '../../services/api';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
}

interface SpeechRecognitionResultEventLike {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export const ChatInput = ({ onSend, onStop }: ChatInputProps) => {
  const [input, setInput] = React.useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const isLoading = useChatStore((state) => state.isLoading);
  const setSidebarActiveTab = useChatStore((state) => state.setSidebarActiveTab);
  const language = useChatStore((state) => state.language);
  const selectedDocument = useChatStore((state) => state.selectedDocument);
  const setSelectedDocument = useChatStore((state) => state.setSelectedDocument);
  const isBusy = isStreaming || isLoading;
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef<{
    start: () => void;
    stop: () => void;
  } | null>(null);

  const prevStreamingRef = useRef(isStreaming);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const newH = Math.min(textareaRef.current.scrollHeight, 200);
      textareaRef.current.style.height = `${newH}px`;
    }
  }, [input]);

  // Auto-focus input when streaming completes
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      textareaRef.current?.focus();
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await api.uploadDocument(file);
      const job = result.job_id ? await api.waitForIndexJob(result.job_id) : null;
      if (result.indexed || job?.result?.indexed) {
        toast.success(`Indexed "${result.filename}" (${job?.result?.chunks ?? result.chunks ?? 0} chunks)`);
        setSidebarActiveTab('documents');
      } else {
        toast.error(result.message || 'Failed to index file');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed');
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const toggleRecording = () => {
    const speechWindow = window as SpeechWindow;
    const SpeechRecognitionAPI = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      toast.error('Speech recognition not supported in this browser');
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = language === 'english'
      ? 'en-US'
      : language === 'vietnamese'
        ? 'vi-VN'
        : (navigator.language || 'en-US');
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setIsRecording(true);
    recognition.onend = () => setIsRecording(false);
    recognition.onerror = () => {
      setIsRecording(false);
      toast.error('Microphone access denied or error occurred');
    };
    recognition.onresult = (event: SpeechRecognitionResultEventLike) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => (prev ? prev + ' ' + transcript : transcript));
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleSubmit = () => {
    if (!input.trim() || isBusy) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const charCount = input.length;
  const showCharCount = charCount > 200;

  return (
    <div className="relative mx-auto flex w-full flex-col gap-2">
      <motion.div
        initial={{ y: 8, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.22 }}
        className={cn(
          "relative flex w-full flex-col rounded-[14px] border bg-card/95 shadow-sm transition-[border-color,box-shadow] duration-200",
          isBusy
            ? "border-primary/35"
            : "border-border/60 hover:border-border focus-within:border-primary/45 focus-within:shadow-[0_0_0_3px_hsl(var(--primary)/0.08)]"
        )}
      >
        {selectedDocument && (
          <div className="flex items-center gap-2 border-b border-border/45 px-3 py-2">
            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] bg-primary/10 text-primary">
              <FileText className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1 text-left">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Document scope</p>
              <p className="truncate text-xs font-medium text-foreground" title={selectedDocument.name}>{selectedDocument.name}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9 rounded-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => setSelectedDocument(null)}
              aria-label={`Clear document scope for ${selectedDocument.name}`}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2 px-2.5 py-2.5">
          {/* Attach button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".pdf,.md,.markdown,.rst,.txt,.py,.docx,.ipynb"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="mb-0.5 h-9 w-9 shrink-0 rounded-[10px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            disabled={isBusy}
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach file"
          >
            <Paperclip className="h-4 w-4" />
          </Button>

          {/* Textarea */}
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedDocument ? `Ask about ${selectedDocument.name}...` : 'Ask Nova anything...'}
            className="min-h-9 max-h-[200px] w-full resize-none border-0 bg-transparent px-0 py-1.5 text-[15px] font-normal leading-relaxed shadow-none placeholder:text-muted-foreground/60 focus-visible:ring-0"
            disabled={isBusy}
            rows={1}
            maxLength={4000}
            aria-label="Message input"
          />

          {/* Right controls */}
          <div className="mb-0.5 flex shrink-0 items-center gap-1">
            {/* A fixed mic slot prevents the send button from jumping sideways. */}
            <div className="relative h-9 w-9">
              <AnimatePresence initial={false}>
                {!input.trim() && !isBusy && (
                  <motion.div
                    className="absolute inset-0"
                    initial={{ opacity: 0, scale: 0.78, x: 5, filter: 'blur(4px)' }}
                    animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
                    exit={{ opacity: 0, scale: 0.82, x: 5, filter: 'blur(4px)' }}
                    transition={{ type: "spring", stiffness: 360, damping: 28, mass: 0.65 }}
                  >
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={toggleRecording}
                    className={cn(
                      "flex h-9 w-9 rounded-[10px] transition-colors",
                      isRecording
                        ? "text-red-500 bg-red-500/10 hover:bg-red-500/20"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                    )}
                    aria-label="Voice input"
                  >
                    {isRecording ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                  </Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Send and stop morph in place without changing control width. */}
            <div className="relative h-9 w-9">
              <AnimatePresence initial={false} mode="sync">
                {isBusy ? (
                  <motion.div
                    key="stop"
                    className="absolute inset-0"
                    initial={{ scale: 0.72, opacity: 0, rotate: -35, filter: 'blur(3px)' }}
                    animate={{ scale: 1, opacity: 1, rotate: 0, filter: 'blur(0px)' }}
                    exit={{ scale: 0.72, opacity: 0, rotate: 35, filter: 'blur(3px)' }}
                    transition={{ type: "spring", stiffness: 340, damping: 25, mass: 0.7 }}
                  >
                  <Button
                    type="button"
                    onClick={onStop}
                    size="icon"
                    className="h-9 w-9 rounded-[10px] border border-destructive/20 bg-destructive/10 text-destructive transition-colors hover:bg-destructive/20"
                    aria-label="Stop generation"
                  >
                    <Square className="h-3.5 w-3.5 fill-current" />
                  </Button>
                  </motion.div>
                ) : (
                  <motion.div
                    key="send"
                    className="absolute inset-0"
                    initial={{ scale: 0.72, opacity: 0, rotate: -35, filter: 'blur(3px)' }}
                    animate={{ scale: 1, opacity: 1, rotate: 0, filter: 'blur(0px)' }}
                    exit={{ scale: 0.72, opacity: 0, rotate: 35, filter: 'blur(3px)' }}
                    transition={{ type: "spring", stiffness: 340, damping: 25, mass: 0.7 }}
                  >
                  <Button
                    type="button"
                    onClick={handleSubmit}
                    disabled={!input.trim()}
                    size="icon"
                    className={cn(
                      "h-9 w-9 rounded-[10px] transition-colors shadow-sm",
                      input.trim()
                        ? "bg-primary text-primary-foreground hover:bg-primary/90"
                        : "bg-muted/60 text-muted-foreground/50 cursor-not-allowed"
                    )}
                    aria-label="Send message"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

      </motion.div>
      <div className="flex min-h-4 items-center justify-between px-1">
        <span className="text-xs font-medium text-muted-foreground/70">
          {isBusy ? 'Nova is generating…' : 'Nova can make mistakes. Verify important information.'}
        </span>
        {showCharCount && (
          <span className={cn(
            "font-mono text-xs tabular-nums",
            charCount > 1800 ? "text-destructive" : charCount > 1200 ? "text-amber-500" : "text-muted-foreground/70"
          )}>
            {charCount.toLocaleString()}/4000
          </span>
        )}
      </div>
    </div>
  );
};
