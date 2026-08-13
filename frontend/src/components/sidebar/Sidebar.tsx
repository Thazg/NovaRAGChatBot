import React, { useState, useMemo, useEffect } from 'react';
import { Copy, Download, Edit2, FolderOpen, LogOut, MessageSquare, Moon, MoreHorizontal, PanelLeft, PanelLeftClose, Pin, Search, Settings, Sparkles, SquarePen, Sun, Trash2, UserCircle } from 'lucide-react';
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
      className="w-full min-w-0 max-w-full"
    >
      <div
        className={cn(
          "group flex w-full min-w-0 max-w-full items-center overflow-hidden rounded-xl border cursor-pointer transition-all duration-200",
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
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] transition-colors",
            isActive ? "bg-primary/20 text-primary" : "bg-muted/50 text-muted-foreground group-hover:text-foreground"
          )}>
            <MessageSquare className="h-3.5 w-3.5" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium leading-tight">{conv.title}</p>
              <p className="mt-0.5 truncate text-xs text-muted-foreground/70">
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
                className="h-9 w-9 shrink-0 rounded-[10px] text-muted-foreground opacity-100 transition-colors hover:text-foreground lg:opacity-0 lg:group-hover:opacity-100"
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
      animate={{ width: forceShow ? "100%" : (sidebarOpen ? 320 : 72) }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className={cn(
        "nova-sidebar z-40 flex h-full min-w-0 shrink-0 flex-col overflow-hidden border-r border-border/40",
        forceShow ? "flex" : "hidden md:flex"
      )}
    >
      {/* Header: New Chat + Toggle */}
      <div className={cn("flex w-full min-w-0 shrink-0 items-center p-3", sidebarOpen ? "justify-between gap-2" : "justify-center flex-col gap-3")}>
        <motion.div whileTap={{ scale: 0.98 }} className={cn(sidebarOpen ? "min-w-0 flex-1" : "w-auto")}>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button 
                  onClick={() => { createConversation(); toast.success('New chat created'); }}
                  className={cn(
                    "h-10 rounded-[10px] border border-primary/25 bg-primary/10 font-semibold text-primary shadow-none transition-colors hover:bg-primary/15",
                    sidebarOpen ? "w-full min-w-0 max-w-full justify-start gap-2.5 px-4" : "w-10 justify-center p-0"
                  )}
                  aria-label="New chat"
                >
                  <SquarePen className="h-[18px] w-[18px]" />
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
            "h-9 w-9 shrink-0 rounded-[10px] text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground",
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
            <div className="relative min-w-0 max-w-full">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
              <Input
                placeholder="Search..."
                value={searchQuery}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
                className="h-10 rounded-[10px] border-border/40 bg-muted/30 pl-9 text-[13px] placeholder:text-muted-foreground/60 focus-visible:ring-1 focus-visible:ring-primary/40"
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
            <div className="flex w-full min-w-0 items-center gap-1 overflow-hidden rounded-xl border border-border/20 bg-muted/30 p-1">
              <button
                className={cn(
                  "flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors",
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
                  "flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors",
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
          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 pb-2">
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
                  <DocumentManager onUploadComplete={() => setActiveTab('documents')} onSelectDocument={onClose} />
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
                  <p className="truncate text-left text-xs text-muted-foreground/70">Personal workspace</p>
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
        <DialogContent className="overflow-hidden rounded-[18px] border-border/60 bg-background sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-lg">
              <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-primary/10 text-primary">
                <Sparkles className="h-[18px] w-[18px]" />
              </span>
              About Nova
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <p className="text-sm font-semibold text-foreground">Nova AI Knowledge OS</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                A private, document-grounded workspace for searchable and citation-aware conversations.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded-md border border-border/60 bg-muted/60 px-2 py-1 font-mono">v2.1.0</span>
              <span>React · TypeScript · FastAPI · Hybrid retrieval</span>
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
