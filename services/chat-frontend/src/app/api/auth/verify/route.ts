import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const { email } = await request.json();

    if (!email || !email.includes('@')) {
      return NextResponse.json({ error: 'Invalid email address' }, { status: 400 });
    }

    const parts = email.split('@');
    const domain = parts[1].toLowerCase();
    
    // STRICT DOMAIN CHECK
    const validDomains = ['11xcompany.com', 'peakpa.com', '11x.com'];
    
    if (!validDomains.includes(domain)) {
        // Return 404 if the account does not exist
        return NextResponse.json({ error: 'Account does not exist' }, { status: 404 });
    }

    return NextResponse.json({ success: true });

  } catch (error) {
    console.error('Tenant verification error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
