'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Brain, User, Plus, Settings, MessageSquare, Paperclip } from 'lucide-react';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMsg,
          // Exclude the message we just sent from history
          messages: messages 
        }),
      });

      const data = await response.json();
      
      if (response.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.error}` }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Connection failed. Please try again.' }]);
    } finally {
      setIsLoading(false);
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
        
        <button className="new-chat-btn" onClick={() => setMessages([])}>
          <Plus size={18} /> New Chat
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
          {messages.length === 0 && (
            <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Brain size={48} style={{ margin: '0 auto 16px', opacity: 0.5 }} />
              <h2>How can I help you today?</h2>
              <p style={{ marginTop: '8px' }}>Ask me about documents, metrics, or company knowledge.</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message-row ${msg.role}`}>
              <div className={`avatar ${msg.role === 'assistant' ? 'ai' : ''}`}>
                {msg.role === 'user' ? <User size={18} /> : <Brain size={18} color="white" />}
              </div>
              <div className="message-content">
                <div className="bubble">
                  {msg.content}
                </div>
              </div>
            </div>
          ))}
          
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
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="input-container">
          <form onSubmit={handleSubmit} className="input-box">
            <Paperclip size={20} color="var(--text-secondary)" style={{ marginRight: '12px', cursor: 'pointer' }} />
            <input
              type="text"
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Digital Brain..."
              disabled={isLoading}
            />
            <button type="submit" className="send-btn" disabled={!input.trim() || isLoading}>
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
