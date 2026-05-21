import { NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, PutCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb';

// Initialize DynamoDB Client (automatically uses ECS Task Role)
const client = new DynamoDBClient({ region: process.env.AWS_REGION || 'us-east-1' });
const docClient = DynamoDBDocumentClient.from(client);

const TABLE_NAME = process.env.CHAT_HISTORY_TABLE_NAME;

// Parse the ALB Cognito JWT to get the user's email
function extractEmailFromOidc(oidcData: string | null): string | null {
  if (!oidcData) return null;
  try {
    const payload = oidcData.split('.')[1];
    const decoded = Buffer.from(payload, 'base64').toString('utf-8');
    const json = JSON.parse(decoded);
    return json.email || null;
  } catch (e) {
    console.error('Failed to parse OIDC token:', e);
    return null;
  }
}

// GET: Fetch user's chat history
export async function GET(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    
    if (!TABLE_NAME) {
      console.error('CHAT_HISTORY_TABLE_NAME is missing');
      return NextResponse.json({ messages: [] });
    }

    const command = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'user_email = :email',
      ExpressionAttributeValues: {
        ':email': email
      },
      ScanIndexForward: false, // Sort descending to get latest first
      Limit: 20 // Limit to latest 20 messages (10 user/assistant interactions)
    });

    const response = await docClient.send(command);
    
    // Reverse the items so they are in ascending chronological order for the UI
    const items = response.Items?.reverse() || [];
    
    const messages = items.map(item => ({
      role: item.role,
      content: item.content,
      timestamp: item.timestamp
    }));

    return NextResponse.json({ messages });
  } catch (error) {
    console.error('Failed to fetch chat history:', error);
    return NextResponse.json({ error: 'Failed to fetch history' }, { status: 500 });
  }
}

// POST: Save a new message to history
export async function POST(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    
    if (!TABLE_NAME) {
      console.error('CHAT_HISTORY_TABLE_NAME is missing');
      return NextResponse.json({ success: false });
    }

    const body = await request.json();
    const { role, content } = body;

    if (!role || !content) {
      return NextResponse.json({ error: 'Missing role or content' }, { status: 400 });
    }

    // Save exactly with millisecond precision
    const timestamp = new Date().toISOString() + Math.random().toString().slice(1, 6);

    const command = new PutCommand({
      TableName: TABLE_NAME,
      Item: {
        user_email: email,
        timestamp: timestamp,
        role: role,
        content: content
      }
    });

    await docClient.send(command);

    return NextResponse.json({ success: true, timestamp });
  } catch (error) {
    console.error('Failed to save chat message:', error);
    return NextResponse.json({ error: 'Failed to save message' }, { status: 500 });
  }
}

// DELETE: Clear user's chat history (Note: DynamoDB requires deleting items one by one or using batch, here we query then delete)
export async function DELETE(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    
    if (!TABLE_NAME) return NextResponse.json({ success: false });

    // First query all items
    const queryCommand = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'user_email = :email',
      ExpressionAttributeValues: { ':email': email }
    });
    
    const response = await docClient.send(queryCommand);
    const items = response.Items || [];

    // Delete items sequentially (batch write could be used for larger histories)
    for (const item of items) {
      await docClient.send(new DeleteCommand({
        TableName: TABLE_NAME,
        Key: {
          user_email: email,
          timestamp: item.timestamp
        }
      }));
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Failed to clear chat history:', error);
    return NextResponse.json({ error: 'Failed to clear history' }, { status: 500 });
  }
}
