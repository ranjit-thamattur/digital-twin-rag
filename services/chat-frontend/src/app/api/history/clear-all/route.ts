import { NextResponse } from 'next/server';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb';

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

export async function DELETE(request: Request) {
  try {
    const email = extractEmailFromOidc(request.headers.get('x-amzn-oidc-data')) || request.headers.get('x-user-email') || 'ceo@11xcompany.com';
    
    if (!TABLE_NAME) return NextResponse.json({ success: false });

    // 1. Fetch all session metadata for this user
    const sessionsQuery = new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: 'pk = :pk',
      ExpressionAttributeValues: {
        ':pk': `USER#${email}`
      }
    });

    const sessionsResponse = await docClient.send(sessionsQuery);
    const sessions = sessionsResponse.Items || [];

    // 2. Loop through each session and delete the messages AND the metadata
    for (const session of sessions) {
      const sessionId = session.sessionId;
      const sessionSk = session.sk;

      // Delete the metadata row
      await docClient.send(new DeleteCommand({
        TableName: TABLE_NAME,
        Key: { pk: `USER#${email}`, sk: sessionSk }
      }));

      // Query all messages for this session
      const messagesQuery = new QueryCommand({
        TableName: TABLE_NAME,
        KeyConditionExpression: 'pk = :pk',
        ExpressionAttributeValues: { ':pk': `SESSION#${sessionId}` }
      });
      
      const messagesResponse = await docClient.send(messagesQuery);
      const messages = messagesResponse.Items || [];

      // Delete all messages
      for (const msg of messages) {
        await docClient.send(new DeleteCommand({
          TableName: TABLE_NAME,
          Key: { pk: msg.pk, sk: msg.sk }
        }));
      }
    }

    return NextResponse.json({ success: true, count: sessions.length });
  } catch (error) {
    console.error('Failed to clear all chat history:', error);
    return NextResponse.json({ error: 'Failed to clear all history' }, { status: 500 });
  }
}
