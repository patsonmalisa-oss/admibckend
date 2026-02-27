// To run this backend server, you need Node.js and several packages installed.
// Open a terminal in the project root directory and run:
// npm install busboy bcryptjs jsonwebtoken
// node workflows/main.js
// The server will start on http://localhost:3000.

const http = require('http');
const https = require('https');
const { URL } = require('url');
const busboy = require('busboy');
const FormData = require('form-data');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { mockExtractFromDocuments } = require('./mockExtraction');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// In-memory storage
const users = {};
const surveys = [];
const jobs = [];
const chatHistories = {};
const researchChatHistories = {}; // Separate history for the research assistant
const sessionFiles = []; 

// Environment Configuration
const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-change-this-in-render';
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || "";
const DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL || "deepseek-chat";
const PYTHON_SERVICE_HOST = process.env.PYTHON_SERVICE_HOST || 'localhost';
const PYTHON_SERVICE_PORT = process.env.PYTHON_SERVICE_PORT || 5001;
const PYTHON_SERVICE_URL = `http://${PYTHON_SERVICE_HOST}:${PYTHON_SERVICE_PORT}/process`;

// Validate required environment variables
if (!process.env.JWT_SECRET && process.env.NODE_ENV === 'production') {
    console.warn('WARNING: JWT_SECRET not set. Using default insecure key. Set JWT_SECRET environment variable.');
}
if (!DEEPSEEK_API_KEY && process.env.NODE_ENV === 'production') {
    console.warn('WARNING: DEEPSEEK_API_KEY not set. DeepSeek features will not work.');
}

const server = http.createServer((req, res) => {
    const reqUrl = new URL(req.url, `http://${req.headers.host}`);

    // Allow specific frontend domains for better security
    const allowedOrigins = [
        'https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app',
        'https://admfront-five.vercel.app',
        'http://localhost:3000',
        'http://localhost:3001'
    ];
    
    const origin = req.headers.origin;
    if (allowedOrigins.includes(origin)) {
        res.setHeader('Access-Control-Allow-Origin', origin);
    } else {
        // For development or other trusted origins
        res.setHeader('Access-Control-Allow-Origin', '*');
    }
    
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS, PUT, DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
    res.setHeader('Access-Control-Allow-Credentials', 'true');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    // --- API ROUTING ---

    // Root Endpoint (Health Check)
    if (reqUrl.pathname === '/' && req.method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('ADMI Backend Server is Running');
    }

    // --- Docs with Umbuzo Endpoints ---

    // 1. Document Ingestion (/api/documents/ingest)
    else if (reqUrl.pathname === '/api/documents/ingest' && req.method === 'POST') {
        let bb;
        try {
            bb = busboy({ headers: req.headers });
        } catch (err) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify({ error: 'Invalid upload request.' }));
        }

        const filePromises = [];

        bb.on('file', (fieldname, file, filename, encoding, mimetype) => {
            const chunks = [];
            file.on('data', (chunk) => chunks.push(chunk));
            file.on('end', () => {
                let safeFilename = "unknown_file";
                if (typeof filename === 'string') safeFilename = filename;
                else if (typeof filename === 'object' && filename?.filename) safeFilename = filename.filename;
                safeFilename = path.basename(safeFilename);

                const buffer = Buffer.concat(chunks);
                const fileData = {
                    filename: safeFilename,
                    mimetype: mimetype,
                    content: buffer.toString('base64'),
                    size: buffer.length
                };
                sessionFiles.push(fileData);
                filePromises.push(fileData);
            });
        });

        bb.on('finish', () => {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ 
                success: true, 
                files: filePromises.map(f => ({ filename: f.filename, size: f.size, content: f.content })) 
            }));
        });

        req.pipe(bb);
    }

    // 2. Document Extraction (/api/documents/extract)
    else if (reqUrl.pathname === '/api/documents/extract' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', async () => {
            try {
                const { documentContent, prompt, outputFormat, filename } = JSON.parse(body);
                
                let buffer;
                let safeFilename = filename || "document.pdf";

                if (documentContent) {
                    buffer = Buffer.from(documentContent, 'base64');
                } else if (filename) {
                    const found = sessionFiles.find(f => f.filename === filename);
                    if (found) buffer = Buffer.from(found.content, 'base64');
                }

                if (!buffer) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'No document content provided or file not found.' }));
                }

                // Create FormData for the Python service
                const formData = new FormData();
                formData.append('file', new Blob([buffer], { type: 'application/pdf' }), safeFilename);
                formData.append('prompt', prompt);

                try {
                    // Make HTTP request to Python LangExtract service
                    const pythonServiceRes = await fetch(PYTHON_SERVICE_URL, {
                        method: 'POST',
                        body: formData,
                    });

                    const pythonResult = await pythonServiceRes.json();

                    if (!pythonServiceRes.ok || pythonResult.error) {
                        throw new Error(pythonResult.error || pythonServiceRes.statusText);
                    }

                    // Normalize output structure
                    const data = pythonResult.extractions || pythonResult.data || pythonResult;
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ data: data, outputFormat: outputFormat }));

                } catch (fetchError) {
                    console.error("Python service unavailable or failed:", fetchError.message);
                    console.log("Falling back to mock extraction...");
                    
                    // Fallback to mock extraction
                    const mockRes = mockExtractFromDocuments({
                        files: [{ fileName: safeFilename, buffer: buffer, mimetype: 'application/pdf' }],
                        csvText: null,
                        prompt: prompt,
                        outputFormat: outputFormat || 'json',
                        fieldHints: []
                    });
                    
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ 
                        data: mockRes.data, 
                        outputFormat: outputFormat,
                        warning: "Used mock extraction because AI service was unavailable."
                    }));
                }

            } catch (e) {
                console.error("Error in /api/documents/extract:", e);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Internal Server Error during document processing.' }));
            }
        });
    }

    // 3. Analog Metadata (/api/documents/analog-metadata)
    else if (reqUrl.pathname === '/api/documents/analog-metadata' && req.method === 'POST') {
        let bb;
        try { bb = busboy({ headers: req.headers }); } catch (e) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify({ error: 'Invalid request' }));
        }
        const files = [];
        bb.on('file', (fieldname, file, filename) => {
            let safeName = typeof filename === 'object' ? filename.filename : filename;
            files.push({ filename: safeName, summary: 'Uploaded successfully' });
            file.resume();
        });
        bb.on('finish', () => {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ files }));
        });
        req.pipe(bb);
    }

    // 4. Data Terminal (/api/terminal/execute)
    else if (reqUrl.pathname === '/api/terminal/execute' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', () => {
            try {
                const { csvData, command } = JSON.parse(body);
                if (!csvData || !command) throw new Error('Missing data');

                const rows = csvData.trim().split('\n').map(r => r.split(',').map(c => c.trim()));
                const headers = rows[0];
                const data = rows.slice(1);
                const colIndex = (name) => headers.indexOf(name);

                let response = { textOutput: '', chartData: null, command: '' };

                if (command.startsWith('head')) {
                    response.textOutput = rows.slice(0, 6).map(r => r.join(', ')).join('\n');
                } else if (command.startsWith('describe')) {
                    let stats = [];
                    headers.forEach((h, i) => {
                        const vals = data.map(r => parseFloat(r[i])).filter(v => !isNaN(v));
                        if (vals.length > 0) {
                            const sum = vals.reduce((a, b) => a + b, 0);
                            const avg = sum / vals.length;
                            const min = Math.min(...vals);
                            const max = Math.max(...vals);
                            stats.push(`${h}: Count=${vals.length}, Mean=${avg.toFixed(2)}, Min=${min}, Max=${max}`);
                        }
                    });
                    response.textOutput = stats.join('\n');
                } else if (command.includes('linear regression')) {
                    const parts = command.split(' ');
                    const yCol = parts[parts.indexOf('on') + 1];
                    const xCol = parts[parts.indexOf('vs') + 1];
                    const xi = colIndex(xCol);
                    const yi = colIndex(yCol);
                    
                    if (xi === -1 || yi === -1) {
                        response.textOutput = `Columns not found. Available: ${headers.join(', ')}`;
                    } else {
                        const xVals = [], yVals = [];
                        data.forEach(r => {
                            const x = parseFloat(r[xi]), y = parseFloat(r[yi]);
                            if (!isNaN(x) && !isNaN(y)) { xVals.push(x); yVals.push(y); }
                        });
                        
                        const n = xVals.length;
                        const sumX = xVals.reduce((a, b) => a + b, 0);
                        const sumY = yVals.reduce((a, b) => a + b, 0);
                        const sumXY = xVals.reduce((a, b, i) => a + b * yVals[i], 0);
                        const sumXX = xVals.reduce((a, b) => a + b * b, 0);
                        
                        const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
                        const intercept = (sumY - slope * sumX) / n;
                        
                        response.textOutput = `Linear Regression: Y = ${slope.toFixed(4)}X + ${intercept.toFixed(4)}`;
                        response.command = 'linear_regression';
                        response.chartData = { x: xVals, y: yVals, slope, intercept };
                    }
                } else if (command.includes('histogram')) {
                    const col = command.split('of')[1].trim();
                    const ci = colIndex(col);
                    if (ci === -1) {
                        response.textOutput = `Column '${col}' not found.`;
                    } else {
                        const vals = data.map(r => parseFloat(r[ci])).filter(v => !isNaN(v));
                        const min = Math.min(...vals);
                        const max = Math.max(...vals);
                        const binCount = 10;
                        const binSize = (max - min) / binCount;
                        const bins = new Array(binCount).fill(0);
                        const labels = [];
                        
                        for (let i = 0; i < binCount; i++) {
                            labels.push((min + i * binSize).toFixed(1));
                        }
                        
                        vals.forEach(v => {
                            let bin = Math.floor((v - min) / binSize);
                            if (bin === binCount) bin--;
                            bins[bin]++;
                        });
                        
                        response.textOutput = `Histogram for ${col} generated.`;
                        response.command = 'histogram';
                        response.chartData = { labels, values: bins, column: col };
                    }
                } else {
                    response.textOutput = "Unknown command. Try 'head', 'describe', 'linear regression on Y vs X', or 'histogram of Col'.";
                }

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(response));

            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: e.message }));
            }
        });
    }

    // --- Existing Endpoints ---
    else if (reqUrl.pathname === '/api/signup' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', async () => {
            try {
                const { name, email, password } = JSON.parse(body);
                if (!name || !email || !password) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Name, email, and password are required.' }));
                }
                if (users[email]) {
                    res.writeHead(409, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'User with this email already exists.' }));
                }

                const salt = await bcrypt.genSalt(10);
                const hashedPassword = await bcrypt.hash(password, salt);

                users[email] = { name, email, password: hashedPassword, createdAt: new Date() };
                console.log('New user registered:', users[email]);

                res.writeHead(201, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ message: 'User created successfully.' }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid request data.' }));
            }
        });
    }
    else if (reqUrl.pathname === '/api/login' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', async () => {
            try {
                const { email, password } = JSON.parse(body);
                const user = users[email];

                if (!user || !await bcrypt.compare(password, user.password)) {
                    res.writeHead(401, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Invalid email or password.' }));
                }

                const token = jwt.sign({ email: user.email, name: user.name }, JWT_SECRET, { expiresIn: '1h' });

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ message: 'Login successful.', token, name: user.name }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid request data.' }));
            }
        });
    }
    else if (reqUrl.pathname === '/api/create-survey' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', () => {
            try {
                const surveyData = JSON.parse(body);
                
                if (!surveyData.title || !surveyData.questions || surveyData.questions.length === 0) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Survey must have a title and at least one question.' }));
                }

                const newSurvey = {
                    id: `survey_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                    ...surveyData,
                    createdAt: new Date().toISOString(),
                    status: 'scheduled'
                };
                surveys.push(newSurvey);

                console.log('New survey created:', newSurvey);
                console.log('Total surveys in memory:', surveys.length);

                res.writeHead(201, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ message: 'Survey created successfully!', surveyId: newSurvey.id }));

            } catch (error) {
                console.error('Error processing survey creation request:', error);
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid survey data format.' }));
            }
        });
    }
    else if (reqUrl.pathname === '/api/surveys' && req.method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(surveys));
    }
    else if (reqUrl.pathname === '/api/assistant' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', async () => {
            try {
                const { userId, message } = JSON.parse(body);

                if (!userId || !message) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Missing userId or message.' }));
                }

                if (!chatHistories[userId]) {
                    chatHistories[userId] = [
                        { role: 'system', content: 'You are a helpful assistant for the African Development Models Initiative application. Your goal is to guide users on how to use the app. You know about the following pages: Home, About Us, Survey Forms, Data Ingestion & Analysis, Research Dashboard, and AI Agent. Be concise and helpful.' }
                    ];
                }
                chatHistories[userId].push({ role: 'user', content: message });

                const deepseekRequestData = JSON.stringify({
                    model: DEEPSEEK_MODEL,
                    messages: chatHistories[userId],
                    max_tokens: 250,
                });

                const options = {
                    hostname: 'api.deepseek.com',
                    path: '/v1/chat/completions',
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${DEEPSEEK_API_KEY}`,
                    }
                };

                const deepseekReq = https.request(options, (deepseekRes) => {
                    let deepseekResBody = '';
                    deepseekRes.on('data', (chunk) => deepseekResBody += chunk);
                    deepseekRes.on('end', () => {
                        try {
                            const result = JSON.parse(deepseekResBody);
                            const reply = result.choices[0].message.content;
                            
                            chatHistories[userId].push({ role: 'assistant', content: reply });

                            res.writeHead(200, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({ reply: reply }));
                        } catch (e) {
                            res.writeHead(500, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({ error: 'Failed to parse DeepSeek response.' }));
                        }
                    });
                });

                deepseekReq.on('error', (e) => {
                    console.error('Error calling DeepSeek API:', e);
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Failed to communicate with DeepSeek API.' }));
                });

                deepseekReq.write(deepseekRequestData);
                deepseekReq.end();

            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON.' }));
            }
        });
    }
    else if (reqUrl.pathname === '/api/research-assistant' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => body += chunk.toString());
        req.on('end', async () => {
            try {
                const { message, contextId, userId = 'default_user' } = JSON.parse(body);

                if (!message) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Message is required.' }));
                }

                let contextPrompt = "You are an expert research assistant. Your goal is to provide advice on survey design, question phrasing, and data analysis strategies. Be insightful and clear.";
                if (contextId) {
                    const survey = surveys.find(s => s.id === contextId);
                    if (survey) {
                        contextPrompt += `\n\nThe user has provided the following survey as context. Use it to inform your advice:\n${JSON.stringify(survey, null, 2)}`;
                    }
                }

                if (!researchChatHistories[userId]) {
                    researchChatHistories[userId] = [{ role: 'system', content: contextPrompt }];
                }
                researchChatHistories[userId].push({ role: 'user', content: message });

                const deepseekRequestData = JSON.stringify({
                    model: DEEPSEEK_MODEL,
                    messages: researchChatHistories[userId],
                    max_tokens: 500,
                });

                const options = {
                    hostname: 'api.deepseek.com',
                    path: '/v1/chat/completions',
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${DEEPSEEK_API_KEY}` }
                };

                const deepseekReq = https.request(options, (deepseekRes) => {
                    let deepseekResBody = '';
                    deepseekRes.on('data', (chunk) => deepseekResBody += chunk);
                    deepseekRes.on('end', () => {
                        try {
                            const result = JSON.parse(deepseekResBody);
                            const reply = result.choices[0].message.content;
                            researchChatHistories[userId].push({ role: 'assistant', content: reply });
                            res.writeHead(200, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({ reply }));
                        } catch (e) {
                            res.writeHead(500, { 'Content-Type': 'application/json' });
                            res.end(JSON.stringify({ error: 'Failed to parse DeepSeek response.' }));
                        }
                    });
                });
                deepseekReq.on('error', (e) => {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Failed to communicate with DeepSeek API.' }));
                });
                deepseekReq.write(deepseekRequestData);
                deepseekReq.end();

            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON.' }));
            }
        });
    }
    // Fallback for other routes
    else {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
    }
});

const PORT = process.env.PORT || 3001;
const NODE_ENV = process.env.NODE_ENV || 'development';
const serverInstance = server.listen(PORT, () => {
    console.log(`\n${'='.repeat(60)}`);
    console.log('ADMI Backend Server Started');
    console.log(`${'='.repeat(60)}`);
    console.log(`Port: ${PORT}`);
    console.log(`Environment: ${NODE_ENV}`);
    console.log(`Python service: ${PYTHON_SERVICE_URL}`);
    console.log(`${'='.repeat(60)}\n`);
});

serverInstance.on('error', (e) => {
    if (e.code === 'EADDRINUSE') {
        console.error(`Error: Port ${PORT} is already in use.`);
        process.exit(1);
    } else {
        console.error('An error occurred:', e);
        process.exit(1);
    }
});
