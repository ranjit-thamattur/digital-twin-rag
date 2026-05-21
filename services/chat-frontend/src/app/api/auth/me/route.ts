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

export async function GET(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    return NextResponse.json({ email });
  } catch (error) {
    return NextResponse.json({ email: 'Unknown User' });
  }
}
