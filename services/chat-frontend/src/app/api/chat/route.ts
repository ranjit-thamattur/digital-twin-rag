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
    // confirmed: true when user clicks "Yes, coordinate" on a confirmation card
    const { message, messages, confirmed = false } = body;

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
      const cleanDomain = domain.split('.')[0];
      tenantId = `tenant-${cleanDomain}`;
      personaId = parts[0] === 'hr' ? 'hr_manager' : parts[0];
    }

    console.log(`[API] Routing -> Tenant: ${tenantId} | Persona: ${personaId} | Confirmed: ${confirmed}`);

    // 3. All messages route through Chief of Staff AI
    //    - No workflow match  → Digital Brain answers silently (user sees no difference)
    //    - Workflow match, confirmed=false → confirmation card returned (no action taken)
    //    - Workflow match, confirmed=true  → multi-role fan-out executes
    const mcpUrl = process.env.MCP_SERVER_URL || 'http://mcp-server:3000';

    const payload = {
      query:     message,
      tenantId,
      personaId,
      messages:  messages || [],
      confirmed,             // ← false until user explicitly approves
    };

    const response = await fetch(`${mcpUrl}/call/chief_of_staff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      // 5 min timeout — multi-role coordination takes longer than single-role RAG
      signal: AbortSignal.timeout(300000)
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`MCP Error: ${response.status} ${errorText}`);
      return NextResponse.json({ error: 'Failed to connect to Digital Brain backend.' }, { status: 500 });
    }

    const data = await response.json();
    const content = data.content;

    // Confirmation card — workflow matched but not yet confirmed
    // Return as-is to the frontend so it can render the confirmation UI
    if (content?.type === 'confirmation_required') {
      console.log(`[API] Confirmation required for workflow: ${content.workflow_id}`);
      return NextResponse.json({
        type:     'confirmation_required',
        workflow: content,
      });
    }

    // Normal answer — either Digital Brain (no match) or Chief of Staff (confirmed)
    let answer = 'Digital Brain returned an empty response.';
    let memoryUsed: any[] = [];

    if (content) {
      if (typeof content === 'object') {
        answer     = content.answer      || answer;
        memoryUsed = content.memory_used || [];
      } else {
        answer = content;
      }
    }

    return NextResponse.json({ answer, memoryUsed });

  } catch (error) {
    console.error('Chat API Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
