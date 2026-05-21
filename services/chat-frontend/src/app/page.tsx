'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Brain, User, Plus, Settings, MessageSquare, Paperclip, Loader2 } from 'lucide-react';

type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetchingHistory, setIsFetchingHistory] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch history on load
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch('/api/history');
        if (res.ok) {
          const data = await res.json();
          setMessages(data.messages || []);
        }
      } catch (e) {
        console.error('Failed to fetch history', e);
      } finally {
        setIsFetchingHistory(false);
      }
    };
    fetchHistory();
  }, []);

  const saveToHistory = async (role: string, content: string) => {
    try {
      await fetch('/api/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, content })
      });
    } catch (e) {
      console.error('Failed to save to history', e);
    }
  };

  const clearHistory = async () => {
    if (!confirm('Are you sure you want to clear your chat history?')) return;
    setMessages([]);
    try {
      await fetch('/api/history', { method: 'DELETE' });
    } catch (e) {
      console.error('Failed to delete history', e);
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
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);
    
    // Fire and forget save
    saveToHistory('user', userMsg);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMsg,
          // Exclude the message we just sent from history
          messages: messages.filter(m => m.role !== 'system') 
        }),
      });

      const data = await response.json();
      
      if (response.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
        saveToHistory('assistant', data.answer);
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
    // Reset input so the same file can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setMessages(prev => [...prev, { 
          role: 'system', 
          content: `✅ File "${file.name}" uploaded successfully. Digital Brain is currently processing it into your knowledge base.` 
        }]);
      } else {
        setMessages(prev => [...prev, { 
          role: 'system', 
          content: `❌ Failed to upload "${file.name}": ${data.error}` 
        }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'system', 
        content: `❌ Connection error while uploading "${file.name}".` 
      }]);
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
        
        <button className="new-chat-btn" onClick={clearHistory}>
          <Plus size={18} /> Clear Chat History
        </button>

        <div className="chat-history">
          <div className="history-title">Recent Chats</div>
          <div className="history-item">
            <MessageSquare size={14} style={{ display: 'inline', marginRight: '8px' }}/>
            Q4 Metrics Review
          </div>
          <div className="history-item">
            <MessageSquare size={14} style={{ display: 'inline', marginRight: '8px' }}/>
            HR Policy Update
          </div>
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
              <p>Loading history...</p>
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
            {/* Hidden file input */}
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              onChange={handleFileUpload} 
              accept=".pdf,.txt,.docx,.pptx,.csv"
            />
            {/* Clickable paperclip */}
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
              disabled={isLoading || isUploading}
            />
            <button type="submit" className="send-btn" disabled={!input.trim() || isLoading || isUploading}>
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
