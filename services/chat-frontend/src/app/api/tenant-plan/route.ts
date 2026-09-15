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

// GET: which plan (basic/premium) the current user's tenant is on.
export async function GET(request: Request) {
  try {
    const headers = request.headers;
    let email = extractEmailFromOidc(headers.get('x-amzn-oidc-data'));
    if (!email) {
      email = headers.get('x-user-email') || 'ceo@11xcompany.com';
    }

    let tenantId = 'default';
    if (email && email.includes('@')) {
      const cleanDomain = email.split('@')[1].toLowerCase().split('.')[0];
      tenantId = `tenant-${cleanDomain}`;
    }

    const mcpUrl = process.env.MCP_SERVER_URL || 'http://mcp-server:3000';

    const response = await fetch(`${mcpUrl}/call/get_tenant_plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenantId }),
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return NextResponse.json({ plan: 'basic' });
    }

    const data = await response.json();
    const content = data.content || {};

    return NextResponse.json({ plan: content.plan === 'premium' ? 'premium' : 'basic' });
  } catch (error) {
    console.error('Tenant plan API error:', error);
    return NextResponse.json({ plan: 'basic' });
  }
}
