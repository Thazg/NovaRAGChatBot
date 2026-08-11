import { useEffect, useState } from 'react';
import { LogOut, Menu, Sparkles, User, MessageSquare, FolderOpen, Plus, ShieldCheck } from 'lucide-react';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatArea } from '../chat/ChatArea';
import { Sheet, SheetContent, SheetTrigger } from '../ui/sheet';

import { useChatStore } from '../../store/useChatStore';
import { SettingsDrawer } from './SettingsDrawer';
import { cn } from '../../lib/utils';
import { useResolvedTheme } from '../../hooks/useResolvedTheme';

export const Layout = () => {
  const { theme, avatar, sidebarActiveTab, setSidebarActiveTab, createConversation } = useChatStore();
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);
  const resolvedTheme = useResolvedTheme(theme);

  // Apply dark mode by default if theme is 'system'
  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');

    root.classList.add(resolvedTheme);
  }, [resolvedTheme]);

  return (
    <div className="nova-shell relative flex h-dvh w-full overflow-hidden text-foreground">
      <div className="nova-grid" />
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <main className="z-10 flex-1 flex flex-col min-w-0 relative overflow-hidden">

        {/* ===== MOBILE HEADER ===== */}
        <header className="md:hidden shrink-0 z-20 sticky top-0 bg-background/80 backdrop-blur-2xl border-b border-border/30">
          {/* Row 1: hamburger + branding + new chat + settings */}
          <div className="flex items-center justify-between px-3 h-[50px]">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <Sheet open={mobileSheetOpen} onOpenChange={setMobileSheetOpen}>
                <SheetTrigger asChild>
                  <button className="flex items-center gap-1.5 h-8 px-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
                    <Menu className="h-4 w-4" />
                    <span className="text-xs font-medium hidden">Menu</span>
                  </button>
                </SheetTrigger>
                <SheetContent side="left" hideClose className="p-0 border-r-0 bg-background/95 backdrop-blur-2xl w-[85vw] max-w-[340px]">
                  <div className="h-full w-full">
                    <Sidebar forceShow onClose={() => setMobileSheetOpen(false)} />
                  </div>
                </SheetContent>
              </Sheet>

              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary/30 via-primary/20 to-violet-500/20 border border-primary/25 flex items-center justify-center shadow-sm shrink-0">
                  <Sparkles className="h-3 w-3 text-primary" />
                </div>
                <span className="font-bold tracking-tight text-[14px] text-foreground">Nova AI</span>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={() => { createConversation(); }}
                className="flex items-center gap-1 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold shadow-sm hover:bg-primary/90 active:scale-95 transition-all"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New</span>
              </button>
              <SettingsDrawer />
              <button
                type="button"
                onClick={() => useChatStore.getState().logout()}
                className="h-8 w-8 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Row 2: segmented tab control */}
          <div className="px-3 pb-2">
            <div className="flex items-center gap-1 p-0.5 bg-muted/50 rounded-xl border border-border/30">
              <button
                onClick={() => { setSidebarActiveTab('conversations'); setMobileSheetOpen(true); }}
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-all",
                  sidebarActiveTab === 'conversations'
                    ? "bg-background shadow-sm text-foreground border border-border/30"
                    : "text-muted-foreground/70 hover:text-foreground"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                Chats
              </button>
              <button
                onClick={() => { setSidebarActiveTab('documents'); setMobileSheetOpen(true); }}
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 h-8 rounded-lg text-xs font-semibold transition-all",
                  sidebarActiveTab === 'documents'
                    ? "bg-background shadow-sm text-foreground border border-border/30"
                    : "text-muted-foreground/70 hover:text-foreground"
                )}
              >
                <FolderOpen className="h-3.5 w-3.5" />
                Docs
              </button>
            </div>
          </div>
        </header>

        {/* ===== DESKTOP HEADER ===== */}
        <header className="hidden md:flex h-[64px] border-b border-border/40 items-center justify-between px-6 bg-background/45 backdrop-blur-2xl z-20 sticky top-0 shrink-0">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary/30 via-primary/20 to-violet-500/20 border border-primary/25 flex items-center justify-center shadow-sm">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
              </div>
              <div>
                <span className="font-bold tracking-tight text-[14px] text-foreground">Nova AI</span>
                <span className="ml-1.5 text-[11px] text-muted-foreground/60 font-medium">Knowledge OS</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 flex-1 justify-end">
            <div className="hidden lg:flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1 text-[10px] font-semibold text-emerald-500/80">
              <ShieldCheck className="h-3 w-3" />
              Private workspace
            </div>
            <SettingsDrawer />
            <div className={cn(
              "w-8 h-8 rounded-full overflow-hidden border-2 shrink-0 transition-all",
              avatar ? "border-primary/40 shadow-sm shadow-primary/20" : "border-border/50 bg-muted/50"
            )}>
              {avatar ? (
                <img src={avatar} alt="User" className="h-full w-full object-cover" />
              ) : (
                <div className="h-full w-full flex items-center justify-center">
                  <User className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Chat area */}
        <ChatArea />
      </main>
    </div>
  );
};
