import { NextRequest, NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, UpdateCommand } from '@aws-sdk/lib-dynamodb';

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

export async function DELETE(req: NextRequest) {
  try {
    // Get the current user's tenantId from the Cognito token
    const tenantId = extractEmailFromOidc(req.headers.get('x-amzn-oidc-data'))
      || req.headers.get('x-user-email')
      || 'default_tenant';

    // 1. Remove the Google Drive attributes from the tenant's row in DynamoDB
    const tenantTable = process.env.TENANT_TABLE || 'clonemind-tenants';
    await docClient.send(new UpdateCommand({
      TableName: tenantTable,
      Key: { tenantId: tenantId },
      UpdateExpression: 'REMOVE googleDriveToken, googleDriveStatus, googleDriveConnectedAt, googleDrivePageToken, googleDriveChannelId, googleDriveResourceId, googleDriveFolderId'
    }));

    // 2. Optionally: revoke the token from Google's side too
    // This is a best-practice so the user sees "Removed" in their Google account settings
    // We'd need the access_token to do this, but since we only stored the refresh_token,
    // skipping for now — the token simply becomes unusable once deleted from DB.

    console.log(`Disconnected Google Drive for tenant: ${tenantId}`);
    return NextResponse.json({ success: true, message: 'Google Drive disconnected' });

  } catch (error) {
    console.error('Failed to disconnect Google Drive:', error);
    return NextResponse.json({ error: 'Failed to disconnect' }, { status: 500 });
  }
}
