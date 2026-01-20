// MCP Layer: Intelligent Model Selection
const item = $input.first();

// Get query from Extract Query node (earlier in workflow)
const extractNode = $('Extract Query').first();
const query = (extractNode?.json?.query || item.json?.query || '').toLowerCase();
const tenantId = extractNode?.json?.tenantId || item.json?.tenantId;

// Model capabilities
const models = {
    'llama3.2:1b': {
        speed: 'fast',        // 3-5 seconds
        reasoning: 'basic',
        memory: 'low',
        useCase: 'Simple factual queries, inventory lookups'
    },
    'llama3.2:latest': {
        speed: 'medium',      // 20-25 seconds
        reasoning: 'good',
        memory: 'medium',
        useCase: 'Complex comparisons, recommendations'
    },
    'phi3:mini': {
        speed: 'slow',        // 30+ seconds
        reasoning: 'excellent',
        memory: 'medium',
        useCase: 'Deep analysis, mathematical reasoning'
    }
};

// Query analysis patterns
const queryPatterns = {
    // Simple - Fast model (llama3.2:1b)
    simple: {
        keywords: ['what', 'list', 'show', 'price', 'cost', 'stock', 'available', 'have', 'tell me'],
        patterns: [
            /what (is|are) (the )?price/i,
            /how much (does|do|is|are)/i,
            /do you have/i,
            /what .* available/i,
            /show me/i,
            /list (all|the)/i
        ]
    },

    // Medium - Medium model (llama3.2:latest)
    medium: {
        keywords: ['compare', 'difference', 'recommend', 'suggest', 'better', 'best', 'versus', 'vs'],
        patterns: [
            /compare .* (and|with|to)/i,
            /what (is|are) (the )?difference/i,
            /which (is|are) better/i,
            /recommend .* for/i,
            /should i (buy|get|choose)/i
        ]
    },

    // Complex - Best model (phi3:mini)
    complex: {
        keywords: ['calculate', 'compute', 'analyze', 'optimize', 'why', 'explain how', 'reason'],
        patterns: [
            /calculate (total|cost|savings)/i,
            /how many .* (needed|required)/i,
            /optimize .* for/i,
            /explain (why|how)/i,
            /what if .* (change|increase|decrease)/i
        ]
    }
};

// Scoring function
function analyzeQuery(query) {
    let scores = { simple: 0, medium: 0, complex: 0 };

    // Check keywords
    for (const [level, data] of Object.entries(queryPatterns)) {
        for (const keyword of data.keywords) {
            if (query.includes(keyword)) {
                scores[level] += 1;
            }
        }

        // Check regex patterns (worth more)
        for (const pattern of data.patterns) {
            if (pattern.test(query)) {
                scores[level] += 2;
            }
        }
    }

    return scores;
}

// Declare variables
let selectedModel = 'llama3.2:1b';
let reason = 'Default fast model';
let scores = { simple: 0, medium: 0, complex: 0 };

// Analyze query (if empty, use default)
if (!query || query.trim() === '') {
    console.log('Empty query - using default fast model');
    selectedModel = 'llama3.2:1b';
    reason = 'Empty query - using default fast model';
} else {
    scores = analyzeQuery(query);
    console.log('Query analysis scores:', scores);

    // Select model based on scores
    // phi3 only for VERY complex queries (score >= 3)
    if (scores.complex >= 3) {
        selectedModel = 'phi3:mini';
        reason = 'Very complex query detected - using best reasoning model';
    } else if (scores.complex > 0 || (scores.medium > scores.simple && scores.medium > 0)) {
        // Use llama3.2:3b for moderately complex queries
        selectedModel = 'llama3.2:latest';
        reason = scores.complex > 0 ? 'Complex query - using 3B model' : 'Medium complexity - using balanced model';
    } else {
        selectedModel = 'llama3.2:1b';
        reason = 'Simple query - using fast model';
    }

    // Query length heuristic
    const wordCount = query.split(' ').length;
    if (wordCount > 20 && selectedModel === 'llama3.2:1b') {
        selectedModel = 'llama3.2:latest';
        reason = 'Long query detected - upgraded to medium model';
    }
}

console.log(`Selected model: ${selectedModel}`);
console.log(`Reason: ${reason}`);
console.log(`Model info:`, models[selectedModel]);

return [{
    json: {
        ...item.json,
        selectedModel: selectedModel,
        modelSelectionReason: reason,
        modelCapabilities: models[selectedModel],
        queryScores: scores
    }
}];
