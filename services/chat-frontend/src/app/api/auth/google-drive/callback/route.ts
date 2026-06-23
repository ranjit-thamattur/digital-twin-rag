import { NextRequest, NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, PutCommand } from '@aws-sdk/lib-dynamodb';

// Initialize DynamoDB Client
const client = new DynamoDBClient({ region: process.env.AWS_DEFAULT_REGION || 'us-east-1' });
const docClient = DynamoDBDocumentClient.from(client);

export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const code = searchParams.get('code');
  const error = searchParams.get('error');

  if (error) {
    return NextResponse.json({ error: 'User denied permission' }, { status: 400 });
  }

  if (!code) {
    return NextResponse.json({ error: 'No authorization code provided' }, { status: 400 });
  }

  const clientId = process.env.GOOGLE_CLIENT_ID || 'PLACEHOLDER_CLIENT_ID';
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET || 'PLACEHOLDER_CLIENT_SECRET';
  
  // Try to use the host from headers, fallback to localhost
  const host = req.headers.get('host') || 'localhost:3000';
  const protocol = req.headers.get('x-forwarded-proto') || (host.includes('localhost') ? 'http' : 'https');
  const redirectUri = `${protocol}://${host}/api/auth/google-drive/callback`;

  try {
    // 1. Exchange the auth code for access and refresh tokens
    const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        code,
        grant_type: 'authorization_code',
        redirect_uri: redirectUri,
      }),
    });

    const tokens = await tokenResponse.json();

    if (!tokenResponse.ok) {
      console.error('Google OAuth Error:', tokens);
      return NextResponse.json({ error: 'Failed to exchange token', details: tokens }, { status: 400 });
    }

    const { access_token, refresh_token, expires_in } = tokens;

    // 2. Save the refresh_token to the Database
    // In a real app, you would retrieve the tenantId from the user's session.
    // For now, we use a placeholder or generic tenantId.
    const tenantId = 'default_tenant'; 

    if (refresh_token) {
      await docClient.send(new PutCommand({
        TableName: process.env.INTEGRATIONS_TABLE || 'TenantIntegrations',
        Item: {
          tenantId: tenantId,
          provider: 'google_drive',
          refreshToken: refresh_token, // IMPORTANT: In production, encrypt this value before saving!
          updatedAt: new Date().toISOString(),
          status: 'CONNECTED'
        }
      }));
      console.log(`Saved Google Drive refresh token for tenant ${tenantId}`);
    }

    // 3. Register the Webhook (Optional immediate registration)
    // We will do this in the webhook setup step or via a separate job

    // 4. Redirect back to the chat settings, indicating success
    return NextResponse.redirect(`${protocol}://${host}/chat?gdrive_connected=true`);
    
  } catch (err) {
    console.error('OAuth Callback Exception:', err);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
