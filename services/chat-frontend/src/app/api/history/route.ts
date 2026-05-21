import { NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, PutCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb';

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

// GET: Fetch messages for a specific session
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get('sessionId');
    
    if (!sessionId || !TABLE_NAME) {
      return NextResponse.json({ messages: [] });
    }

    const command = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'pk = :pk',
      ExpressionAttributeValues: {
        ':pk': `SESSION#${sessionId}`
      },
      ScanIndexForward: false, // Sort descending to get latest first
      Limit: 50 // Limit to latest 50 messages per session
    });

    const response = await docClient.send(command);
    
    const items = response.Items?.reverse() || [];
    const messages = items.map(item => ({
      role: item.role,
      content: item.content,
      timestamp: item.sk.replace('MSG#', '')
    }));

    return NextResponse.json({ messages });
  } catch (error) {
    console.error('Failed to fetch chat history:', error);
    return NextResponse.json({ error: 'Failed to fetch history' }, { status: 500 });
  }
}

// POST: Save a new message and update session metadata
export async function POST(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    if (!TABLE_NAME) return NextResponse.json({ success: false });

    const body = await request.json();
    const { sessionId, role, content, isFirstMessage } = body;

    if (!sessionId || !role || !content) {
      return NextResponse.json({ error: 'Missing sessionId, role, or content' }, { status: 400 });
    }

    const timestamp = new Date().toISOString() + Math.random().toString().slice(1, 6);

    // 1. Save the message
    await docClient.send(new PutCommand({
      TableName: TABLE_NAME,
      Item: {
        pk: `SESSION#${sessionId}`,
        sk: `MSG#${timestamp}`,
        role: role,
        content: content
      }
    }));

    // 2. If it's the first message, create/update the Session metadata for the sidebar
    if (isFirstMessage && role === 'user') {
      const title = content.length > 30 ? content.substring(0, 30) + '...' : content;
      await docClient.send(new PutCommand({
        TableName: TABLE_NAME,
        Item: {
          pk: `USER#${email}`,
          sk: `SESSION#${timestamp}`, // Sort key is timestamp so we can query latest sessions easily
          sessionId: sessionId,
          title: title,
          updatedAt: timestamp
        }
      }));
    }

    return NextResponse.json({ success: true, timestamp });
  } catch (error) {
    console.error('Failed to save chat message:', error);
    return NextResponse.json({ error: 'Failed to save message' }, { status: 500 });
  }
}

// DELETE: Clear a specific session
export async function DELETE(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get('sessionId');
    const sessionSk = searchParams.get('sessionSk'); // The SK used in the USER#email partition

    if (!TABLE_NAME || !sessionId) return NextResponse.json({ success: false });

    // 1. Delete session metadata from user's list
    if (sessionSk) {
      await docClient.send(new DeleteCommand({
        TableName: TABLE_NAME,
        Key: { pk: `USER#${email}`, sk: sessionSk }
      }));
    }

    // 2. Query and delete all messages in the session
    const queryCommand = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'pk = :pk',
      ExpressionAttributeValues: { ':pk': `SESSION#${sessionId}` }
    });
    
    const response = await docClient.send(queryCommand);
    const items = response.Items || [];

    for (const item of items) {
      await docClient.send(new DeleteCommand({
        TableName: TABLE_NAME,
        Key: { pk: item.pk, sk: item.sk }
      }));
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Failed to clear chat history:', error);
    return NextResponse.json({ error: 'Failed to clear history' }, { status: 500 });
  }
}
