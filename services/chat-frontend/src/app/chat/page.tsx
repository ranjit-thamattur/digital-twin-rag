'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Brain, User, Plus, Settings, MessageSquare, Paperclip, Loader2, Trash2, Menu, X, LogOut, Sun, Moon, Monitor, Download, AlertTriangle, Upload, Mic, Check, Link as LinkIcon } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';

type MemoryItem = {
  id: number;
  filename: string;
  snippet?: string;
};

type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  memoryUsed?: MemoryItem[];
};

type Session = {
  sessionId: string;
  title: string;
  sessionSk?: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetchingHistory, setIsFetchingHistory] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [userEmail, setUserEmail] = useState<string>('Loading...');

  // Settings State
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light' | 'system'>('system');
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [activeMemoryMessageIndex, setActiveMemoryMessageIndex] = useState<number | null>(null);
  
  // Connectors State
  const [isGoogleDriveConnected, setIsGoogleDriveConnected] = useState(false);
  const [isConnectingDrive, setIsConnectingDrive] = useState(false);

  // Upload Modal State
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadAsCommon, setUploadAsCommon] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Voice Mode State
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [voiceState, setVoiceState] = useState<'listening' | 'thinking' | 'speaking'>('listening');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [voiceLang, setVoiceLang] = useState('en-US'); // User STT language
  const [detectedLang, setDetectedLang] = useState('en-US');
  const recognitionRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isSwitchingLanguageRef = useRef(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check URL params for successful Google Drive connection
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('gdrive_connected') === 'true') {
        setIsGoogleDriveConnected(true);
        // Optionally open settings automatically to show success
        setIsSettingsOpen(true);
        // Clean up URL
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }
  }, []);

  // Fetch recent sessions on load
  useEffect(() => {
    fetchSessions();
    fetchUser();

    // Load saved theme
    const savedTheme = localStorage.getItem('theme') as 'dark' | 'light' | 'system' || 'system';
    setTheme(savedTheme);
    applyTheme(savedTheme);
  }, []);

  const applyTheme = (t: 'dark' | 'light' | 'system') => {
    if (t === 'dark') {
      document.documentElement.removeAttribute('data-theme');
    } else if (t === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      // System
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
    }
  };

  const handleThemeChange = (newTheme: 'dark' | 'light' | 'system') => {
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    applyTheme(newTheme);
  };

  const fetchUser = async () => {
    try {
      const res = await fetch('/api/auth/me', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setUserEmail(data.email);
      }
    } catch (e) {
      setUserEmail('Unknown');
    }
  };

  const fetchSessions = async (selectFirst: boolean = true) => {
    try {
      const res = await fetch('/api/history/sessions', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);

        if (selectFirst && data.sessions && data.sessions.length > 0) {
          loadSession(data.sessions[0].sessionId);
        } else if (selectFirst) {
          startNewChat();
        }
      }
    } catch (e) {
      console.error('Failed to fetch sessions', e);
      startNewChat();
    }
  };

  const loadSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setIsFetchingHistory(true);
    try {
      const res = await fetch(`/api/history?sessionId=${sessionId}`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (e) {
      console.error('Failed to load session messages', e);
    } finally {
      setIsFetchingHistory(false);
      setIsMobileSidebarOpen(false); // Close sidebar on mobile after selecting
    }
  };

  const startNewChat = () => {
    setCurrentSessionId(uuidv4());
    setMessages([]);
    setIsFetchingHistory(false);
    setIsMobileSidebarOpen(false);
  };

  const saveToHistory = async (role: string, content: string, isFirst: boolean = false) => {
    try {
      await fetch('/api/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId: currentSessionId,
          role,
          content,
          isFirstMessage: isFirst
        })
      });
      if (isFirst) {
        // Refresh sidebar after first message
        setTimeout(() => fetchSessions(false), 500);
      }
    } catch (e) {
      console.error('Failed to save to history', e);
    }
  };

  const deleteSession = async (sessionId: string, sessionSk?: string) => {
    if (!confirm('Are you sure you want to delete this chat?')) return;

    try {
      let url = `/api/history?sessionId=${sessionId}`;
      if (sessionSk) url += `&sessionSk=${sessionSk}`;

      await fetch(url, { method: 'DELETE' });

      // Remove from UI
      setSessions(prev => prev.filter(s => s.sessionId !== sessionId));
      if (currentSessionId === sessionId) {
        startNewChat();
      }
    } catch (e) {
      console.error('Failed to delete session', e);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isUploading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setInput('');
    const isFirstMessage = messages.length === 0;

    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    // Fire and forget save
    saveToHistory('user', userMsg, isFirstMessage);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          messages: messages.filter(m => m.role !== 'system')
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.answer, memoryUsed: data.memoryUsed }]);
        saveToHistory('assistant', data.answer, false);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.error}` }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Connection failed. Please try again.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  // --- Voice Mode Logic ---
  const startListening = () => {
    setVoiceState('listening');
    setLiveTranscript('');

    // @ts-ignore - webkitSpeechRecognition is not standard TS
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in your browser. Please try Chrome or Edge.");
      endVoiceMode();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = voiceLang; // Use the selected language

    recognition.onresult = (event: any) => {
      let final = '';
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          final += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      setLiveTranscript(final || interim);
    };

    recognition.onend = () => {
      // Need a way to read the latest liveTranscript state here
      // But it's captured in closure, so we just use a small hack or rely on useEffect if it was complex
      // For simplicity, we just use the final text
    };

    recognition.onerror = (e: any) => {
      console.error("Speech recognition error:", e.error);
      if (e.error === 'no-speech' && document.querySelector('.voice-overlay')) {
        try { recognition.start(); } catch (err) { }
      } else if (e.error === 'aborted') {
        // Ignored. This happens intentionally when we stop() it to change the language.
        // It will be restarted by the dropdown onChange handler.
      } else {
        // Instead of instantly closing the window, show the error so the user can see it
        setLiveTranscript(`STT Error: ${e.error}. Please try again.`);
        setVoiceState('listening');
        // We do NOT call endVoiceMode() here anymore to prevent the window from unexpectedly crashing.
        // We will attempt to restart it after 2 seconds so the user can read the error.
        setTimeout(() => {
          try { recognition.start(); } catch (err) { }
        }, 2000);
      }
    };

    // Fix closure issue with onend
    const origOnEnd = recognition.onend;
    recognition.onend = () => {
      if (isSwitchingLanguageRef.current) {
        isSwitchingLanguageRef.current = false;
        try { recognition.start(); } catch (e) { }
        return;
      }

      // We read the DOM element if we can't get the state directly in closure
      const transcriptDiv = document.querySelector('.voice-transcript');
      const text = transcriptDiv?.textContent || '';

      if (text.trim() && text !== '...') {
        handleVoiceSubmit(text.trim());
      } else {
        if (document.querySelector('.voice-overlay') && document.querySelector('.voice-orb.listening')) {
          try { recognition.start(); } catch (e) { }
        }
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (e) {
      console.error(e);
    }
  };

  const handleVoiceSubmit = async (transcript: string) => {
    setVoiceState('thinking');

    const isFirstMessage = messages.length === 0;
    setMessages(prev => [...prev, { role: 'user', content: transcript }]);
    saveToHistory('user', transcript, isFirstMessage);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: transcript,
          messages: messages.filter(m => m.role !== 'system')
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.answer, memoryUsed: data.memoryUsed }]);
        saveToHistory('assistant', data.answer, false);
        await speakResponse(data.answer, transcript);
      } else {
        await speakResponse("I'm sorry, I encountered an error.", transcript);
      }
    } catch (err) {
      await speakResponse("Connection failed. Please try again.", transcript);
    }
  };

  const speakResponse = async (text: string, originalTranscript: string) => {
    setVoiceState('speaking');
    try {
      // Check if we should skip audio playback for specific languages
      if (voiceLang === 'ta-IN' || voiceLang === 'ml-IN') {
        // Skip audio, just transition state and restart listening after a short delay
        setTimeout(() => {
          if (document.querySelector('.voice-overlay')) {
            startListening();
          }
        }, 1500); // 1.5s delay to simulate reading time
        return;
      }

      // 1. Clean the text for speaking (remove semantic cache label and emojis)
      let spokenText = text.replace(/\(Source: Semantic Cache.*?\)/g, '');
      // Strip common emojis and symbols that choke TTS engines or falsely trigger language detection
      spokenText = spokenText.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '');
      spokenText = spokenText.trim();

      if (!spokenText) {
        spokenText = "Okay."; // Fallback if the response was purely emojis
      }

      // 2. Check the ACTUAL script of the response text
      const textHasDevanagari = /[\u0900-\u097F]/.test(spokenText);
      // If the user selected Hindi OR the text contains Devanagari, use Kajal.
      const useKajal = textHasDevanagari || voiceLang === 'hi-IN';
      const langToPass = useKajal ? 'hi-IN' : 'en-US';

      const res = await fetch('/api/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: spokenText, lang: langToPass })
      });

      if (!res.ok) throw new Error('TTS Failed');

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      if (!audioRef.current) {
        audioRef.current = new Audio();
      }

      audioRef.current.src = url;
      audioRef.current.onended = () => {
        if (document.querySelector('.voice-overlay')) {
          startListening();
        }
      };

      audioRef.current.play().catch(e => {
        console.error("Audio playback failed", e);
        if (document.querySelector('.voice-overlay')) {
          startListening();
        }
      });
    } catch (e) {
      console.error("TTS playback error:", e);
      if (document.querySelector('.voice-overlay')) {
        startListening();
      }
    }
  };

  const handleConnectDrive = () => {
    setIsConnectingDrive(true);
    // Redirect browser to our actual backend OAuth initiate route
    window.location.href = '/api/auth/google-drive';
  };

  const handleDisconnectDrive = async () => {
    if (!confirm('Are you sure you want to disconnect Google Drive? Real-time syncing will stop.')) return;
    try {
      const res = await fetch('/api/auth/google-drive/disconnect', { method: 'DELETE' });
      if (res.ok) {
        setIsGoogleDriveConnected(false);
      } else {
        alert('Failed to disconnect. Please try again.');
      }
    } catch (e) {
      alert('Network error. Please try again.');
    }
  };

  const endVoiceMode = () => {
    setIsVoiceMode(false);
    setVoiceState('listening');
    setLiveTranscript('');
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    if (audioRef.current) {
      audioRef.current.pause();
    }
  };

  // -------------------------

  const exportChat = (format: 'txt' | 'csv') => {
    if (messages.length === 0) return;

    let content = '';
    const filename = `digital-brain-chat-${new Date().toISOString().split('T')[0]}.${format}`;

    if (format === 'txt') {
      content = messages.map(m => `[${m.role.toUpperCase()}]\n${m.content}\n`).join('\n');
    } else if (format === 'csv') {
      content = 'Role,Message\n' + messages.map(m => `"${m.role}","${m.content.replace(/"/g, '""')}"`).join('\n');
    }

    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const exportPDF = () => {
    // A clean and simple way to export to PDF without heavy dependencies
    // is to trigger the browser print dialog while using CSS media queries to hide sidebars.
    setIsSettingsOpen(false);
    setTimeout(() => {
      window.print();
    }, 300);
  };

  const clearAllHistory = async () => {
    if (!confirm('DANGER: Are you sure you want to completely wipe your entire chat history? This cannot be undone.')) return;

    setIsClearingHistory(true);
    try {
      const res = await fetch('/api/history/clear-all', { method: 'DELETE' });
      if (res.ok) {
        setSessions([]);
        setMessages([]);
        setCurrentSessionId(uuidv4());
        setIsSettingsOpen(false);
      } else {
        alert('Failed to clear history. Please try again.');
      }
    } catch (e) {
      alert('Connection error while clearing history.');
    } finally {
      setIsClearingHistory(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    // Modal is already open
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const confirmUpload = async () => {
    if (!selectedFile) return;

    setIsUploadModalOpen(false);
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('isCommon', String(uploadAsCommon));

      const response = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await response.json();

      if (response.ok) {
        setMessages(prev => [...prev, { role: 'system', content: `✅ File "${selectedFile.name}" uploaded successfully ${uploadAsCommon ? '(Shared with entire company)' : '(Private)'}. Digital Brain is currently processing it into your knowledge base.` }]);
      } else {
        setMessages(prev => [...prev, { role: 'system', content: `❌ Failed to upload "${selectedFile.name}": ${data.error}` }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'system', content: `❌ Connection error while uploading "${selectedFile.name}".` }]);
    } finally {
      setIsUploading(false);
      setSelectedFile(null);
      setUploadAsCommon(false); // Reset
    }
  };

  return (
    <div className="app-container">
      {/* Settings Modal */}
      {isSettingsOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100dvh', backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: '90%', maxWidth: '500px', backgroundColor: 'var(--bg-sidebar)', borderRadius: '12px', padding: '24px', border: '1px solid var(--border-light)', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Settings</h2>
              <X size={20} style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setIsSettingsOpen(false)} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

              {/* Theme Toggle */}
              <div>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Theme</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button onClick={() => handleThemeChange('system')} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: `1px solid ${theme === 'system' ? 'var(--accent-primary)' : 'var(--border-light)'}`, backgroundColor: theme === 'system' ? 'rgba(139, 92, 246, 0.1)' : 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                    <Monitor size={16} /> System
                  </button>
                  <button onClick={() => handleThemeChange('light')} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: `1px solid ${theme === 'light' ? 'var(--accent-primary)' : 'var(--border-light)'}`, backgroundColor: theme === 'light' ? 'rgba(139, 92, 246, 0.1)' : 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                    <Sun size={16} /> Light
                  </button>
                  <button onClick={() => handleThemeChange('dark')} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: `1px solid ${theme === 'dark' ? 'var(--accent-primary)' : 'var(--border-light)'}`, backgroundColor: theme === 'dark' ? 'rgba(139, 92, 246, 0.1)' : 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                    <Moon size={16} /> Dark
                  </button>
                </div>
              </div>

              {/* Export Data */}
              <div>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Export Current Chat</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button onClick={() => exportChat('txt')} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: '1px solid var(--border-light)', backgroundColor: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }} disabled={messages.length === 0}>
                    <Download size={16} /> TXT
                  </button>
                  <button onClick={() => exportChat('csv')} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: '1px solid var(--border-light)', backgroundColor: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }} disabled={messages.length === 0}>
                    <Download size={16} /> CSV
                  </button>
                  <button onClick={exportPDF} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: '1px solid var(--border-light)', backgroundColor: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }} disabled={messages.length === 0}>
                    <Download size={16} /> PDF
                  </button>
                </div>
              </div>

              {/* Connectors */}
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '24px' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Connectors</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px', border: '1px solid var(--border-light)', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '40px', height: '40px', borderRadius: '8px', backgroundColor: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {/* Fake Google Drive Icon */}
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M8.59003 4.23001L4.27002 11.75C4.05002 12.13 4.05002 12.6 4.27002 12.98L8.60004 20.48C8.82004 20.86 9.23004 21.1 9.67004 21.1H18.33C18.77 21.1 19.18 20.86 19.4 20.48L23.73 12.98C23.95 12.6 23.95 12.13 23.73 11.75L19.4 4.24C19.18 3.86 18.77 3.62001 18.33 3.62001H9.67004C9.23004 3.61001 8.81003 3.85001 8.59003 4.23001Z" fill="#FFC107"/>
                          <path d="M12.44 14.86H4.27002C4.05002 14.86 3.84 14.98 3.73 15.17C3.62 15.36 3.62 15.59 3.73 15.78L8.06 23.28C8.28 23.66 8.69001 23.9 9.13001 23.9H17.8L12.44 14.86Z" fill="#1976D2"/>
                          <path d="M11.66 4.88001C11.44 4.5 11.03 4.26001 10.59 4.26001H1.92001C1.70001 4.26001 1.49001 4.38001 1.38001 4.57001C1.27001 4.76001 1.27001 4.99001 1.38001 5.18001L5.70001 12.68L11.66 4.88001Z" fill="#4CAF50"/>
                        </svg>
                      </div>
                      <div>
                        <h4 style={{ fontSize: '1rem', fontWeight: 500, margin: 0, color: 'var(--text-primary)' }}>Google Drive</h4>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>Sync policies & documents real-time</p>
                      </div>
                    </div>
                    
                    {isGoogleDriveConnected ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#10b981', fontSize: '0.85rem', fontWeight: 500 }}>
                          <Check size={16} /> Connected (Syncing real-time)
                        </div>
                        <button
                          onClick={handleDisconnectDrive}
                          style={{ padding: '6px 12px', borderRadius: '6px', backgroundColor: 'transparent', color: '#ff4d4f', border: '1px solid #ff4d4f', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 500 }}
                        >
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button 
                        onClick={handleConnectDrive}
                        disabled={isConnectingDrive}
                        style={{ padding: '8px 16px', borderRadius: '6px', backgroundColor: 'var(--accent-primary)', color: 'white', border: 'none', cursor: isConnectingDrive ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        {isConnectingDrive ? <Loader2 size={14} className="animate-spin" /> : <LinkIcon size={14} />}
                        {isConnectingDrive ? 'Connecting...' : 'Connect'}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Danger Zone */}
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '24px' }}>
                <h3 style={{ fontSize: '0.9rem', color: '#ff4d4f', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <AlertTriangle size={16} /> Danger Zone
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                  Permanently delete all of your chat history. This action cannot be undone.
                </p>
                <button
                  onClick={clearAllHistory}
                  disabled={isClearingHistory}
                  style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid #ff4d4f', backgroundColor: 'rgba(255, 77, 79, 0.1)', color: '#ff4d4f', cursor: isClearingHistory ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', fontWeight: 500 }}
                >
                  {isClearingHistory ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  {isClearingHistory ? 'Deleting...' : 'Clear All History'}
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {isUploadModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100dvh', backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(5px)' }}>
          <div style={{ width: '90%', maxWidth: '400px', backgroundColor: 'var(--bg-sidebar)', borderRadius: '16px', padding: '24px', border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Upload size={20} color="var(--accent-primary)" /> Upload Document
              </h2>
              <X size={20} style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setIsUploadModalOpen(false)} />
            </div>

            <div
              style={{ border: '2px dashed var(--border-light)', borderRadius: '12px', padding: '32px 16px', textAlign: 'center', marginBottom: '20px', backgroundColor: 'rgba(255,255,255,0.02)', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}
            >
              <div style={{ marginBottom: '12px', color: 'var(--text-primary)', fontWeight: 500, fontSize: '1.1rem', wordBreak: 'break-all' }}>
                {selectedFile?.name || 'Click here to browse your computer'}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                {selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB` : 'PDF, TXT, DOCX, PPTX, CSV, XLSX'}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', padding: '12px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
              <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Share with entire company</span>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', position: 'relative' }}>
                <input
                  type="checkbox"
                  checked={uploadAsCommon}
                  onChange={(e) => setUploadAsCommon(e.target.checked)}
                  style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
                />
                <div style={{ width: '40px', height: '24px', backgroundColor: uploadAsCommon ? 'var(--accent-primary)' : 'var(--border-light)', borderRadius: '12px', transition: 'background-color 0.2s', position: 'relative' }}>
                  <div style={{ position: 'absolute', top: '2px', left: uploadAsCommon ? '18px' : '2px', width: '20px', height: '20px', backgroundColor: '#fff', borderRadius: '50%', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }} />
                </div>
              </label>
            </div>

            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: '1.4' }}>
              {uploadAsCommon
                ? 'Everyone in the company will be able to query information from this document.'
                : 'Only you will be able to query information from this document.'}
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setIsUploadModalOpen(false)} style={{ flex: 1, padding: '12px', borderRadius: '8px', border: '1px solid var(--border-light)', backgroundColor: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 500 }}>
                Cancel
              </button>
              <button onClick={confirmUpload} style={{ flex: 1, padding: '12px', borderRadius: '8px', border: 'none', backgroundColor: 'var(--accent-primary)', color: 'white', cursor: 'pointer', fontWeight: 500, boxShadow: '0 4px 12px rgba(139, 92, 246, 0.3)' }}>
                Upload File
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mobile Overlay */}
      {isMobileSidebarOpen && (
        <div className="mobile-overlay" onClick={() => setIsMobileSidebarOpen(false)}></div>
      )}

      {/* Sidebar */}
      <div className={`sidebar ${isMobileSidebarOpen ? 'open' : ''}`}>
        <div className="brand" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="brand-icon">
              <Brain size={20} />
            </div>
            <span>Digital Brain</span>
          </div>
          <X
            size={24}
            className="mobile-close-icon"
            onClick={() => setIsMobileSidebarOpen(false)}
            style={{ cursor: 'pointer' }}
          />
        </div>

        <button className="new-chat-btn" onClick={startNewChat}>
          <Plus size={18} /> New Chat
        </button>

        <div className="chat-history">
          <div className="history-title">Recent Chats</div>
          {sessions.map(session => (
            <div
              key={session.sessionId}
              className={`history-item ${currentSessionId === session.sessionId ? 'active' : ''}`}
              onClick={() => loadSession(session.sessionId)}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <MessageSquare size={14} style={{ marginRight: '8px', minWidth: '14px' }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{session.title}</span>
              </div>
              <Trash2
                size={14}
                className="delete-icon"
                onClick={(e) => { e.stopPropagation(); deleteSession(session.sessionId, session.sessionSk); }}
              />
            </div>
          ))}
          {sessions.length === 0 && !isFetchingHistory && (
            <div style={{ padding: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>No recent chats.</div>
          )}
        </div>

        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid var(--border-light)', display: 'flex', flexDirection: 'column', gap: '16px' }}>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className="avatar" style={{ width: '32px', height: '32px', backgroundColor: 'var(--accent-primary)' }}>
              <User size={16} color="white" />
            </div>
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
              {userEmail}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div
              style={{ display: 'flex', gap: '10px', color: 'var(--text-secondary)', cursor: 'pointer', alignItems: 'center' }}
              onClick={() => setIsSettingsOpen(true)}
            >
              <Settings size={16} />
              <span style={{ fontSize: '0.9rem' }}>Settings</span>
            </div>

            <a
              href="/api/auth/logout"
              style={{ display: 'flex', gap: '6px', color: '#ff4d4f', cursor: 'pointer', alignItems: 'center', textDecoration: 'none' }}
            >
              <LogOut size={16} />
              <span style={{ fontSize: '0.9rem' }}>Logout</span>
            </a>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="main-chat">
        <div className="header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Menu
              size={24}
              className="mobile-menu-icon"
              onClick={() => setIsMobileSidebarOpen(true)}
              style={{ cursor: 'pointer' }}
            />
            <div>Your Digital Twin</div>
          </div>
        </div>

        <div className="messages-container">
          {isFetchingHistory ? (
            <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Loader2 size={32} className="animate-spin" style={{ margin: '0 auto 16px', opacity: 0.5 }} />
              <p>Loading conversation...</p>
            </div>
          ) : messages.length === 0 ? (
            <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Brain size={48} style={{ margin: '0 auto 16px', opacity: 0.5 }} />
              <h2>How can I help you today?</h2>
              <p style={{ marginTop: '8px' }}>Ask me about documents, metrics, or company knowledge.</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className={`message-row ${msg.role}`}>
                {msg.role !== 'system' && (
                  <div className={`avatar ${msg.role === 'assistant' ? 'ai' : ''}`}>
                    {msg.role === 'user' ? <User size={18} /> : <Brain size={18} color="white" />}
                  </div>
                )}
                <div className="message-content" style={msg.role === 'system' ? { width: '100%', alignItems: 'center' } : undefined}>
                  <div className="bubble" style={msg.role === 'system' ? { backgroundColor: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '8px 16px' } : undefined}>
                    {msg.content}
                  </div>
                  {msg.role === 'assistant' && msg.memoryUsed && msg.memoryUsed.length > 0 && (
                    <div
                      onClick={() => setActiveMemoryMessageIndex(activeMemoryMessageIndex === i ? null : i)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px',
                        fontSize: '0.75rem', color: 'var(--accent-primary)', cursor: 'pointer',
                        padding: '4px 8px', borderRadius: '4px', backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        width: 'fit-content', opacity: 0.8, transition: 'opacity 0.2s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                      onMouseLeave={(e) => e.currentTarget.style.opacity = '0.8'}
                    >
                      <Brain size={12} />
                      {activeMemoryMessageIndex === i ? "Hide Brain State" : "View Brain State"}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {isLoading && (
            <div className="message-row ai">
              <div className="avatar ai">
                <Brain size={18} color="white" />
              </div>
              <div className="message-content">
                <div className="bubble" style={{ display: 'flex', alignItems: 'center' }}>
                  <div className="loading-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {isUploading && (
            <div className="message-row system" style={{ justifyContent: 'center' }}>
              <div className="bubble" style={{ backgroundColor: 'transparent', color: 'var(--text-secondary)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Loader2 size={14} className="animate-spin" /> Uploading document to S3...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="input-container">
          <form onSubmit={handleSubmit} className="input-box">
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileSelect}
              accept=".pdf,.txt,.docx,.pptx,.csv,.xlsx,.xls"
            />
            <Paperclip
              size={20}
              color="var(--text-secondary)"
              style={{ marginRight: '12px', cursor: 'pointer' }}
              onClick={() => setIsUploadModalOpen(true)}
            />
            <button
              type="button"
              className="voice-feature-btn"
              onClick={() => {
                setIsVoiceMode(true);

                // Safari Auto-play workaround: Bless the audio contexts during the trusted click event
                if (!audioRef.current) {
                  audioRef.current = new Audio();
                }
                audioRef.current.play().catch(() => { });
                audioRef.current.pause();

                if (window.speechSynthesis) {
                  const unlock = new SpeechSynthesisUtterance('');
                  window.speechSynthesis.speak(unlock);
                }

                startListening();
              }}
            >
              <Mic size={16} />
              Voice
            </button>
            <input
              type="text"
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Digital Brain..."
              disabled={isLoading || isUploading || isFetchingHistory}
            />
            <button type="submit" className="send-btn" disabled={!input.trim() || isLoading || isUploading || isFetchingHistory}>
              <Send size={16} />
            </button>
          </form>
          <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '12px' }}>
            Digital Brain can make mistakes. Check important information.
          </div>
        </div>
      </div>

      {/* Voice Mode Overlay */}
      {isVoiceMode && (
        <div className="voice-overlay">

          <div style={{ position: 'absolute', top: '24px', right: '24px', zIndex: 210 }}>
            <select
              value={voiceLang}
              onChange={(e) => {
                setVoiceLang(e.target.value);
                if (recognitionRef.current) {
                  recognitionRef.current.lang = e.target.value;
                  // If it's currently listening, we need to restart it for the new language to take effect immediately
                  if (voiceState === 'listening') {
                    isSwitchingLanguageRef.current = true;
                    try {
                      recognitionRef.current.stop();
                    } catch (err) { }
                  }
                }
              }}
              style={{
                background: 'rgba(255,255,255,0.1)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.3)',
                padding: '8px 12px',
                borderRadius: '8px',
                outline: 'none',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="en-US">🇺🇸 English</option>
              <option value="hi-IN">🇮🇳 Hindi (हिंदी)</option>
              <option value="ml-IN">🇮🇳 Malayalam (മലയാളം)</option>
              <option value="ta-IN">🇮🇳 Tamil (தமிழ்)</option>
              <option value="ar-SA">🇸🇦 Arabic (العربية)</option>
            </select>
          </div>

          <div className={`voice-orb ${voiceState}`} />

          <div className="voice-status">
            {voiceState === 'listening' && 'Listening...'}
            {voiceState === 'thinking' && 'Thinking...'}
            {voiceState === 'speaking' && 'Speaking...'}
          </div>

          <div className="voice-transcript">{liveTranscript || '...'}</div>

          <button className="voice-end-btn" onClick={endVoiceMode}>
            End Conversation
          </button>
        </div>
      )}

      {/* Hidden Memory Side Panel / Bottom Sheet */}
      {activeMemoryMessageIndex !== null && messages[activeMemoryMessageIndex]?.memoryUsed && (
        <div className="memory-panel-overlay" style={{
          position: 'fixed', top: 0, right: 0, width: '100%', height: '100dvh',
          pointerEvents: 'none', zIndex: 50, display: 'flex', justifyContent: 'flex-end'
        }}>
          {/* Mobile backdrop */}
          <div
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', backgroundColor: 'rgba(0,0,0,0.4)', pointerEvents: 'auto' }}
            className="mobile-only"
            onClick={() => setActiveMemoryMessageIndex(null)}
          />

          <div className="memory-panel" style={{
            width: '100%', maxWidth: '400px', backgroundColor: 'var(--bg-sidebar)',
            borderLeft: '1px solid var(--border-light)', pointerEvents: 'auto',
            display: 'flex', flexDirection: 'column', height: '100%',
            boxShadow: '-10px 0 25px rgba(0,0,0,0.2)', transition: 'transform 0.3s ease',
            zIndex: 51
          }}>
            <div style={{ padding: '20px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Brain size={18} color="var(--accent-primary)" /> Brain Memory
              </h3>
              <X size={20} style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setActiveMemoryMessageIndex(null)} />
            </div>
            <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                Documents accessed to generate this response:
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {messages[activeMemoryMessageIndex].memoryUsed!.map((mem, idx) => (
                  <div key={idx} style={{ padding: '12px', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px', wordBreak: 'break-word' }}>
                      <Paperclip size={14} style={{ flexShrink: 0 }} /> {mem.filename}
                    </div>
                    {mem.snippet && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: '1.5', fontStyle: 'italic', paddingLeft: '8px', borderLeft: '2px solid var(--border-light)' }}>
                        "{mem.snippet}"
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* CSS for responsiveness inline */}
          <style dangerouslySetInnerHTML={{
            __html: `
            @media (max-width: 768px) {
              .memory-panel {
                position: absolute;
                bottom: 0;
                top: auto;
                height: 60vh;
                max-width: 100%;
                border-left: none;
                border-top: 1px solid var(--border-light);
                border-radius: 16px 16px 0 0;
              }
            }
            @media (min-width: 769px) {
              .mobile-only { display: none !important; }
            }
          `}} />
        </div>
      )}
    </div>
  );
}
