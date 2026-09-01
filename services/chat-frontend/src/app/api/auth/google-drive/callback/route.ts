import { NextRequest, NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, UpdateCommand } from '@aws-sdk/lib-dynamodb';
import { google } from 'googleapis';
import { v4 as uuidv4 } from 'uuid';

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

    const { refresh_token, access_token } = tokens;

    // 2. Resolve the tenantId from the Cognito OIDC token (set by the ALB)
    //    Falls back to the x-user-email header for local dev
    const tenantId = extractEmailFromOidc(req.headers.get('x-amzn-oidc-data'))
      || req.headers.get('x-user-email')
      || 'default_tenant';

    // 3. Register the Webhook (Push Notifications) and Create Sync Folder
    let pageToken = null;
    let channelId = null;
    let resourceId = null;
    let folderId = null;
    
    try {
      const oauth2Client = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
      oauth2Client.setCredentials(tokens);
      const drive = google.drive({ version: 'v3', auth: oauth2Client });

      // Search for the "Digital Brain Sync" folder
      // We only have drive.readonly scope, so we cannot create it automatically.
      const folderRes = await drive.files.list({
        q: "name='Digital Brain Sync' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields: 'files(id)',
        spaces: 'drive'
      });
      
      if (folderRes.data.files && folderRes.data.files.length > 0) {
        folderId = folderRes.data.files[0].id;
        console.log(`Found existing sync folder ${folderId} for tenant ${tenantId}`);
      } else {
        // Auto-create the "Digital Brain Sync" folder — user doesn't need to do this manually
        console.log(`Sync folder not found for tenant ${tenantId} — creating it automatically`);
        const createRes = await drive.files.create({
          requestBody: {
            name: 'Digital Brain Sync',
            mimeType: 'application/vnd.google-apps.folder',
          },
          fields: 'id',
        });
        folderId = createRes.data.id;
        console.log(`Created sync folder ${folderId} for tenant ${tenantId}`);
      }

      // Get the start page token to track future changes
      const startPageTokenRes = await drive.changes.getStartPageToken();
      pageToken = startPageTokenRes.data.startPageToken;
      
      channelId = uuidv4();
      const webhookUrl = `${appUrl}/api/webhooks/google-drive`;

      // Subscribe to changes
      const watchRes = await drive.changes.watch({
        pageToken: pageToken || undefined,
        requestBody: {
          id: channelId,
          type: 'web_hook',
          address: webhookUrl,
          payload: true
        }
      });
      resourceId = watchRes.data.resourceId;
      console.log(`Registered Google Drive watch for tenant ${tenantId}. Channel: ${channelId}`);
    } catch (watchErr) {
      console.error('Failed to register Google Drive watch. Domain might not be verified in Google Search Console.', watchErr);
      // We continue even if watch fails, so we at least save the refresh_token
    }

    // 4. Save the credentials and folder ID into the EXISTING clonemind-tenants DynamoDB table
    if (refresh_token) {
      const tenantTable = process.env.TENANT_TABLE || 'clonemind-tenants';
      await docClient.send(new UpdateCommand({
        TableName: tenantTable,
        Key: { tenantId: tenantId },
        UpdateExpression: 'SET googleDriveToken = :token, googleDriveConnectedAt = :ts, googleDriveStatus = :status, googleDrivePageToken = :pt, googleDriveChannelId = :cid, googleDriveResourceId = :rid, googleDriveFolderId = :fid',
        ExpressionAttributeValues: {
          ':token': refresh_token,
          ':ts': new Date().toISOString(),
          ':status': 'CONNECTED',
          ':pt': pageToken || null,
          ':cid': channelId || null,
          ':rid': resourceId || null,
          ':fid': folderId || null
        }
      }));
      console.log(`Saved Google Drive credentials for tenant: ${tenantId}`);
    }

    // 4. Redirect back to the chat settings with success flag
    return NextResponse.redirect(`${appUrl}/chat?gdrive_connected=true`);
    
  } catch (err) {
    console.error('OAuth Callback Exception:', err);
    return NextResponse.redirect(`${appUrl}/chat?gdrive_error=server_error`);
  }
}
