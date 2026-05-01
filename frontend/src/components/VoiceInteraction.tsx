import { useState, useEffect, useCallback, useRef } from 'react';
import BackButton from './BackButton';
import { speakText } from '@/lib/voiceUtils';
import MessageBubble, { type ChatMessage } from './chat/MessageBubble';
import SuggestionChips from './chat/SuggestionChips';
import TypingIndicator from './chat/TypingIndicator';
import Sidebar, { ChatSession } from './Sidebar';

const API = import.meta.env.VITE_API_URL || '';
// In local dev, use Vite proxy to avoid CORS/origin mismatches.
const BACKEND_URL = import.meta.env.DEV ? '' : API;

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

interface VoiceInteractionProps {
  language: Language;
  onBack: () => void;
}


const backLabels: Record<string, string> = {
  hi: 'Change language',
  en: 'Change language',
  mr: 'Change language',
  bn: 'Change language',
  ta: 'Change language',
  te: 'Change language',
  kn: 'Change language',
  ml: 'Change language',
  pa: 'Change language',
  gu: 'Change language',
};

const langAccents: Record<string, string> = {
  hi: '#f59e0b',
  en: '#9ca3af',
  mr: '#ea580c',
  bn: '#dc2626',
  ta: '#14b8a6',
  te: '#b91c1c',
  kn: '#16a34a',
  ml: '#7c3aed',
  pa: '#d97706',
  gu: '#2563eb',
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: any) => void) | null;
  start: () => void;
  stop: () => void;
};

/** Get or create a stable user_id in localStorage */
function getUserId(): string {
  const key = 'voice_os_user_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = `user-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    localStorage.setItem(key, id);
  }
  return id;
}

function getEffectiveUserId(): string {
  const token = localStorage.getItem('voice_os_token');
  const authId = localStorage.getItem('voice_os_auth_user_id');
  if (token && authId) return authId;
  return getUserId();
}


function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [processingText, setProcessingText] = useState('');
  const [typedQuery, setTypedQuery] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isSidebarLoading, setIsSidebarLoading] = useState(false);
  const [latestAudioBase64, setLatestAudioBase64] = useState<string>('');
  const [authEmail, setAuthEmail] = useState('');
  const [authName, setAuthName] = useState('');

  const hasGreetedRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const liveTranscriptRef = useRef('');
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastActionAtRef = useRef(0);
  const inFlightRef = useRef(false);
  const lastRequestRef = useRef<{ text?: string; audioBlob?: Blob; liveText?: string } | null>(null);
  const silenceTimerRef = useRef<number | null>(null);

  const ACTION_DEBOUNCE_MS = 450;
  const ASSISTANT_RESPONSE_DELAY_MS = 320;

  const backLabel = backLabels[language.code] ?? backLabels.en;
  const accent = langAccents[language.code] ?? '#f59e0b';
  const inputPlaceholder = language.code === 'hi'
    ? 'अपना प्रश्न लिखें...'
    : language.code === 'en'
      ? 'Type your question...'
      : 'Type your question...';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isProcessing]);

  // ── Fetch conversations from MongoDB Atlas ─────────────────────────────
  const fetchSessions = useCallback(async () => {
    const token = localStorage.getItem('voice_os_token');
    if (!token) return;
    setIsSidebarLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const json = await res.json();
      const list: ChatSession[] = (json?.data || []).map((c: any) => ({
        id: c.session_id,
        title: c.title || 'New Conversation',
        updatedAt: c.updated_at ? new Date(c.updated_at).getTime() : Date.now(),
      }));
      setSessions(list);
    } catch {
      // silently fail — sidebar remains empty
    } finally {
      setIsSidebarLoading(false);
    }
  }, []);

  // Load session list on mount
  useEffect(() => {
    const keyId = `voice_os_session_id_${language.code}`;
    const existingId = localStorage.getItem(keyId);
    if (existingId) setSessionId(existingId);
    setAuthEmail(localStorage.getItem('voice_os_auth_email') || '');
    setAuthName(localStorage.getItem('voice_os_auth_name') || '');
    void fetchSessions();
  }, [language.code, fetchSessions]);

  const updateSessionHistory = useCallback((sid: string, title: string) => {
    setSessions(prev => {
      const existing = prev.find(s => s.id === sid);
      if (existing) {
        return prev.map(s => s.id === sid ? { ...s, title: title || s.title, updatedAt: Date.now() } : s);
      }
      return [{ id: sid, title: title || 'New Conversation', updatedAt: Date.now() }, ...prev];
    });
  }, []);

  const stopRecognition = useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.stop();
    } catch {
      // no-op
    }
    recognitionRef.current = null;
  }, []);

  /* Cancel everything on unmount */
  const cleanupRecording = useCallback(() => {
    stopRecognition();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    setLiveTranscript('');
    setProcessingText('');
    liveTranscriptRef.current = '';
  }, [stopRecognition]);

  /* Speak greeting on mount */
  useEffect(() => {
    if (!('speechSynthesis' in window)) return;
    if (hasGreetedRef.current) return;
    let cancelled = false;

    const doSpeak = (voices: SpeechSynthesisVoice[]) => {
      if (cancelled || hasGreetedRef.current) return;
      hasGreetedRef.current = true;
      speakText(
        language.greeting,
        language.code,
        voices,
        () => {
          if (!cancelled) setIsSpeaking(true);
        },
        () => {
          if (!cancelled) setIsSpeaking(false);
        },
        () => {
          if (!cancelled) setIsSpeaking(false);
        },
      );

      setChatMessages((prev) => {
        if (prev.length > 0) return prev;
        return [
          {
            id: `assistant-greeting-${Date.now()}`,
            role: 'assistant',
            text: language.greeting,
            confidenceLevel: 'high',
            fallbackUsed: false,
          },
        ];
      });
    };

    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      setTimeout(() => doSpeak(voices), 200);
    } else {
      const handler = () => {
        const updatedVoices = speechSynthesis.getVoices();
        if (updatedVoices.length > 0) {
          doSpeak(updatedVoices);
          speechSynthesis.removeEventListener('voiceschanged', handler);
        }
      };
      speechSynthesis.addEventListener('voiceschanged', handler);
      setTimeout(() => {
        if (!hasGreetedRef.current) doSpeak(speechSynthesis.getVoices());
      }, 1000);
    }

    return () => {
      cancelled = true;
      speechSynthesis.cancel();
      cleanupRecording();
    };
  }, [language, cleanupRecording]);

  const updateSessionFromResponse = useCallback(
    (nextSessionId?: string) => {
      const normalized = (nextSessionId || '').trim();
      if (!normalized) return;
      setSessionId(normalized);
      localStorage.setItem(`voice_os_session_id_${language.code}`, normalized);
    },
    [language.code],
  );

  const normalizeAssistantText = useCallback((responseText: unknown): string => {
    if (!responseText) return language.code === 'hi'
      ? 'Sorry, I could not find a suitable scheme for your request.'
      : 'Sorry, I could not find a suitable scheme for your request.';
    if (typeof responseText === 'string' && responseText.trim()) return responseText.trim();
    if (typeof responseText === 'object') {
      const payload = responseText as { confirmation?: string; explanation?: string; next_step?: string };
      const parts = [payload.confirmation, payload.explanation, payload.next_step].filter(Boolean);
      return parts.join(' ').trim() || 'Sorry, I could not find a suitable scheme for your request.';
    }
    return 'Sorry, I could not find a suitable scheme for your request.';
  }, [language.code]);

  const playAssistantAudio = useCallback((audioBase64?: string) => {
    if (!audioBase64) return;
    const src = audioBase64.startsWith('data:') ? audioBase64 : `data:audio/mp3;base64,${audioBase64}`;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
    }
    const audio = new Audio(src);
    audioRef.current = audio;
    void audio.play().catch(() => {
      // browser autoplay policy may block playback; keeping silent fallback
    });
  }, []);

  const isRapidAction = useCallback((): boolean => {
    const now = Date.now();
    if (now - lastActionAtRef.current < ACTION_DEBOUNCE_MS) {
      return true;
    }
    lastActionAtRef.current = now;
    return false;
  }, [ACTION_DEBOUNCE_MS]);

  const appendUserMessage = useCallback((text: string) => {
    const clean = text.trim();
    if (!clean) return;
    updateSessionHistory(sessionId, clean);
    setChatMessages((prev) => ([
      ...prev,
      {
        id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        role: 'user',
        text: clean,
      },
    ]));
  }, [sessionId, updateSessionHistory]);

  const appendAssistantMessage = useCallback((data: any) => {
    const payload = data?.data || data;
    const responseText = payload?.response_text;
    const assistantText = normalizeAssistantText(responseText);
    const rawConf = typeof payload?.confidence === 'number' ? payload.confidence : 0;
    const confidenceLevel = rawConf > 0.75 ? 'high' : rawConf > 0.45 ? 'medium' : 'low';
    const fallbackUsed = Boolean(payload?.fallback_used);
    
    setChatMessages((prev) => ([
      ...prev,
      {
        id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        role: 'assistant',
        text: assistantText,
        confidenceLevel,
        fallbackUsed,
      },
    ]));
    setLatestAudioBase64(payload?.audio_base64 || '');
  }, [normalizeAssistantText]);

  useEffect(() => {
    if (latestAudioBase64) {
      const src = latestAudioBase64.startsWith('data:') ? latestAudioBase64 : `data:audio/mp3;base64,${latestAudioBase64}`;
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
      const audio = new Audio(src);
      audioRef.current = audio;
      void audio.play().catch(() => {});
    }
  }, [latestAudioBase64]);

  const processWithBackend = useCallback(async (params: { text?: string; audioBlob?: Blob; liveText?: string }) => {
    if (inFlightRef.current || isProcessing) return;
    inFlightRef.current = true;
    lastRequestRef.current = params;
    setIsProcessing(true);
    setErrorMsg('');
    setProcessingText(params.liveText?.trim() || params.text?.trim() || '');

    const formData = new FormData();
    // We intentionally DO NOT send audioBlob to bypass backend STT
    // and rely completely on the frontend live transcript text.
    // if (params.audioBlob) {
    //   formData.append('audio', params.audioBlob, 'recording.webm');
    // }
    const inputText = (params.text || params.liveText || '').trim();
    if (inputText) {
      formData.append('text', inputText);
    }
    formData.append('user_id', getEffectiveUserId());
    formData.append('language', language.code);
    if (sessionId) {
      formData.append('session_id', sessionId);
    }

    // Attach JWT token if available
    const headers: Record<string, string> = {};
    const token = localStorage.getItem('voice_os_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const response = await fetch(`${BACKEND_URL}/api/process-text`, {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody?.error || `Backend error: ${response.status}`);
      }

      const data = await response.json();
      await new Promise((resolve) => setTimeout(resolve, ASSISTANT_RESPONSE_DELAY_MS));
      setErrorMsg(''); // clear any previous error
      updateSessionFromResponse(data?.data?.session_id || data?.session_id);
      appendAssistantMessage(data);
      // Refresh sidebar so new conversation appears
      void fetchSessions();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'नेटवर्क समस्या हुई';
      const isNetworkError = msg.toLowerCase().includes('failed to fetch') || msg.toLowerCase().includes('network');
      
      if (isNetworkError) {
        setErrorMsg(language.code === 'hi' ? 'नेटवर्क समस्या हुई। कृपया दोबारा कोशिश करें।' : 'Network error. Please try again.');
      } else {
        setErrorMsg(msg);
      }
      // Do NOT add a duplicate chat bubble — the inline banner is enough
    } finally {
      inFlightRef.current = false;
      setIsProcessing(false);
      setIsListening(false);
      setProcessingText('');
    }
  }, [appendAssistantMessage, ASSISTANT_RESPONSE_DELAY_MS, fetchSessions, isProcessing, language.code, sessionId, updateSessionFromResponse]);

  const handleRetry = useCallback(() => {
    if (isProcessing) return;
    if (!lastRequestRef.current) return;
    setErrorMsg('');
    void processWithBackend(lastRequestRef.current);
  }, [isProcessing, processWithBackend]);

  const sendSuggestion = useCallback((text: string) => {
    if (isProcessing || isRapidAction()) return;
    appendUserMessage(text);
    void processWithBackend({ text });
  }, [appendUserMessage, isProcessing, isRapidAction, processWithBackend]);

  const handleTextSubmit = useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const clean = typedQuery.trim();
    if (!clean || isProcessing || isListening || isRapidAction()) return;
    appendUserMessage(clean);
    setTypedQuery('');
    void processWithBackend({ text: clean });
  }, [appendUserMessage, isListening, isProcessing, isRapidAction, processWithBackend, typedQuery]);

  /** Start or stop recording */
  const handleMicClick = useCallback(async () => {
    if (isProcessing || isRapidAction()) return;

    // STOP recording
    if (isListening) {
      stopRecognition();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    // Cancel any ongoing speech synthesis or audio playback
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (audioRef.current) {
      audioRef.current.pause();
    }
    setIsSpeaking(false);
    setErrorMsg('');
    setLiveTranscript('');
    liveTranscriptRef.current = '';
    
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    // REQUEST microphone
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch {
      setErrorMsg('Microphone access denied. Please allow microphone access and try again.');
      return;
    }

    streamRef.current = stream;
    audioChunksRef.current = [];

    // Pick best supported MIME type
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mediaRecorderRef.current = recorder;

    const SpeechRecognitionCtor = getSpeechRecognitionCtor();
    if (SpeechRecognitionCtor) {
      const recognition = new SpeechRecognitionCtor();
      recognition.lang = language.code === 'en' ? 'en-IN' : `${language.code}-IN`;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (event: any) => {
        const text = Array.from(event.results || [])
          .map((result: any) => result?.[0]?.transcript ?? '')
          .join(' ')
          .trim();
        setTypedQuery(text);
        liveTranscriptRef.current = text;
        
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = window.setTimeout(() => {
          if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
          }
        }, 2000);
      };
      recognitionRef.current = recognition;
    }

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      stopRecognition();
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      const blob = new Blob(audioChunksRef.current, { type: mimeType || 'audio/webm' });
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setIsListening(false);
      
      // Auto-submit on stop
      const currentText = liveTranscriptRef.current.trim();
      if (currentText && !isProcessing) {
        appendUserMessage(currentText);
        setTypedQuery('');
        liveTranscriptRef.current = '';
        void processWithBackend({ text: currentText });
      }
    };

    recorder.start(100);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch {
        // no-op
      }
    }
    setIsListening(true);
  }, [appendUserMessage, isListening, isProcessing, isRapidAction, language.code, processWithBackend, stopRecognition]);

  const handleBack = useCallback(() => {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    cleanupRecording();
    onBack();
  }, [onBack, cleanupRecording]);

  const handleNewChat = useCallback(() => {
    const newId = `session-${Date.now()}`;
    setSessionId(newId);
    localStorage.setItem(`voice_os_session_id_${language.code}`, newId);
    setChatMessages([]);
    setTypedQuery('');
    setErrorMsg('');
  }, [language.code]);

  const handleSelectSession = useCallback(async (id: string) => {
    setSessionId(id);
    localStorage.setItem(`voice_os_session_id_${language.code}`, id);
    setChatMessages([]);
    setLiveTranscript('');
    setProcessingText('');
    setErrorMsg('');
    // Fetch history from MongoDB
    const token = localStorage.getItem('voice_os_token');
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/conversations/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const json = await res.json();
      const msgs: ChatMessage[] = (json?.data?.messages || []).map((m: any, i: number) => ({
        id: `loaded-${i}-${m.timestamp}`,
        role: m.role as 'user' | 'assistant',
        text: m.text,
        confidenceLevel: 'low' as const,
        fallbackUsed: false,
      }));
      setChatMessages(msgs);
    } catch {
      // silently fail — empty chat is fine
    }
  }, [language.code]);

  const handleDeleteSession = useCallback(async (id: string) => {
    const token = localStorage.getItem('voice_os_token');
    if (!token) return;
    try {
      await fetch(`${BACKEND_URL}/api/conversations/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessions(prev => prev.filter(s => s.id !== id));
      if (sessionId === id) handleNewChat();
    } catch {
      // silently fail
    }
  }, [sessionId, handleNewChat]);

  return (
    <div className="flex h-screen bg-black overflow-hidden relative">
      <Sidebar 
        sessions={sessions}
        currentSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        isLoading={isSidebarLoading}
        authEmail={authEmail}
        authName={authName}
      />

      <div className="flex-1 flex flex-col relative w-full max-w-5xl mx-auto">
        <div className="flex items-center justify-between px-4 py-3 md:py-4 border-b border-[#1f1f1f]">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setIsSidebarOpen(true)}
              className="md:hidden text-[#9ca3af] hover:text-white"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                <path fillRule="evenodd" d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5z"/>
              </svg>
            </button>
            <BackButton onClick={handleBack} label={backLabel} />
          </div>
          <div
            className="flex items-center gap-2 px-3 py-1 rounded-full border bg-[#111111] font-body text-xs font-medium"
            style={{ borderColor: `${accent}40`, color: accent }}
          >
            {language.nativeName}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto chat-scrollbar px-4 py-6">
          <div className="flex flex-col gap-6 mx-auto w-full max-w-3xl">
            {chatMessages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {isProcessing && <TypingIndicator />}
            {errorMsg && (
              <div className="self-start max-w-[85%] md:max-w-[70%] rounded-2xl bg-rose-500/10 border border-rose-500/30 px-4 py-3 text-rose-200">
                {errorMsg}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* ── Centered Large Mic Button + Live Transcript ── */}
        <div className="flex flex-col items-center justify-center py-4 gap-4">
          {/* Mic button with ripple rings */}
          <div className="relative flex items-center justify-center">
            {isListening && (
              <>
                <span className="absolute inline-flex h-24 w-24 rounded-full bg-[#f59e0b]/20 animate-ping" />
                <span className="absolute inline-flex h-32 w-32 rounded-full bg-[#f59e0b]/10 animate-ping" style={{ animationDelay: '0.2s' }} />
              </>
            )}
            <button
              type="button"
              onClick={handleMicClick}
              disabled={isProcessing}
              className={`relative z-10 w-20 h-20 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 ${
                isListening
                  ? 'bg-[#f59e0b] text-black scale-110 shadow-[0_0_40px_rgba(245,158,11,0.5)]'
                  : isProcessing
                    ? 'bg-[#14b8a6]/20 text-[#14b8a6] cursor-not-allowed'
                    : 'bg-[#1f1f1f] text-[#9ca3af] hover:bg-[#2a2a2a] hover:text-white hover:scale-105 border border-[#3a3a3a]'
              }`}
            >
              {isListening ? (
                /* Stop / Square icon when active */
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 16 16">
                  <path d="M5 3.5h6A1.5 1.5 0 0 1 12.5 5v6a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 11V5A1.5 1.5 0 0 1 5 3.5z"/>
                </svg>
              ) : isProcessing ? (
                /* Spinner when processing */
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 16 16" className="animate-spin">
                  <path d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
                  <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
                </svg>
              ) : (
                /* Mic icon */
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 16 16">
                  <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/>
                  <path d="M10 8a2 2 0 1 1-4 0V3a2 2 0 1 1 4 0v5zM8 0a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V3a3 3 0 0 0-3-3z"/>
                </svg>
              )}
            </button>
          </div>

          {/* Status label */}
          <p className={`text-sm font-medium transition-colors ${
            isListening ? 'text-[#f59e0b]' : isProcessing ? 'text-[#14b8a6]' : 'text-[#6b7280]'
          }`}>
            {isListening
              ? (language.code === 'hi' ? '🎤 सुन रहा है... (रोकने के लिए क्लिक करें)' : '🎤 Listening... (click to stop)')
              : isProcessing
                ? (language.code === 'hi' ? '⏳ प्रोसेस हो रहा है...' : '⏳ Processing...')
                : (language.code === 'hi' ? 'बोलने के लिए क्लिक करें' : 'Click to speak')}
          </p>

          {/* Live transcript display */}
          {isListening && typedQuery && (
            <div className="mx-auto max-w-lg w-full px-4">
              <div className="bg-[#1a1400] border border-[#f59e0b]/30 rounded-2xl px-5 py-3 text-center">
                <p className="text-[#f5e0a0] text-sm md:text-base leading-relaxed">{typedQuery}</p>
              </div>
            </div>
          )}
        </div>

        <div className="px-4 pb-6 w-full max-w-3xl mx-auto">
          <div className="mb-2">
            <SuggestionChips onSelect={sendSuggestion} disabled={isProcessing || isListening} />
          </div>

          <form onSubmit={handleTextSubmit} className="relative">
            {/* Loading / Listening States */}
            {(isListening || isProcessing) && (
              <div className="absolute -top-8 left-4 flex items-center gap-2 text-xs font-medium">
                {isListening && (
                  <span className="text-[#f59e0b] animate-pulse">
                    {language.code === 'hi' ? '🎤 सुन रहा है...' : '🎤 Listening...'}
                  </span>
                )}
                {isProcessing && (
                  <span className="text-[#14b8a6] animate-pulse">
                    {language.code === 'hi' ? '⏳ प्रोसेस हो रहा है...' : '⏳ Processing your request...'}
                  </span>
                )}
              </div>
            )}

            <div className={`flex flex-row items-end gap-2 rounded-2xl border ${isListening ? 'border-[#f59e0b] ring-1 ring-[#f59e0b]/20 bg-[#1a1400]' : 'border-[#2a2a2a] bg-[#171717]'} px-3 py-3 shadow-sm transition-all`}>
              <button 
                type="button" 
                onClick={handleMicClick}
                disabled={isProcessing}
                className={`p-2 shrink-0 rounded-full transition-colors ${isListening ? 'text-[#f59e0b] bg-[#f59e0b]/20' : 'text-[#9ca3af] hover:text-white hover:bg-[#2a2a2a] disabled:opacity-50'}`}
              >
                {isListening ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M5.5 6.5A.5.5 0 0 1 6 6h4a.5.5 0 0 1 0 1H6a.5.5 0 0 1-.5-.5z"/>
                    <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/>
                    <path d="M10 8a2 2 0 1 1-4 0V3a2 2 0 1 1 4 0v5zM8 0a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V3a3 3 0 0 0-3-3z"/>
                  </svg>
                )}
              </button>
              
              <textarea
                value={typedQuery}
                onChange={(e) => {
                  setTypedQuery(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleTextSubmit(e as any);
                  }
                }}
                placeholder={inputPlaceholder}
                disabled={isProcessing}
                rows={1}
                className="flex-1 max-h-[120px] min-h-[24px] bg-transparent text-sm md:text-base text-[#e5e7eb] placeholder:text-[#6b7280] outline-none resize-none py-1.5"
                style={{ overflowY: typedQuery.split('\n').length > 3 ? 'auto' : 'hidden' }}
              />

              <button
                type="submit"
                disabled={isProcessing || !typedQuery.trim()}
                className="p-2 shrink-0 rounded-full bg-[#f59e0b] text-black transition-opacity disabled:opacity-50 hover:bg-[#d97706]"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                  <path fillRule="evenodd" d="M15.854.146a.5.5 0 0 1 .11.54l-5.819 14.547a.75.75 0 0 1-1.329.124l-3.178-4.995L.643 7.184a.75.75 0 0 1 .124-1.33L15.314.037a.5.5 0 0 1 .54.11ZM6.636 10.07l2.761 4.338L14.13 2.576 6.636 10.07Zm6.787-8.201L1.591 6.602l4.339 2.76 7.494-7.493Z"/>
                </svg>
              </button>
            </div>
            <div className="text-center mt-2">
               <p className="text-xs text-[#6b7280]">Voice OS can make mistakes. Check important info.</p>
            </div>
          </form>
        </div>

      </div>
    </div>
  );
};

export default VoiceInteraction;
