import { useCallback, useEffect, useRef, useState } from 'react';
import { useChatStore } from '../../store/useChatStore';
import { ChatBubble } from './ChatBubble';
import { ChatInput } from './ChatInput';
import { WelcomeScreen } from './WelcomeScreen';
import { GlobalSearch } from './GlobalSearch';
import { api } from '../../services/api';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { FolderOpen, Globe2, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '../ui/button';

const errorMessage = (error: unknown): string => error instanceof Error ? error.message : 'Unknown error';
const errorName = (error: unknown): string => error instanceof DOMException ? error.name : '';

export const ChatArea = () => {
  const {
    conversations,
    currentConversationId,
    addMessage,
    appendStreamToMessage,
    setIsStreaming,
    setIsLoading,
    createConversation,
    regenerateLastMessage,
    isStreaming,
    customInstructions,
    characterStyle,
    nickname,
    language,
    selectedDocument,
    setSelectedDocument,
    setSidebarActiveTab,
    setSidebarOpen,
  } = useChatStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchOffer, setSearchOffer] = useState<{ query: string; loading: boolean } | null>(null);

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const messages = currentConversation?.messages || [];

  const characterPrompts: Record<string, string> = {
    warm: 'Respond in a warm, caring, and affectionate manner. Use gentle and kind language.',
    enthusiastic: 'Respond with enthusiasm and energy. Be upbeat and excited in your tone.',
    professional: 'Respond in a professional, formal, and polished tone. Be precise and well-structured.',
    concise: 'Respond concisely and directly. Keep answers brief and to the point.',
    friendly: 'Respond in a casual, friendly, and approachable manner. Be conversational.',
    custom: '',
  };

  const buildInstructions = () => {
    const parts: string[] = [];
    if (nickname?.trim()) parts.push(`Address the user as "${nickname.trim()}".`);
    const characterPrompt = characterPrompts[characterStyle] || '';
    if (characterPrompt) parts.push(characterPrompt);
    if (customInstructions?.trim()) parts.push(customInstructions.trim());
    return parts.join('\n\n');
  };

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const { scrollHeight, clientHeight } = scrollRef.current;
      scrollRef.current.scrollTo({
        top: scrollHeight - clientHeight,
        behavior: 'smooth',
      });
    }
  }, []);

  const latestMessageLength = messages.at(-1)?.content.length ?? 0;
  useEffect(() => {
    const frame = requestAnimationFrame(scrollToBottom);
    return () => cancelAnimationFrame(frame);
  }, [messages.length, latestMessageLength, scrollToBottom]);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setIsLoading(false);
  }, [setIsLoading, setIsStreaming]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl + N: New Chat
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        createConversation();
        toast.success('New conversation created');
      }
      
      // Ctrl + K: Global Search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen(prev => !prev);
      }
      
      // Ctrl + /: Focus Input
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        const textarea = document.querySelector('textarea');
        if (textarea) {
          textarea.focus();
        }
      }
      
      // Esc: Stop Generation or Close Search
      if (e.key === 'Escape') {
        if (isSearchOpen) {
          e.preventDefault();
          setIsSearchOpen(false);
        } else if (isStreaming) {
          e.preventDefault();
          handleStop();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isStreaming, createConversation, isSearchOpen, handleStop]);

  const handleSearchDownload = useCallback(async (query: string) => {
    setSearchOffer({ query, loading: true });
    try {
      const result = await api.searchDownload(query);
      if (result.status === 'success' && result.downloaded.length > 0) {
        const newCount = result.downloaded.filter((document) => document.new).length;
        toast.success(`Downloaded ${newCount} new documents about "${query}"`);
        // Add a system message
        const targetConvId = currentConversationId || createConversation();
        addMessage(targetConvId, {
          role: 'system',
          content: `📥 Downloaded ${result.downloaded.length} PDF(s) about "${query}". Re-indexed. You can now ask questions about these documents.`,
        });
      } else {
        toast.info(result.message || 'No documents found for that query.');
      }
    } catch (err: unknown) {
      toast.error('Search failed: ' + errorMessage(err));
    } finally {
      setSearchOffer(null);
    }
  }, [currentConversationId, createConversation, addMessage]);

  const handleSearchAndDownload = useCallback(async (targetConvId: string, topic: string) => {
    const msgId = addMessage(targetConvId, { role: 'assistant', content: '' });
    const append = (text: string) => appendStreamToMessage(targetConvId, msgId, text);
    append(`🔍 Searching and downloading PDFs about "${topic}"...\n\n`);
    try {
      const result = await api.searchDownload(topic, 3);
      append(`📥 ${result.message || 'Download complete.'}\n\n`);
      if (result.downloaded?.length > 0) {
        const files = result.downloaded.map((document) => `- ${document.file_name}`).join('\n');
        append(`**Files added:**\n${files}\n\nYou can now ask questions about these documents.`);
      } else {
        append('No PDFs found for this topic. Try a different search term.');
      }
    } catch (err: unknown) {
      append(`❌ Search failed: ${errorMessage(err)}`);
    }
  }, [addMessage, appendStreamToMessage]);

  const handleSend = async (content: string) => {
    if (!content.trim()) return;

    let targetConvId = currentConversationId;
    if (!targetConvId) {
      targetConvId = createConversation();
    }

    addMessage(targetConvId, {
      role: 'user',
      content: content.trim(),
    });

    const trimmed = content.trim();
    const searchMatch = trimmed.match(/^(?:search|tìm)\s+(?:for|kiếm)?\s*(.+)/i);

    if (searchMatch) {
      const topic = searchMatch[1].trim();
      setIsLoading(true);
      await handleSearchAndDownload(targetConvId, topic);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    abortControllerRef.current = new AbortController();
    setSearchOffer(null);
    const assistantMessageId = addMessage(targetConvId, {
      role: 'assistant',
      content: '',
    });

    try {
      setIsStreaming(true);
      setIsLoading(false);

      await api.streamMessage(
        targetConvId,
        trimmed,
        (chunk) => {
          appendStreamToMessage(targetConvId, assistantMessageId, chunk);
        },
        abortControllerRef.current.signal,
        buildInstructions(),
        (action) => {
          if (action.type === 'search_offer') {
            setSearchOffer({ query: action.query, loading: false });
          }
        },
        language,
        false,
        selectedDocument?.name,
      );
    } catch (error: unknown) {
      if (errorName(error) === 'AbortError') {
        toast.info('Generation stopped');
      } else {
        appendStreamToMessage(targetConvId, assistantMessageId, 'Unable to reach Nova right now. Please try again.');
        toast.error('Failed to send message. Please try again.');
        console.error(error);
      }
    } finally {
      setIsStreaming(false);
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleRegenerate = async () => {
    if (!currentConversationId) return;
    
    const currentConversation = conversations.find(c => c.id === currentConversationId);
    if (!currentConversation || currentConversation.messages.length < 2) return;
    
    const lastUserMessage = currentConversation.messages.filter(m => m.role === 'user').pop();
    if (!lastUserMessage) return;
    
    regenerateLastMessage(currentConversationId);
    setIsLoading(true);
    abortControllerRef.current = new AbortController();
    const assistantMessageId = addMessage(currentConversationId, {
      role: 'assistant',
      content: '',
    });

    try {
      setIsStreaming(true);
      setIsLoading(false);

      await api.streamMessage(
        currentConversationId,
        lastUserMessage.content,
        (chunk) => {
          appendStreamToMessage(currentConversationId, assistantMessageId, chunk);
        },
        abortControllerRef.current.signal,
        buildInstructions(),
        undefined,
        language,
        true,
        selectedDocument?.name,
      );
    } catch (error: unknown) {
      if (errorName(error) === 'AbortError') {
        toast.info('Generation stopped');
      } else {
        appendStreamToMessage(currentConversationId, assistantMessageId, 'Unable to regenerate this response. Please try again.');
        toast.error('Failed to regenerate message. Please try again.');
        console.error(error);
      }
    } finally {
      setIsStreaming(false);
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="relative z-10 flex-1 flex flex-col h-full overflow-hidden bg-background/25">
      <GlobalSearch isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto pt-4 md:pt-8 scroll-smooth"
      >
        {messages.length === 0 ? (
          <WelcomeScreen onSelectSuggestion={handleSend} />
        ) : (
          <div className="mx-auto flex w-full max-w-[960px] flex-col px-4 pb-4 md:px-8 lg:px-10">
            {messages.map((message, index) => {
              const isLastMessage = index === messages.length - 1;
              const messageIsStreaming = isLastMessage && message.role === 'assistant' && isStreaming;
              const isLastAssistantMessage = message.role === 'assistant' && index === messages.findLastIndex(m => m.role === 'assistant');
              return (
                <ChatBubble
                  key={message.id}
                  message={message}
                  isStreaming={messageIsStreaming}
                  onRegenerate={isLastAssistantMessage ? handleRegenerate : undefined}
                />
              );
            })}

            {searchOffer && !searchOffer.loading && !isStreaming && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mx-auto mt-2 w-full max-w-[680px] rounded-[14px] border border-border/50 bg-card/75 p-3.5 shadow-sm"
              >
                <p className="text-sm font-semibold text-foreground">
                  {selectedDocument
                    ? `No matching passages found in ${selectedDocument.name}`
                    : 'No relevant document passages were found'}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Choose a document, rebuild the index, or expand the search to the web.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-[10px] px-3 text-xs"
                    onClick={() => {
                      setSidebarActiveTab('documents');
                      setSidebarOpen(true);
                      window.dispatchEvent(new CustomEvent('nova:open-sidebar'));
                    }}
                  >
                    <FolderOpen className="h-4 w-4" />
                    Choose a document
                  </Button>
                  {selectedDocument && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 rounded-[10px] px-3 text-xs"
                      onClick={() => setSelectedDocument(null)}
                    >
                      Clear scope
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-[10px] px-3 text-xs"
                    onClick={async () => {
                      try {
                        const result = await api.reindexDocuments();
                        if (result.job_id) await api.waitForIndexJob(result.job_id);
                        toast.success('Knowledge index rebuilt');
                        setSearchOffer(null);
                      } catch (error) {
                        toast.error(errorMessage(error));
                      }
                    }}
                  >
                    <RefreshCw className="h-4 w-4" />
                    Re-index
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleSearchDownload(searchOffer.query)}
                    className="h-9 rounded-[10px] px-3 text-xs text-muted-foreground"
                  >
                    <Globe2 className="h-4 w-4" />
                    Search web
                  </Button>
                </div>
              </motion.div>
            )}

            {searchOffer?.loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Searching and downloading PDFs about "{searchOffer.query.slice(0, 50)}"...
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* Input area with a feathered backdrop instead of a hard color edge */}
      <div className="nova-composer-dock relative isolate px-4 pb-[max(1.25rem,env(safe-area-inset-bottom,0.75rem))] pt-5 md:pb-6 md:pt-6">
        <div className="relative z-10 mx-auto w-full max-w-[920px]">
          <ChatInput onSend={handleSend} onStop={handleStop} />
        </div>
      </div>
    </div>
  );
};
