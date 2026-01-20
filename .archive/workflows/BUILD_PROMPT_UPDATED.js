// Updated N8N Build Prompt Node - Dynamic Tenant Prompts from API
const item = $input.first();
const searchResponse = item.json;
const results = searchResponse.result || [];
const buildNode = $('Build Search').first();
const query = buildNode.json.query;
const tenantId = buildNode.json.tenantId || 'default';
const personaId = buildNode.json.personaId || 'user';

// Reranking - top 3 results
const rerankedResults = results
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 3);

// Load tenant-specific prompts from API
let tenantConfig = null;
let systemMessage = '';

try {
    const configResponse = await this.helpers.request({
        method: 'GET',
        url: `http://tenant-service-dt:8000/api/prompts/${tenantId}`,
        json: true
    });

    tenantConfig = configResponse;

    // Get persona-specific config
    const personaConfig = tenantConfig.personas[personaId] || {};

    // Build dynamic system prompt
    systemMessage = `You are an AI assistant for ${tenantConfig.companyName}, a ${tenantConfig.industry} company.

Use ${tenantConfig.tone} tone in your responses.

${tenantConfig.specialInstructions}

For ${personaId} persona: ${personaConfig.additionalContext || 'Provide helpful information.'}

IMPORTANT: Use ONLY the context provided below. Be specific with numbers and data.`;

    // Add few-shot examples
    const fewShotExamples = `

Examples:
Q: What is our revenue?
A: ${tenantConfig.companyName}'s total revenue for the latest period was [specific number from context].

Q: How many employees?
A: ${tenantConfig.companyName} has [specific number from context] employees.

Q: What are our main products?
A: [Based on context provided]
`;

    systemMessage += fewShotExamples;

} catch (error) {
    console.log(`Failed to load tenant config for ${tenantId}, using default`);

    // Fallback to default prompt
    systemMessage = `You are an AI assistant. Use ONLY the context provided below. Be direct and specific with data.

Examples:
Q: What is our revenue?
A: Based on the documents, total revenue was [specific amount].
`;
}

// If no context, return early
if (rerankedResults.length === 0) {
    return [{
        json: {
            prompt: `${systemMessage}\n\nQuestion: ${query}\n\nAnswer: I don't have relevant information in the knowledge base to answer this question.`,
            hasContext: false,
            tenantId: tenantId,
            personaId: personaId
        }
    }];
}

// Build context from top results (1500 chars each)
const contexts = rerankedResults.map((r, idx) => {
    const text = (r.payload?.text || '').substring(0, 1500);
    return `[Document ${idx + 1}]\n${text}`;
});

const contextText = contexts.join('\n\n');

// Final RAG prompt
const ragPrompt = `${systemMessage}

Context from Knowledge Base:
${contextText}

Question: ${query}

Answer:`;

return [{
    json: {
        prompt: ragPrompt,
        hasContext: true,
        contextCount: rerankedResults.length,
        tenantId: tenantId,
        personaId: personaId,
        usedAPI: tenantConfig ? true : false
    }
}];
