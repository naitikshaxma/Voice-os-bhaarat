import { useState, useEffect, useCallback } from 'react';

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: number; // ms epoch
}

interface SidebarProps {
  sessions: ChatSession[];
  currentSessionId: string;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession?: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
  isLoading?: boolean;
  authEmail?: string;
  authName?: string;
}

function timeAgo(ms: number): string {
  if (!ms) return '';
  const diff = Date.now() - ms;
  const m = Math.floor(diff / 60000);
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(diff / 86400000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (d < 7) return `${d}d ago`;
  return new Date(ms).toLocaleDateString();
}

function groupSessions(sessions: ChatSession[]) {
  const today: ChatSession[] = [];
  const yesterday: ChatSession[] = [];
  const older: ChatSession[] = [];
  const now = Date.now();
  sessions.forEach(s => {
    const diff = now - s.updatedAt;
    if (diff < 86400000) today.push(s);
    else if (diff < 172800000) yesterday.push(s);
    else older.push(s);
  });
  return { today, yesterday, older };
}

function SkeletonItem() {
  return (
    <div className="px-3 py-3 rounded-lg animate-pulse">
      <div className="h-3 bg-[#2a2a2a] rounded w-4/5 mb-2" />
      <div className="h-2 bg-[#222] rounded w-2/5" />
    </div>
  );
}

function SessionGroup({ label, sessions, currentSessionId, onSelectSession, onDeleteSession, onToggle }: {
  label: string;
  sessions: ChatSession[];
  currentSessionId: string;
  onSelectSession: (id: string) => void;
  onDeleteSession?: (id: string) => void;
  onToggle: () => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (!sessions.length) return null;
  return (
    <div className="mb-3">
      <p className="text-[10px] font-semibold text-[#4b5563] uppercase tracking-widest px-3 mb-1">{label}</p>
      {sessions.map(session => {
        const isActive = currentSessionId === session.id;
        return (
          <div
            key={session.id}
            className="relative group"
            onMouseEnter={() => setHovered(session.id)}
            onMouseLeave={() => setHovered(null)}
          >
            <button
              onClick={() => {
                onSelectSession(session.id);
                if (window.innerWidth < 768) onToggle();
              }}
              className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 ${
                isActive
                  ? 'bg-[#1e3a5f] text-white border border-[#2563eb]/40'
                  : 'text-[#9ca3af] hover:bg-[#1a1a1a] hover:text-[#d1d5db]'
              }`}
            >
              {/* Active indicator */}
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-blue-500 rounded-r-full" />
              )}
              <span className="block truncate pr-6 font-medium">
                {session.title || 'New Conversation'}
              </span>
              <span className="block text-[10px] text-[#4b5563] mt-0.5">
                {timeAgo(session.updatedAt)}
              </span>
            </button>

            {/* Delete button — appears on hover */}
            {onDeleteSession && hovered === session.id && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm('Delete this conversation?')) onDeleteSession(session.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#4b5563] hover:text-red-400 transition rounded"
                title="Delete conversation"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" viewBox="0 0 16 16">
                  <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                  <path fillRule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                </svg>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function Sidebar({
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  isOpen,
  onToggle,
  isLoading = false,
  authEmail = '',
  authName = '',
}: SidebarProps) {
  const { today, yesterday, older } = groupSessions(sessions);

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={onToggle}
        />
      )}

      <div
        className={`fixed md:relative z-50 h-screen flex flex-col transition-transform duration-300 ease-in-out
          w-64 md:w-72 bg-[#0d0d0d] border-r border-[#1f1f1f] ${
            isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
          }`}
      >
        {/* Header */}
        <div className="p-3 border-b border-[#1f1f1f] flex items-center gap-2">
          {/* Logo mark */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center flex-shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="white" viewBox="0 0 16 16">
                <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/>
                <path d="M10 8a2 2 0 1 1-4 0V3a2 2 0 1 1 4 0v5z"/>
              </svg>
            </div>
            <span className="text-sm font-semibold text-white truncate">Voice OS Bharat</span>
          </div>
          {/* Close on mobile */}
          <button
            onClick={onToggle}
            className="md:hidden p-1.5 text-[#6b7280] hover:text-white rounded transition"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
            </svg>
          </button>
        </div>

        {/* New Chat button */}
        <div className="p-3 border-b border-[#1f1f1f]">
          <button
            id="new-chat-btn"
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 active:scale-[0.98] text-white px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 shadow-sm"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
              <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/>
            </svg>
            New Chat
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5 scrollbar-thin scrollbar-thumb-[#2a2a2a] scrollbar-track-transparent">
          {isLoading ? (
            <>
              <SkeletonItem />
              <SkeletonItem />
              <SkeletonItem />
            </>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <div className="w-10 h-10 rounded-full bg-[#1a1a1a] flex items-center justify-center mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="#4b5563" viewBox="0 0 16 16">
                  <path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zm-2 6a1 1 0 1 0-2 0 1 1 0 0 0 2 0zm-3 0a1 1 0 1 0-2 0 1 1 0 0 0 2 0zm-3 0a1 1 0 1 0-2 0 1 1 0 0 0 2 0z"/>
                </svg>
              </div>
              <p className="text-xs text-[#4b5563]">No conversations yet.</p>
              <p className="text-xs text-[#374151] mt-1">Start asking questions!</p>
            </div>
          ) : (
            <>
              <SessionGroup
                label="Today"
                sessions={today}
                currentSessionId={currentSessionId}
                onSelectSession={onSelectSession}
                onDeleteSession={onDeleteSession}
                onToggle={onToggle}
              />
              <SessionGroup
                label="Yesterday"
                sessions={yesterday}
                currentSessionId={currentSessionId}
                onSelectSession={onSelectSession}
                onDeleteSession={onDeleteSession}
                onToggle={onToggle}
              />
              <SessionGroup
                label="Older"
                sessions={older}
                currentSessionId={currentSessionId}
                onSelectSession={onSelectSession}
                onDeleteSession={onDeleteSession}
                onToggle={onToggle}
              />
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-[#1f1f1f]">
          <div className="flex items-center gap-2 px-2 py-1.5">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0">
              {authName ? authName[0]?.toUpperCase() : authEmail ? authEmail[0]?.toUpperCase() : 'G'}
            </div>
            <span className="text-xs text-[#6b7280] truncate">
              {authName ? `Signed in as ${authName}` : authEmail ? `Signed in as ${authEmail}` : 'Not signed in'}
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
