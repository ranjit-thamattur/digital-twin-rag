import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function extractEmailFromOidc(oidcData: string | null): string | null {
  if (!oidcData) return null;
  try {
    const payload = oidcData.split('.')[1];
    const decoded = Buffer.from(payload, 'base64').toString('utf-8');
    const json = JSON.parse(decoded);
    return json.email || null;
  } catch (e) {
    return null;
  }
}

// GET: Real document-count / last-updated stats for the current user's
// tenant + persona, used by the "Your Business Brain" dashboard panel.
export async function GET(request: Request) {
  try {
    const headers = request.headers;
    let email = extractEmailFromOidc(headers.get('x-amzn-oidc-data'));
    if (!email) {
      email = headers.get('x-user-email') || 'ceo@11xcompany.com';
    }

    let tenantId = 'default';
    let personaId = 'global';
    if (email && email.includes('@')) {
      const parts = email.split('@');
      const cleanDomain = parts[1].toLowerCase().split('.')[0];
      tenantId = `tenant-${cleanDomain}`;
      personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
    }

    const mcpUrl = process.env.MCP_SERVER_URL || 'http://mcp-server:3000';

    const response = await fetch(`${mcpUrl}/call/get_knowledge_stats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenantId, personaId }),
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return NextResponse.json({ document_count: 0, last_updated: null });
    }

    const data = await response.json();
    const content = data.content || {};

    return NextResponse.json({
      document_count: content.document_count ?? 0,
      last_updated: content.last_updated ?? null,
    });
  } catch (error) {
    console.error('Knowledge stats API error:', error);
    return NextResponse.json({ document_count: 0, last_updated: null });
  }
}
