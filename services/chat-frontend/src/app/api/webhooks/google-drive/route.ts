import { NextRequest, NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, ScanCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { google } from 'googleapis';

const awsRegion = process.env.AWS_DEFAULT_REGION || 'us-east-1';
const dynamoClient = new DynamoDBClient({ region: awsRegion });
const docClient = DynamoDBDocumentClient.from(dynamoClient);
const s3Client = new S3Client({ region: awsRegion });

// Background processor function
async function processGoogleDriveChanges(channelId: string) {
  try {
    const tenantTable = process.env.TENANT_TABLE || 'clonemind-tenants';
    const s3Bucket = process.env.DOCUMENTS_BUCKET_NAME || 'clonemind-docs';
    const clientId = process.env.GOOGLE_CLIENT_ID || '';
    const clientSecret = process.env.GOOGLE_CLIENT_SECRET || '';
    const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ai.peakpa.com';
    const redirectUri = `${appUrl}/api/auth/google-drive/callback`;

    // 1. Look up the tenant by channelId (using Scan since we don't have a GSI yet)
    const scanRes = await docClient.send(new ScanCommand({
      TableName: tenantTable,
      FilterExpression: 'googleDriveChannelId = :cid',
      ExpressionAttributeValues: { ':cid': channelId }
    }));

    if (!scanRes.Items || scanRes.Items.length === 0) {
      console.log(`Webhook: No tenant found for channelId ${channelId}`);
      return;
    }

    const tenant = scanRes.Items[0];
    const tenantId = tenant.tenantId;
    const refreshToken = tenant.googleDriveToken;
    let pageToken = tenant.googleDrivePageToken;
    const syncFolderId = tenant.googleDriveFolderId;

    if (!refreshToken || !pageToken || !syncFolderId) {
      console.log(`Webhook: Tenant ${tenantId} missing token, pageToken, or folderId`);
      return;
    }

    // 2. Initialize Google Drive client
    const oauth2Client = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
    oauth2Client.setCredentials({ refresh_token: refreshToken });
    const drive = google.drive({ version: 'v3', auth: oauth2Client });

    // 3. Fetch changes
    let newPageToken = pageToken;
    let hasMore = true;

    while (hasMore) {
      const changesRes = await drive.changes.list({
        pageToken: newPageToken,
        includeRemoved: false,
        includeItemsFromAllDrives: true,
        supportsAllDrives: true,
        fields: 'nextPageToken, newStartPageToken, changes(fileId, file(name, mimeType, parents))'
      });

      const changes = changesRes.data.changes || [];
      
      for (const change of changes) {
        if (change.fileId && change.file) {
          const file = change.file;
          // Skip folders
          if (file.mimeType === 'application/vnd.google-apps.folder') continue;

          // Skip files not in the Digital Brain Sync folder
          if (!file.parents || !file.parents.includes(syncFolderId)) {
            console.log(`Webhook: Skipping ${file.name} - not in sync folder`);
            continue;
          }

          console.log(`Webhook: Downloading changed file ${file.name} for tenant ${tenantId}`);

          try {
            // 4. Download file from Google Drive
            const fileRes = await drive.files.get(
              { fileId: change.fileId, alt: 'media' },
              { responseType: 'arraybuffer' }
            );
            
            const fileBuffer = Buffer.from(fileRes.data as ArrayBuffer);

            if (fileBuffer.length === 0) {
              console.log(`Webhook: Skipping ${file.name} - file is empty (0 bytes)`);
              continue;
            }

            if (file.name && file.name.match(/\.(txt|md|csv|json)$/i)) {
              const content = fileBuffer.toString('utf-8').trim();
              if (content.length === 0) {
                console.log(`Webhook: Skipping ${file.name} - text file contains only whitespace`);
                continue;
              }
            }

            // 5. Upload to S3 (isolated to this tenant/persona)
            // Assuming the default persona is 'ceo' for now if not specified.
            const personaId = tenant.defaultPersona || 'ceo';
            
            // Map email to S3 tenant prefix
            let s3TenantId = 'default_tenant';
            if (tenantId && tenantId.includes('@')) {
              const domain = tenantId.split('@')[1];
              const cleanDomain = domain.split('.')[0];
              s3TenantId = `tenant-${cleanDomain}`;
            }
            
            const s3Key = `${s3TenantId}/${personaId}/${file.name}`;

            await s3Client.send(new PutObjectCommand({
              Bucket: s3Bucket,
              Key: s3Key,
              Body: fileBuffer,
              ContentType: file.mimeType || 'application/octet-stream'
            }));

            console.log(`Webhook: Successfully uploaded ${s3Key} to S3`);
          } catch (dlErr) {
            console.error(`Webhook: Failed to process file ${file.name}`, dlErr);
          }
        }
      }

      if (changesRes.data.nextPageToken) {
        newPageToken = changesRes.data.nextPageToken;
      } else {
        newPageToken = changesRes.data.newStartPageToken || newPageToken;
        hasMore = false;
      }
    }

    // 6. Update pageToken in DynamoDB
    if (newPageToken !== pageToken) {
      await docClient.send(new UpdateCommand({
        TableName: tenantTable,
        Key: { tenantId: tenantId },
        UpdateExpression: 'SET googleDrivePageToken = :pt',
        ExpressionAttributeValues: { ':pt': newPageToken }
      }));
      console.log(`Webhook: Updated pageToken for tenant ${tenantId}`);
    }

  } catch (error) {
    console.error('Background Webhook Processing Error:', error);
  }
}

export async function POST(req: NextRequest) {
  try {
    const channelId = req.headers.get('X-Goog-Channel-ID');
    const resourceState = req.headers.get('X-Goog-Resource-State');
    
    console.log(`Webhook Received: [State: ${resourceState}] Channel: ${channelId}`);

    if (resourceState === 'sync') {
      return NextResponse.json({ message: 'Webhook synced successfully' }, { status: 200 });
    }

    if (!channelId) {
      return NextResponse.json({ error: 'Missing Channel ID' }, { status: 400 });
    }

    // Fire and forget the background processing since this is running on an ECS Node instance
    // We must return 200 OK immediately so Google knows we received the webhook
    processGoogleDriveChanges(channelId).catch(err => {
      console.error('Unhandled error in processGoogleDriveChanges:', err);
    });

    return NextResponse.json({ success: true, message: 'Webhook acknowledged' }, { status: 200 });
  } catch (error) {
    console.error('Webhook Endpoint Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
