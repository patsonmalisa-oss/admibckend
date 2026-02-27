# CORS Configuration for ADMI Backend

This document outlines the CORS (Cross-Origin Resource Sharing) configuration for the ADMI backend services to enable proper frontend-backend communication.

## Overview

The ADMI application consists of:
- **Frontend**: Static HTML/JavaScript files served from various origins
- **Node.js Backend**: Serves API endpoints and proxies requests to Python service
- **Python Service**: Handles document extraction and processing

## CORS Configuration

### Allowed Origins

The following origins are configured to allow cross-origin requests:

```javascript
const allowedOrigins = [
  'https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app',
  'https://admfront-five.vercel.app',
  'http://localhost:3000',
  'http://localhost:3001',
  'http://localhost:5001'
];
```

### Allowed Methods

- GET
- POST
- PUT
- DELETE
- OPTIONS

### Allowed Headers

- Content-Type
- Authorization
- X-Requested-With

### Credentials

CORS is configured to allow credentials (cookies, authorization headers) to be included in cross-origin requests.

## Implementation

### Node.js Backend (server.js)

```javascript
const cors = require('cors');

const corsOptions = {
  origin: function (origin, callback) {
    const allowedOrigins = [
      'https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app',
      'https://admfront-five.vercel.app',
      'http://localhost:3000',
      'http://localhost:3001',
      'http://localhost:5001'
    ];
    
    // Allow requests with no origin (like mobile apps or curl requests)
    if (!origin) return callback(null, true);
    
    if (allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With']
};

app.use(cors(corsOptions));
```

### Python Service (langextract_service.py)

```python
from flask_cors import CORS

app = Flask(__name__)

# Configure CORS with specific allowed origins
CORS(app, resources={
    r"/*": {
        "origins": CORS_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True
    }
})
```

## Environment Variables

### Python Service

```bash
# CORS origins (comma-separated)
CORS_ORIGINS=https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app,https://admfront-five.vercel.app,http://localhost:3000,http://localhost:3001,http://localhost:5001
```

### Node.js Backend

CORS configuration is hardcoded in the server.js file for security reasons.

## Troubleshooting

### Common CORS Issues

1. **"CORS policy blocked" errors**
   - Ensure the frontend origin is in the allowed origins list
   - Check that the request includes proper headers

2. **File upload failures**
   - Verify that multipart/form-data requests are properly handled
   - Check that the proxy correctly forwards file uploads

3. **Authentication issues**
   - Ensure credentials are properly configured
   - Verify that authorization headers are allowed

### Testing CORS

Use the test-data-ingestion.html file to verify CORS configuration:

```bash
# Start Node.js backend
node server.js

# Start Python service
python langextract_service.py

# Open test-data-ingestion.html in browser
# Run the integration tests
```

### Debugging

Enable CORS debugging in development:

```javascript
// Add to server.js for debugging
app.use((req, res, next) => {
  console.log('CORS Debug:', {
    origin: req.headers.origin,
    method: req.method,
    url: req.url
  });
  next();
});
```

## Security Considerations

1. **Production Origins**: Only include trusted production domains
2. **Credentials**: Only enable credentials for trusted origins
3. **Headers**: Limit allowed headers to only what's necessary
4. **Methods**: Only allow HTTP methods that are actually used

## Deployment Notes

### Vercel Deployment

When deploying to Vercel, ensure that:
- The frontend and backend are properly configured
- CORS origins include the Vercel deployment URL
- Environment variables are set correctly

### Render Deployment

For Render deployments:
- Set CORS_ORIGINS environment variable
- Ensure both Node.js and Python services are running
- Verify that the proxy configuration is correct

## Future Enhancements

1. **Dynamic CORS**: Allow CORS configuration via environment variables
2. **Origin Validation**: Implement more sophisticated origin validation
3. **Logging**: Add comprehensive CORS request logging
4. **Security Headers**: Implement additional security headers (CSP, HSTS, etc.)