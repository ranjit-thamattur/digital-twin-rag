import { NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand } from '@aws-sdk/lib-dynamodb';

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

// GET: Fetch list of recent chat sessions for the sidebar (limit 10)
export async function GET(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    
    if (!TABLE_NAME) {
      return NextResponse.json({ sessions: [] });
    }

    const command = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'pk = :pk',
      ExpressionAttributeValues: {
        ':pk': `USER#${email}`
      },
      ScanIndexForward: false, // Sort descending to get the newest sessions first
      Limit: 10 // Only return the latest 10 chat sessions
    });

    const response = await docClient.send(command);
    
    const sessions = response.Items?.map(item => ({
      sessionId: item.sessionId,
      title: item.title,
      updatedAt: item.updatedAt,
      sessionSk: item.sk
    })) || [];

    return NextResponse.json({ sessions });
  } catch (error) {
    console.error('Failed to fetch chat sessions:', error);
    return NextResponse.json({ error: 'Failed to fetch sessions' }, { status: 500 });
  }
}
