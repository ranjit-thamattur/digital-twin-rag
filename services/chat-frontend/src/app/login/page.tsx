'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import Image from 'next/image';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const COGNITO_URL = 'https://clonemind-543187302175.auth.us-east-1.amazoncognito.com/login?client_id=70josbv1q9rjfhgji773k8p3gk&response_type=code&scope=email+openid+profile&redirect_uri=https://ai.peakpa.com/oauth2/idpresponse';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setError('Please enter your email address');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        if (res.status === 404) {
          setError('Account does not exist');
        } else {
          setError('Failed to verify account. Please try again.');
        }
        setIsLoading(false);
        return;
      }

      // Success! Redirect to Cognito with the email pre-filled as login_hint
      const finalCognitoUrl = `${COGNITO_URL}&login_hint=${encodeURIComponent(email)}`;
      window.location.href = finalCognitoUrl;

    } catch (err) {
      setError('Connection error. Please check your network.');
      setIsLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100dvh', width: '100%', backgroundColor: 'var(--bg-dark)', overflow: 'hidden' }}>
      
      {/* Left Side - Marketing / Branding */}
      <div style={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column',
        justifyContent: 'center', 
        padding: '60px',
        position: 'relative',
        background: 'radial-gradient(circle at 30% 70%, rgba(139, 92, 246, 0.15), transparent 60%)'
      }}>
        <div style={{ zIndex: 10, maxWidth: '500px' }}>
          <img 
            src="/peak_logo_cognito.png" 
            alt="Peak Performance Advisors" 
            style={{ width: '250px', marginBottom: '60px' }} 
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
          <h1 style={{ fontSize: '4rem', fontWeight: 700, color: '#c4b5fd', marginBottom: '20px', lineHeight: 1.1 }}>
            Digital Brain
          </h1>
          <p style={{ fontSize: '2rem', color: '#e5e7eb', lineHeight: 1.3, fontWeight: 300 }}>
            - Take decisions with a brain of yours
          </p>
        </div>

        {/* Abstract Neural Network Background Effect */}
        <div style={{
          position: 'absolute',
          bottom: '-10%',
          left: '-10%',
          width: '80%',
          height: '80%',
          backgroundImage: 'radial-gradient(circle, rgba(139, 92, 246, 0.2) 2px, transparent 2px)',
          backgroundSize: '40px 40px',
          opacity: 0.3,
          zIndex: 1,
          maskImage: 'linear-gradient(to top right, black, transparent)',
          WebkitMaskImage: 'linear-gradient(to top right, black, transparent)'
        }}></div>
      </div>

      {/* Right Side - Login Form */}
      <div style={{ 
        flex: 1, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        padding: '20px',
        background: 'linear-gradient(135deg, rgba(20, 20, 25, 0.9) 0%, rgba(15, 15, 20, 0.95) 100%)',
        position: 'relative'
      }}>
        
        {/* Glassmorphism Panel */}
        <div style={{
          width: '100%',
          maxWidth: '480px',
          padding: '50px 40px',
          borderRadius: '24px',
          backgroundColor: 'rgba(255, 255, 255, 0.03)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          border: '1px solid rgba(255, 255, 255, 0.05)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
        }}>
          
          <h2 style={{ fontSize: '1.5rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '30px' }}>
            Please enter your email
          </h2>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Email Address</label>
              <input 
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="email@peak-enterprise.com"
                required
                style={{
                  width: '100%',
                  padding: '16px 20px',
                  borderRadius: '12px',
                  backgroundColor: 'rgba(0, 0, 0, 0.2)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: 'var(--text-primary)',
                  fontSize: '1rem',
                  outline: 'none',
                  transition: 'border-color 0.2s ease, box-shadow 0.2s ease'
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = '#8b5cf6';
                  e.target.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.2)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>

            {error && (
              <div style={{ color: '#ef4444', fontSize: '0.9rem', marginTop: '-10px' }}>
                {error}
              </div>
            )}

            <button 
              type="submit"
              disabled={isLoading}
              style={{
                width: '100%',
                padding: '16px',
                borderRadius: '12px',
                border: 'none',
                background: 'linear-gradient(90deg, #6d28d9 0%, #4c1d95 100%)',
                color: 'white',
                fontSize: '1.1rem',
                fontWeight: 600,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.7 : 1,
                marginTop: '10px',
                transition: 'transform 0.2s ease, opacity 0.2s ease',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '10px',
                boxShadow: '0 10px 25px -5px rgba(109, 40, 217, 0.4)'
              }}
              onMouseOver={(e) => !isLoading && (e.currentTarget.style.transform = 'translateY(-2px)')}
              onMouseOut={(e) => !isLoading && (e.currentTarget.style.transform = 'translateY(0)')}
            >
              {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Continue to Sign In'}
            </button>
          </form>

        </div>
      </div>
    </div>
  );
}
