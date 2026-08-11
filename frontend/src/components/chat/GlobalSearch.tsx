import { useState, useEffect, useCallback } from 'react';
import { Search, MessageSquare, FileText, ArrowRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Input } from '../ui/input';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../store/useChatStore';
import { api, type Document } from '../../services/api';

interface SearchResult {
  id: string;
  type: 'conversation' | 'document' | 'message';
  title: string;
  content?: string;
  conversationId?: string;
}

interface GlobalSearchProps {
  isOpen: boolean;
  onClose: () => void;
}

export const GlobalSearch = ({ isOpen, onClose }: GlobalSearchProps) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const { conversations, setCurrentConversation, setSidebarActiveTab, setSidebarOpen } = useChatStore();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    api.getDocuments().then(setDocuments).catch(() => setDocuments([]));
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const searchResults: SearchResult[] = [];
    const lowerQuery = query.toLowerCase();

    conversations.forEach(conv => {
      if (conv.title.toLowerCase().includes(lowerQuery)) {
        searchResults.push({
          id: conv.id,
          type: 'conversation',
          title: conv.title,
          conversationId: conv.id
        });
      }

      conv.messages.forEach(msg => {
        if (msg.content.toLowerCase().includes(lowerQuery)) {
          searchResults.push({
            id: `${conv.id}-${msg.id}`,
            type: 'message',
            title: conv.title,
            content: msg.content.slice(0, 100),
            conversationId: conv.id
          });
        }
      });
    });

    documents.forEach((doc) => {
      if (doc.name.toLowerCase().includes(lowerQuery)) {
        searchResults.push({
          id: `document-${doc.id}`,
          type: 'document',
          title: doc.name,
          content: `${doc.chunks || 0} indexed chunks`,
        });
      }
    });

    setResults(searchResults.slice(0, 10));
    setSelectedIndex(0);
  }, [query, conversations, documents]);

  const handleSelectResult = useCallback((result: SearchResult) => {
    if (result.conversationId) {
      setCurrentConversation(result.conversationId);
    } else if (result.type === 'document') {
      setSidebarActiveTab('documents');
      setSidebarOpen(true);
    }
    onClose();
  }, [onClose, setCurrentConversation, setSidebarActiveTab, setSidebarOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && results.length > 0) {
        e.preventDefault();
        handleSelectResult(results[selectedIndex]);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex, onClose, handleSelectResult]);

  const getResultIcon = (type: SearchResult['type']) => {
    switch (type) {
      case 'conversation':
        return <MessageSquare className="h-4 w-4 text-primary" />;
      case 'message':
        return <MessageSquare className="h-4 w-4 text-muted-foreground" />;
      case 'document':
        return <FileText className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.2, type: "spring", stiffness: 300, damping: 25 }}
            className="fixed top-[12%] sm:top-[18%] left-1/2 -translate-x-1/2 w-[calc(100%_-_1.5rem)] max-w-2xl z-50"
          >
            <div className="nova-panel rounded-2xl shadow-2xl overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-4 border-b border-border/50">
                <Search className="h-5 w-5 text-muted-foreground" />
                <Input
                  placeholder="Search conversations, documents, messages..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="flex-1 h-10 border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 text-base placeholder:text-muted-foreground/60"
                  autoFocus
                />
                <kbd className="hidden sm:inline-flex h-6 items-center gap-1 rounded border border-border/40 bg-muted/50 px-2 text-[11px] font-medium text-muted-foreground">
                  <span className="text-xs">ESC</span>
                </kbd>
              </div>

              <div className="max-h-[400px] overflow-y-auto p-2">
                {query.trim() === '' ? (
                  <div className="py-8 text-center">
                    <Search className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground">Start typing to search</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">
                      Use <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border/40 text-[10px]">↑</kbd> <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border/40 text-[10px]">↓</kbd> to navigate, <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border/40 text-[10px]">Enter</kbd> to select
                    </p>
                  </div>
                ) : results.length === 0 ? (
                  <div className="py-8 text-center">
                    <p className="text-sm text-muted-foreground">No results found</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {results.map((result, idx) => (
                      <motion.button
                        key={result.id}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        onClick={() => handleSelectResult(result)}
                        className={cn(
                          "w-full flex items-start gap-3 p-3 rounded-xl text-left transition-all",
                          idx === selectedIndex
                            ? "bg-primary/10 border border-primary/20"
                            : "hover:bg-muted/50 border border-transparent"
                        )}
                      >
                        <div className="mt-0.5 shrink-0">
                          {getResultIcon(result.type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{result.title}</p>
                          {result.content && (
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{result.content}</p>
                          )}
                        </div>
                        <ArrowRight className="h-4 w-4 text-muted-foreground/50 shrink-0 mt-0.5" />
                      </motion.button>
                    ))}
                  </div>
                )}
              </div>

              {results.length > 0 && (
                <div className="px-4 py-3 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{results.length} results</span>
                  <div className="flex items-center gap-2">
                    <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border/40 text-[10px]">↑↓</kbd>
                    <span>to navigate</span>
                    <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border/40 text-[10px]">↵</kbd>
                    <span>to select</span>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
