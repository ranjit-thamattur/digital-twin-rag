import { NextRequest, NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, UpdateCommand } from '@aws-sdk/lib-dynamodb';

// Initialize DynamoDB Client
const client = new DynamoDBClient({ region: process.env.AWS_DEFAULT_REGION || 'us-east-1' });
const docClient = DynamoDBDocumentClient.from(client);

function extractEmailFromOidc(oidcData: string | null): string | null {
  if (!oidcData) return null;
  try {
    const payload = oidcData.split('.')[1];
    const decoded = Buffer.from(payload, 'base64').toString('utf-8');
    return JSON.parse(decoded).email || null;
  } catch {
    return null;
  }
}

export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const code = searchParams.get('code');
  const error = searchParams.get('error');

  if (error) {
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_APP_URL || 'https://ai.peakpa.com'}/chat?gdrive_error=access_denied`);
  }

  if (!code) {
    return NextResponse.json({ error: 'No authorization code provided' }, { status: 400 });
  }

  const clientId = process.env.GOOGLE_CLIENT_ID || '';
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET || '';
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ai.peakpa.com';
  
  // Use the same hardcoded redirectUri that was used in the initial OAuth request
  // MUST match exactly what we sent Google — using the env var to be consistent
  const redirectUri = `${appUrl}/api/auth/google-drive/callback`;

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
      console.error('Google OAuth Token Exchange Error:', tokens);
      return NextResponse.redirect(`${appUrl}/chat?gdrive_error=token_exchange_failed`);
    }

    const { refresh_token } = tokens;

    // 2. Resolve the tenantId from the Cognito OIDC token (set by the ALB)
    //    Falls back to the x-user-email header for local dev
    const tenantId = extractEmailFromOidc(req.headers.get('x-amzn-oidc-data'))
      || req.headers.get('x-user-email')
      || 'default_tenant';

    // 3. Save the refresh_token into the EXISTING clonemind-tenants DynamoDB table
    //    We store it as a new attribute on the tenant's row (no new table needed!)
    if (refresh_token) {
      const tenantTable = process.env.TENANT_TABLE || 'clonemind-tenants';
      await docClient.send(new UpdateCommand({
        TableName: tenantTable,
        // The tenant row key is the tenantId from the user lookup
        // For now we store it keyed on the user email as a safe fallback
        Key: { tenantId: tenantId },
        UpdateExpression: 'SET googleDriveToken = :token, googleDriveConnectedAt = :ts, googleDriveStatus = :status',
        ExpressionAttributeValues: {
          ':token': refresh_token,
          ':ts': new Date().toISOString(),
          ':status': 'CONNECTED'
        }
      }));
      console.log(`Saved Google Drive refresh token for tenant: ${tenantId}`);
    }

    // 4. Redirect back to the chat settings with success flag
    return NextResponse.redirect(`${appUrl}/chat?gdrive_connected=true`);
    
  } catch (err) {
    console.error('OAuth Callback Exception:', err);
    return NextResponse.redirect(`${appUrl}/chat?gdrive_error=server_error`);
  }
}
