import React, { useState, useMemo, useEffect } from 'react';
import { MessageSquare, PanelLeftClose, PanelLeft, MoreHorizontal, Trash2, Edit2, Search, UserCircle, Sparkles, Pin, Copy, Download, FolderOpen, Settings, Sun, Moon, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { useChatStore } from '../../store/useChatStore';
import { Button } from '../ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { cn } from '../../lib/utils';
import type { Conversation } from '../../types';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../ui/tooltip';
import { DocumentManager } from './DocumentManager';

interface ConversationItemProps {
  conv: Conversation;
  idx: number;
  currentConversationId: string | null;
  sidebarOpen: boolean;
  setCurrentConversation: (id: string) => void;
  handleRename: (id: string, title: string) => void;
  handleDelete: (id: string) => void;
  handlePin: (id: string) => void;
  handleDuplicate: (id: string) => void;
  handleExport: (conv: Conversation) => void;
  isPinned: boolean;
}

const ConversationItem = ({
  conv,
  idx,
  currentConversationId,
  sidebarOpen,
  setCurrentConversation,
  handleRename,
  handleDelete,
  handlePin,
  handleDuplicate,
  handleExport,
  isPinned
}: ConversationItemProps) => {
  const isActive = currentConversationId === conv.id;

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -12, transition: { duration: 0.15 } }}
      transition={{ duration: 0.25, delay: idx * 0.03, type: "spring", stiffness: 350, damping: 30 }}
      layout
    >
      <div
        className={cn(
          "group flex items-center rounded-xl cursor-pointer transition-all duration-200 border",
          isActive
            ? "bg-primary/10 border-primary/20 text-foreground shadow-sm shadow-primary/5"
            : "bg-transparent border-transparent hover:bg-muted/50 text-muted-foreground hover:text-foreground",
          sidebarOpen ? "p-2.5 gap-2.5" : "p-2.5 justify-center"
        )}
        onClick={() => setCurrentConversation(conv.id)}
        title={!sidebarOpen ? conv.title : undefined}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setCurrentConversation(conv.id)}
      >
        <div className="flex items-center gap-2.5 overflow-hidden min-w-0 flex-1">
          {isPinned && <Pin className="h-3 w-3 text-primary/60 shrink-0 -rotate-45" />}
          <div className={cn(
            "h-7 w-7 rounded-lg flex items-center justify-center shrink-0 transition-colors",
            isActive ? "bg-primary/20 text-primary" : "bg-muted/50 text-muted-foreground group-hover:text-foreground"
          )}>
            <MessageSquare className="h-3.5 w-3.5" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium leading-tight">{conv.title}</p>
              <p className="text-[11px] text-muted-foreground/60 truncate mt-0.5">
                {conv.messages.length > 0 ? `${conv.messages.length} messages` : 'Empty'}
              </p>
            </div>
          )}
        </div>
        
        {sidebarOpen && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground/50 hover:text-foreground rounded-lg opacity-0 group-hover:opacity-100 transition-all shrink-0"
                  onClick={(e: React.MouseEvent) => e.stopPropagation()}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44 rounded-xl border-border/50 bg-background/95 backdrop-blur-2xl shadow-xl z-50">
              <DropdownMenuItem className="rounded-lg cursor-pointer text-[13px]" onSelect={() => handleRename(conv.id, conv.title)}>
                <Edit2 className="h-3.5 w-3.5 mr-2" /> Rename
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg cursor-pointer text-[13px]" onSelect={() => handlePin(conv.id)}>
                <Pin className="h-3.5 w-3.5 mr-2" /> {isPinned ? 'Unpin' : 'Pin'}
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg cursor-pointer text-[13px]" onSelect={() => handleDuplicate(conv.id)}>
                <Copy className="h-3.5 w-3.5 mr-2" /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg cursor-pointer text-[13px]" onSelect={() => handleExport(conv)}>
                <Download className="h-3.5 w-3.5 mr-2" /> Export
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:bg-destructive/10 focus:text-destructive rounded-lg cursor-pointer text-[13px]"
                onSelect={() => handleDelete(conv.id)}
              >
                <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </motion.div>
  );
};

// Group label component
const GroupLabel = ({ label }: { label: string }) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    className="px-2.5 pt-3 pb-1.5 first:pt-0"
  >
    <p className="text-[10.5px] font-semibold text-muted-foreground/65 tracking-[0.2em] uppercase">
      {label}
    </p>
  </motion.div>
);

export const Sidebar = ({ forceShow, onClose }: { forceShow?: boolean; onClose?: () => void }) => {
  const {
    conversations,
    currentConversationId,
    sidebarOpen: storeSidebarOpen,
    toggleSidebar,
    createConversation,
    setCurrentConversation,
    deleteConversation,
    renameConversation,
    pinConversation,
    duplicateConversation,
    setSidebarOpen,
    avatar,
    displayName,
    setTheme,
    sidebarActiveTab,
    setSidebarActiveTab,
  } = useChatStore();
  const sidebarOpen = forceShow ? true : storeSidebarOpen;

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [aboutOpen, setAboutOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);
  const activeTab = sidebarActiveTab;
  const setActiveTab = setSidebarActiveTab;

  useEffect(() => {
    if (!sidebarOpen && activeTab === 'documents') {
      setActiveTab('conversations');
    }
  }, [sidebarOpen, activeTab, setActiveTab]);

  const filteredConversations = conversations.filter((c: Conversation) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groupedConversations = useMemo(() => {
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    const sevenDays = 7 * oneDay;

    const pinned = filteredConversations.filter(c => c.pinned);
    const unpinned = filteredConversations.filter(c => !c.pinned);

    const today = unpinned.filter(c => now - c.updatedAt < oneDay);
    const yesterday = unpinned.filter(c => now - c.updatedAt >= oneDay && now - c.updatedAt < 2 * oneDay);
    const last7Days = unpinned.filter(c => now - c.updatedAt >= 2 * oneDay && now - c.updatedAt < sevenDays);
    const older = unpinned.filter(c => now - c.updatedAt >= sevenDays);

    return { pinned, today, yesterday, last7Days, older };
  }, [filteredConversations]);

  const handleDelete = (id: string) => {
    setConversationToDelete(id);
    setDeleteDialogOpen(true);
  };

  const handleToggleSidebar = () => {
    if (sidebarOpen && activeTab === 'documents') {
      setActiveTab('conversations');
    }
    toggleSidebar();
  };

  const handleQuickOpen = (tab: 'conversations' | 'documents') => {
    setActiveTab(tab);
    setSidebarOpen(true);
  };

  const confirmDelete = () => {
    if (conversationToDelete) {
      deleteConversation(conversationToDelete);
      setDeleteDialogOpen(false);
      setConversationToDelete(null);
      toast.success('Conversation deleted');
    }
  };

  const handleRename = (id: string, currentTitle: string) => {
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const submitRename = () => {
    if (editingId && editTitle.trim()) {
      renameConversation(editingId, editTitle.trim());
    }
    setEditingId(null);
  };

  const handlePin = (id: string) => {
    pinConversation(id);
    toast.success('Updated pin status');
  };

  const handleDuplicate = (id: string) => {
    duplicateConversation(id);
    toast.success('Conversation duplicated');
  };

  const handleExport = (conv: Conversation) => {
    const content = conv.messages.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const reserved = '<>:"/\\|?*';
    const safeTitle = Array.from(conv.title)
      .map((char) => reserved.includes(char) || char.charCodeAt(0) < 32 ? '_' : char)
      .join('')
      .slice(0, 80) || 'conversation';
    a.download = `${safeTitle}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Conversation exported');
  };

  const renderConversationGroup = (convs: Conversation[], label: string) => {
    if (convs.length === 0) return null;
    return (
      <div key={label} className="space-y-0.5">
        <GroupLabel label={label} />
        {convs.map((conv: Conversation, idx) => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            idx={idx}
            currentConversationId={currentConversationId}
            sidebarOpen={sidebarOpen}
            setCurrentConversation={setCurrentConversation}
            handleRename={handleRename}
            handleDelete={handleDelete}
            handlePin={handlePin}
            handleDuplicate={handleDuplicate}
            handleExport={handleExport}
            isPinned={!!conv.pinned}
          />
        ))}
      </div>
    );
  };

  return (
    <motion.div 
      initial={false}
      animate={{ width: forceShow ? "100%" : (sidebarOpen ? 340 : 76) }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className={cn(
        "h-full flex flex-col z-40 shrink-0 overflow-hidden border-r border-border/40",
        forceShow ? "flex" : "hidden md:flex"
      )}
      style={{
        background: 'linear-gradient(180deg, hsl(var(--background)) 0%, hsl(var(--card)) 100%)',
      }}
    >
      {/* Header: New Chat + Toggle */}
      <div className={cn("p-3 flex items-center shrink-0", sidebarOpen ? "justify-between gap-2" : "justify-center flex-col gap-3")}>
        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} className={cn(sidebarOpen ? "w-full" : "w-auto")}>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button 
                  onClick={() => { createConversation(); toast.success('New chat created'); }}
                  className={cn(
                    "h-10 rounded-xl bg-gradient-to-r from-primary to-violet-500 text-white shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30 transition-all font-medium border-0",
                    sidebarOpen ? "w-full justify-start gap-2.5 px-4" : "w-10 justify-center p-0"
                  )}
                  aria-label="New chat"
                >
                  <Sparkles className="h-4 w-4" />
                  {sidebarOpen && <span className="text-[13px]">New Chat</span>}
                </Button>
              </TooltipTrigger>
              {!sidebarOpen && <TooltipContent side="right"><p>New Chat</p></TooltipContent>}
            </Tooltip>
          </TooltipProvider>
        </motion.div>
        
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={forceShow ? onClose : handleToggleSidebar}
          className={cn(
            "shrink-0 text-muted-foreground/60 hover:text-foreground hover:bg-muted/50 rounded-xl transition-all h-8 w-8",
            sidebarOpen ? "" : "mt-1"
          )}
          aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          <motion.div
            animate={{ rotate: sidebarOpen ? 0 : 180 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          >
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
          </motion.div>
        </Button>
      </div>

      {/* Search bar (expanded only) */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="px-3 pb-2 shrink-0"
          >
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
              <Input
                placeholder="Search..."
                value={searchQuery}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
                className="pl-8 h-9 rounded-xl bg-muted/30 border-border/30 focus-visible:ring-1 focus-visible:ring-primary/40 text-[13px] placeholder:text-muted-foreground/55 transition-all"
                aria-label="Search conversations"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tab switcher + Content area */}
      {sidebarOpen ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Tab bar */}
          <div className="px-3 pb-2 shrink-0">
            <div className="flex items-center gap-1 p-1 bg-muted/30 rounded-xl border border-border/20">
              <button
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 h-7 rounded-lg text-[11.5px] font-semibold transition-all",
                  activeTab === 'conversations'
                    ? "bg-background shadow-sm text-foreground border border-border/40"
                    : "text-muted-foreground/60 hover:text-muted-foreground"
                )}
                onClick={() => setActiveTab('conversations')}
              >
                <MessageSquare className="h-3 w-3" />
                Chats
                {conversations.length > 0 && (
                  <span className="text-[10px] opacity-50">{conversations.length}</span>
                )}
              </button>
              <button
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 h-7 rounded-lg text-[11.5px] font-semibold transition-all",
                  activeTab === 'documents'
                    ? "bg-background shadow-sm text-foreground border border-border/40"
                    : "text-muted-foreground/60 hover:text-muted-foreground"
                )}
                onClick={() => setActiveTab('documents')}
              >
                <FolderOpen className="h-3 w-3" />
                Docs
              </button>
            </div>
          </div>

          {/* Scrollable content — this is the key fix: overflow-y-auto with min-h-0 on the flex parent */}
          <div className="flex-1 overflow-y-auto min-h-0 px-3 pb-2">
            <AnimatePresence mode="popLayout">
              {activeTab === 'documents' ? (
                <motion.div
                  key="documents"
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  transition={{ duration: 0.2 }}
                  className="h-full"
                >
                  <DocumentManager onUploadComplete={() => setActiveTab('documents')} />
                </motion.div>
              ) : (
                <motion.div
                  key="conversations"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  transition={{ duration: 0.2 }}
                  className="space-y-1"
                >
                  {filteredConversations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <div className="w-12 h-12 rounded-2xl bg-muted/40 flex items-center justify-center mb-3">
                        <MessageSquare className="h-5 w-5 text-muted-foreground/40" />
                      </div>
                      <p className="text-[13px] text-muted-foreground/60 font-medium">No conversations yet</p>
                      <p className="text-[11px] text-muted-foreground/50 mt-1">Start a new chat to begin</p>
                    </div>
                  ) : (
                    <>
                      {renderConversationGroup(groupedConversations.pinned, 'Pinned')}
                      {renderConversationGroup(groupedConversations.today, 'Today')}
                      {renderConversationGroup(groupedConversations.yesterday, 'Yesterday')}
                      {renderConversationGroup(groupedConversations.last7Days, 'Last 7 Days')}
                      {renderConversationGroup(groupedConversations.older, 'Older')}
                    </>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      ) : (
        /* Collapsed sidebar icons */
        <div className="flex-1 flex flex-col items-center justify-between py-4 px-2">
          <div className="flex flex-col items-center gap-2 w-full">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className={cn(
                      "h-9 w-9 rounded-xl transition-all",
                      activeTab === 'conversations'
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                    onClick={() => handleQuickOpen('conversations')}
                    aria-label="Open chats"
                  >
                    <MessageSquare className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">Chats</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-9 w-9 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
                    onClick={() => handleQuickOpen('documents')}
                    aria-label="Open documents"
                  >
                    <FolderOpen className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">Documents</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <motion.div
            animate={{ opacity: [0.3, 0.6, 0.3] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            className="text-[9px] uppercase tracking-[0.3em] text-muted-foreground/30 font-bold"
          >
            Nova
          </motion.div>
        </div>
      )}

      {/* Footer: User profile */}
      <div className={cn("border-t border-border/30 shrink-0", sidebarOpen ? "p-3" : "p-2.5 flex justify-center")}>
        {sidebarOpen ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <div className="flex items-center rounded-xl hover:bg-muted/40 transition-all cursor-pointer gap-3 p-2 w-full group">
                {avatar ? (
                   <img src={avatar} alt="User" className="h-9 w-9 rounded-full object-cover border-2 border-primary/30 shadow-sm shrink-0" />
                ) : (
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary/20 to-violet-500/20 flex items-center justify-center text-primary group-hover:from-primary/30 group-hover:to-violet-500/30 transition-all shadow-sm shrink-0">
                    <UserCircle className="h-4 w-4" />
                  </div>
                )}
                <div className="flex-1 overflow-hidden min-w-0">
                  <p className="text-[13px] font-semibold truncate text-left">{displayName || 'User'}</p>
                  <p className="text-[11px] text-muted-foreground/65 truncate text-left">Private workspace</p>
                </div>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-56 rounded-xl border-border/50">
              <DropdownMenuItem className="rounded-lg gap-3 py-2.5 cursor-pointer" onClick={() => useChatStore.getState().setSettingsOpen(true)}>
                <Settings className="h-4 w-4" />
                <span>Profile Settings</span>
              </DropdownMenuItem>
              <DropdownMenuItem className="rounded-lg gap-3 py-2.5 cursor-pointer" onClick={() => {
                const isDark = document.documentElement.classList.contains('dark');
                setTheme(isDark ? 'light' : 'dark');
              }}>
                {document.documentElement.classList.contains('dark') ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                <span>{document.documentElement.classList.contains('dark') ? 'Light Mode' : 'Dark Mode'}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="rounded-lg gap-3 py-2.5 cursor-pointer" onClick={() => setAboutOpen(true)}>
                <Sparkles className="h-4 w-4" />
                <span>About Nova</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="rounded-lg gap-3 py-2.5 cursor-pointer text-muted-foreground hover:text-destructive focus:text-destructive" onClick={() => useChatStore.getState().logout()}>
                <LogOut className="h-4 w-4" />
                <span>Sign out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center justify-center cursor-pointer group">
                  {avatar ? (
                     <img src={avatar} alt="User" className="h-9 w-9 rounded-full object-cover border-2 border-primary/30 shadow-sm shrink-0" />
                  ) : (
                    <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary/20 to-violet-500/20 flex items-center justify-center text-primary group-hover:from-primary/30 group-hover:to-violet-500/30 transition-all shadow-sm shrink-0">
                      <UserCircle className="h-4 w-4" />
                    </div>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>{displayName || 'User'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* Rename dialog */}
      <Dialog open={!!editingId} onOpenChange={(open: boolean) => !open && setEditingId(null)}>
        <DialogContent className="rounded-2xl border-border/50 sm:max-w-md bg-background/95 backdrop-blur-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg">Rename Conversation</DialogTitle>
          </DialogHeader>
          <Input 
            value={editTitle}
            className="rounded-xl border-border/50 h-11"
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditTitle(e.target.value)}
            maxLength={120}
            onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && submitRename()}
            autoFocus
          />
          <DialogFooter>
            <Button variant="ghost" className="rounded-xl" onClick={() => setEditingId(null)}>Cancel</Button>
            <Button className="rounded-xl bg-primary" onClick={submitRename}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="rounded-2xl border-border/50 sm:max-w-md bg-background/95 backdrop-blur-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg">Delete Conversation</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Are you sure you want to delete this conversation? This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="ghost" className="rounded-xl" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" className="rounded-xl" onClick={confirmDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* About dialog */}
      <Dialog open={aboutOpen} onOpenChange={setAboutOpen}>
        <DialogContent className="rounded-2xl border-border/50 sm:max-w-md bg-background/95 backdrop-blur-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              Nova AI Agent
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground leading-relaxed">
              A private document intelligence workspace powered by Groq or your local Ollama model.
            </p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
              <span className="px-2 py-0.5 rounded-md bg-muted font-mono">v2.0.0</span>
              <span>Built with React + TypeScript</span>
            </div>
          </div>
          <DialogFooter>
            <Button className="rounded-xl" onClick={() => setAboutOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};
