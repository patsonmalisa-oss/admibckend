# ADMI Backend CORS Configuration

This document outlines the CORS (Cross-Origin Resource Sharing) configuration for the ADMI backend to enable communication with the frontend application.

## Overview

The ADMI backend has been configured to accept requests from specific frontend domains, ensuring secure cross-origin communication while maintaining development flexibility.

## Configured Origins

The following origins are allowed to make requests to the backend:

- `https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app` (Your primary frontend)
- `https://admfront-five.vercel.app` (Alternative frontend)
- `http://localhost:3000` (Development server)
- `http://localhost:3001` (Backend development)

## Backend Configuration

### Node.js Server (main.js)

The main backend server includes enhanced CORS configuration:

```javascript
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
```

### Python Service (langextract_service.py)

The Python document extraction service includes Flask-CORS configuration:

```python
# Configure CORS with specific allowed origins
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app",
            "https://admfront-five.vercel.app",
            "http://localhost:3000",
            "http://localhost:3001"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True
    }
})
```

## Available API Endpoints

The backend provides several endpoints that your frontend can communicate with:

### Authentication Endpoints
- `POST /api/signup` - User registration
- `POST /api/login` - User login
- Returns JWT tokens for authentication

### Survey Management
- `POST /api/create-survey` - Create new surveys
- `GET /api/surveys` - Retrieve all surveys

### AI Assistant Endpoints
- `POST /api/assistant` - General AI assistant chat
- `POST /api/research-assistant` - Research-focused AI assistant

### Document Processing
- `POST /api/documents/ingest` - Upload documents
- `POST /api/documents/extract` - Extract data from documents using prompts
- `POST /api/documents/analog-metadata` - Extract metadata from documents
- `POST /api/terminal/execute` - Execute data analysis commands

## Testing CORS Configuration

A test script is provided to verify the CORS configuration:

```bash
node test_cors.js
```

This script will test OPTIONS requests to various endpoints to ensure proper CORS headers are returned.

## Frontend Integration

To integrate with the backend from your frontend:

### 1. Authentication Flow
```javascript
// Login example
const response = await fetch('https://admibckend.onrender.com/api/login', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        email: 'user@example.com',
        password: 'password123'
    })
});

const data = await response.json();
// Store token for subsequent requests
localStorage.setItem('token', data.token);
```

### 2. Authenticated Requests
```javascript
// Example authenticated request
const response = await fetch('https://admibckend.onrender.com/api/surveys', {
    method: 'GET',
    headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
    }
});
```

### 3. Document Processing
```javascript
// Upload and process document
const formData = new FormData();
formData.append('file', documentFile);
formData.append('prompt', 'Extract all financial data from this document');

const response = await fetch('https://admibckend.onrender.com/api/documents/extract', {
    method: 'POST',
    body: formData
});

const result = await response.json();
```

## Environment Variables

For production deployment, ensure these environment variables are set:

```bash
# Backend configuration
JWT_SECRET=your-super-secret-jwt-key
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-chat
PYTHON_SERVICE_HOST=localhost
PYTHON_SERVICE_PORT=5001
PORT=3001

# Python service configuration
PYTHON_PORT=5001
```

## Security Considerations

1. **JWT Secret**: Always use a strong, unique JWT secret in production
2. **API Keys**: Store API keys securely and never expose them in frontend code
3. **HTTPS**: Ensure all production traffic uses HTTPS
4. **CORS**: The configuration allows specific origins only - do not use wildcard (*) in production

## Deployment Notes

### Render.com Deployment

1. **Backend Service**: Deploy `main.js` as a Node.js service
2. **Python Service**: Deploy `langextract_service.py` as a Python service
3. **Environment Variables**: Set all required environment variables in Render dashboard
4. **Health Checks**: Both services include health check endpoints (`/health`)

### Domain Configuration

- Backend URL: `https://admibckend.onrender.com`
- Python Service: `https://admibckend.onrender.com` (proxied through main backend)
- Frontend URL: `https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app`

## Troubleshooting

### Common Issues

1. **CORS Errors**: Ensure frontend origin matches exactly with configured origins
2. **Authentication Failures**: Verify JWT tokens are being sent correctly
3. **Document Processing**: Check that file uploads are properly formatted
4. **AI Assistant**: Verify DeepSeek API key is configured

### Debugging

1. Check browser developer console for CORS errors
2. Verify network requests include proper headers
3. Test endpoints directly using curl or Postman
4. Check server logs for error messages

## Support

For issues related to CORS configuration or backend integration:

1. Run the CORS test script: `node test_cors.js`
2. Check the server logs for detailed error messages
3. Verify environment variables are properly set
4. Ensure frontend and backend are using compatible protocols (HTTP/HTTPS)