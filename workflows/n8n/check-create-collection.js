// Check if collection exists, create if not
const item = $input.first();
const collectionName = item.json.collectionName;

console.log(`Checking if collection ${collectionName} exists...`);

let collectionExists = false;
try {
    const checkResponse = await this.helpers.httpRequest({
        method: 'GET',
        url: `http://qdrant:6333/collections/${collectionName}`,
        json: true
    });
    collectionExists = true;
    console.log(`Collection ${collectionName} exists`);
} catch (error) {
    // 404 means collection doesn't exist - this is expected
    console.log(`Collection ${collectionName} not found, will create it`);
    collectionExists = false;
}

// Create collection if it doesn't exist
if (!collectionExists) {
    console.log(`Creating collection ${collectionName}...`);

    const createResponse = await this.helpers.httpRequest({
        method: 'PUT',
        url: `http://qdrant:6333/collections/${collectionName}`,
        body: {
            vectors: {
                size: 768,
                distance: 'Cosine'
            }
        },
        json: true
    });

    console.log(`Collection created successfully:`, createResponse);
}

// Pass through original data
return [item];
