import { NextResponse } from 'next/server';
import { PollyClient, SynthesizeSpeechCommand } from '@aws-sdk/client-polly';

// Initialize Polly Client
// We use the AWS region from env, default to us-east-1
const polly = new PollyClient({ region: process.env.AWS_REGION || 'us-east-1' });

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { text, lang } = body;

    if (!text) {
      return NextResponse.json({ error: 'No text provided' }, { status: 400 });
    }

    // Choose voice and language based on detected language from STT
    // If the language starts with 'hi', use Hindi voice Kajal
    const isHindi = lang?.toLowerCase().startsWith('hi');
    const voiceId = isHindi ? 'Kajal' : 'Matthew';
    const languageCode = isHindi ? 'hi-IN' : 'en-US';

    console.log(`[TTS API] Synthesizing speech. Lang: ${lang}, Voice: ${voiceId}`);

    // Call Amazon Polly
    const command = new SynthesizeSpeechCommand({
      Text: text.slice(0, 3000), // Polly has a 3000 character limit per request
      OutputFormat: 'mp3',
      VoiceId: voiceId,
      Engine: 'neural', // Use the high-quality neural engine
      LanguageCode: languageCode,
    });

    const response = await polly.send(command);

    if (!response.AudioStream) {
      throw new Error('No audio stream returned from Polly');
    }

    // Convert the stream to a Uint8Array
    const audioBytes = await response.AudioStream.transformToByteArray();

    // Return the audio as an MP3 binary response
    return new Response(audioBytes, {
      headers: {
        'Content-Type': 'audio/mpeg',
        'Cache-Control': 'no-cache',
      },
    });

  } catch (error) {
    console.error('[TTS API] Polly Synthesis Error:', error);
    return NextResponse.json({ error: 'Failed to synthesize speech' }, { status: 500 });
  }
}
