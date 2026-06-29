import { NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, ScanCommand } from '@aws-sdk/lib-dynamodb';

export const dynamic = 'force-dynamic';

const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-east-1' });
const docClient = DynamoDBDocumentClient.from(client);
const TABLE_NAME = process.env.CHAT_HISTORY_TABLE_NAME;

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
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || '';
    
    // Security check: Only allow peakcoach to query all tenants
    if (!email.startsWith('peakcoach@')) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 403 });
    }

    if (!TABLE_NAME) {
      return NextResponse.json({ tenants: [] });
    }

    // Scan DynamoDB for all unique pk (which are in the format USER#email)
    // NOTE: Scanning is okay here for admin dashboards, but could be slow for millions of users.
    const command = new ScanCommand({
      TableName: TABLE_NAME,
      ProjectionExpression: 'pk'
    });

    const response = await docClient.send(command);
    
    const tenants = new Set<string>();

    response.Items?.forEach(item => {
      const pk = item.pk as string;
      if (pk && pk.startsWith('USER#')) {
        const userEmail = pk.replace('USER#', '');
        const parts = userEmail.split('@');
        if (parts.length === 2) {
            const domain = parts[1].split('.')[0];
            // Ignore the coach's own domain or test domains if desired
            if (domain !== 'peakpa') {
               tenants.add(domain);
            }
        }
      }
    });

    return NextResponse.json({ tenants: Array.from(tenants).sort() });
  } catch (error) {
    console.error('Failed to fetch active tenants:', error);
    return NextResponse.json({ error: 'Failed to fetch active tenants' }, { status: 500 });
  }
}
