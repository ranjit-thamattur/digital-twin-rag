'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Brain, User, Plus, Settings, MessageSquare, Paperclip, Loader2, Trash2 } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';

type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
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
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch recent sessions on load
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async (selectFirst: boolean = true) => {
    try {
      const res = await fetch('/api/history/sessions');
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
      const res = await fetch(`/api/history?sessionId=${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (e) {
      console.error('Failed to load session messages', e);
    } finally {
      setIsFetchingHistory(false);
    }
  };

  const startNewChat = () => {
    setCurrentSessionId(uuidv4());
    setMessages([]);
    setIsFetchingHistory(false);
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
        setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
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

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    if (fileInputRef.current) fileInputRef.current.value = '';

    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await response.json();

      if (response.ok) {
        setMessages(prev => [...prev, { role: 'system', content: `✅ File "${file.name}" uploaded successfully. Digital Brain is currently processing it into your knowledge base.` }]);
      } else {
        setMessages(prev => [...prev, { role: 'system', content: `❌ Failed to upload "${file.name}": ${data.error}` }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'system', content: `❌ Connection error while uploading "${file.name}".` }]);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <div className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Brain size={20} />
          </div>
          <span>Digital Brain</span>
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
                <MessageSquare size={14} style={{ marginRight: '8px', minWidth: '14px' }}/>
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

        <div style={{ marginTop: 'auto', display: 'flex', gap: '10px', color: 'var(--text-secondary)', cursor: 'pointer', alignItems: 'center' }}>
          <Settings size={16} />
          <span style={{ fontSize: '0.9rem' }}>Settings</span>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="main-chat">
        <div className="header">
          <div>Your Digital Twin</div>
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
              onChange={handleFileUpload} 
              accept=".pdf,.txt,.docx,.pptx,.csv"
            />
            <Paperclip 
              size={20} 
              color="var(--text-secondary)" 
              style={{ marginRight: '12px', cursor: 'pointer' }} 
              onClick={() => fileInputRef.current?.click()}
            />
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
    </div>
  );
}
