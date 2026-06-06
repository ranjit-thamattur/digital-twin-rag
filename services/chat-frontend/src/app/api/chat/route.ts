import { NextResponse } from 'next/server';

// Parse the ALB Cognito JWT to get the user's email
function extractEmailFromOidc(oidcData: string | null): string | null {
  if (!oidcData) return null;
  try {
    const payload = oidcData.split('.')[1];
    const decoded = Buffer.from(payload, 'base64').toString('utf-8');
    const json = JSON.parse(decoded);
    return json.email || null;
  } catch (e) {
    console.error('Failed to parse OIDC token:', e);
    return null;
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { message, messages } = body;

    // 1. Get Identity from AWS ALB Cognito Headers
    const headers = request.headers;
    let email = extractEmailFromOidc(headers.get('x-amzn-oidc-data'));
    
    // Fallbacks for local testing
    if (!email) {
      email = headers.get('x-user-email') || 'ceo@11xcompany.com'; // Default mock for local dev
      console.log(`[API] Using fallback/mock email: ${email}`);
    } else {
      console.log(`[API] Authenticated user via Cognito: ${email}`);
    }

    // 2. Resolve Tenant and Persona from Email
    let tenantId = 'default';
    let personaId = 'global';

    if (email && email.includes('@')) {
      const parts = email.split('@');
      const domain = parts[1].toLowerCase();
      
      if (domain.includes('11x')) {
        tenantId = 'tenant-11x';
        // Map email prefix to persona
        personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
      } else {
        const cleanDomain = domain.split('.')[0];
        tenantId = `tenant-${cleanDomain}`;
        personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
      }
    }

    console.log(`[API] Routing to -> Tenant: ${tenantId} | Persona: ${personaId}`);

    // 3. Forward to Internal MCP Server
    const mcpUrl = process.env.MCP_SERVER_URL || 'http://mcp-server:3000';
    
    const payload = {
      query: message,
      tenantId,
      personaId,
      system_prompt: "You are the Digital Brain, a professional AI assistant. Answer based only on the Retrieved Wisdom provided to you. Speak in first person. Cite sources.",
      messages: messages || []
    };

    const response = await fetch(`${mcpUrl}/call/generate_twin_response`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      // 3 minute timeout for RAG
      signal: AbortSignal.timeout(180000) 
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`MCP Error: ${response.status} ${errorText}`);
      return NextResponse.json({ error: 'Failed to connect to Digital Brain backend.' }, { status: 500 });
    }

    const data = await response.json();
    const answer = data.content || "Digital Brain returned an empty response.";

    return NextResponse.json({ answer });

  } catch (error) {
    console.error('Chat API Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
