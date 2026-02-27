# ADMI Backend Integration Guide

This document provides a comprehensive guide for setting up and running the ADMI (African Development Models Initiative) backend services with proper frontend-backend communication.

## Overview

The ADMI application consists of three main components:

1. **Frontend**: Static HTML/JavaScript files for user interface
2. **Node.js Backend**: API server and proxy for Python service
3. **Python Service**: Document extraction and processing service

## Architecture

```
Frontend (HTML/JS)
    ↓ (HTTP requests)
Node.js Backend (Port 3001)
    ↓ (Proxy requests)
Python Service (Port 5001)
```

## Quick Start

### 1. Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Start Services

```bash
# Start Node.js backend
node server.js

# Start Python service (in a new terminal)
python langextract_service.py
```

### 3. Access Application

- **Main Application**: http://localhost:3001
- **Test Page**: http://localhost:3001/test-data-ingestion.html
- **AI Agent**: http://localhost:3001/ai-agent.html

## File Structure

```
backend/
├── server.js                    # Node.js backend server
├── langextract_service.py       # Python document processing service
├── ai-agent.html               # AI agent interface
├── test-data-ingestion.html    # Integration test page
├── test_integration.js         # Automated test script
├── CORS_CONFIGURATION.md       # CORS setup documentation
├── package.json                # Node.js dependencies
├── requirements.txt            # Python dependencies
└── README_INTEGRATION.md       # This file
```

## Service Configuration

### Node.js Backend (server.js)

- **Port**: 3001 (configurable via PORT environment variable)
- **Purpose**: Serves static files, provides API endpoints, proxies to Python service
- **Key Features**:
  - CORS configuration for cross-origin requests
  - Proxy middleware for Python service
  - Static file serving
  - Error handling

### Python Service (langextract_service.py)

- **Port**: 5001 (configurable via PYTHON_PORT environment variable)
- **Purpose**: Document extraction and processing
- **Key Features**:
  - PDF and CSV processing
  - AI-powered data extraction
  - Schema validation
  - Batch processing

## API Endpoints

### Node.js Backend

- `GET /api` - Health check
- `POST /api/prompt` - Process prompts
- `GET /python/*` - Proxy to Python service
- `GET /*` - Serve static files

### Python Service

- `GET /health` - Service health check
- `POST /process` - Process documents
- `POST /extract` - Extract data from content

## CORS Configuration

The application is configured to allow cross-origin requests from:

- `https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app`
- `https://admfront-five.vercel.app`
- `http://localhost:3000`
- `http://localhost:3001`
- `http://localhost:5001`

## Testing

### Manual Testing

1. **Open Test Page**: Navigate to `http://localhost:3001/test-data-ingestion.html`
2. **Run Tests**: Click the test buttons to verify service connectivity
3. **Check Results**: View test results in the browser

### Automated Testing

```bash
# Run integration tests
node test_integration.js

# Run with custom ports
node test_integration.js --node-port 3002 --python-port 5002

# View help
node test_integration.js --help
```

### Test Coverage

The integration tests verify:

- ✅ Node.js backend health
- ✅ Python service health
- ✅ Proxy functionality
- ✅ CORS configuration
- ✅ File upload handling
- ✅ Error handling
- ✅ Large file processing

## Environment Variables

### Node.js Backend

```bash
PORT=3001                    # Server port
NODE_ENV=production          # Environment mode
```

### Python Service

```bash
PYTHON_PORT=5001             # Python service port
PYTHON_HOST=0.0.0.0          # Python service host
UPLOAD_FOLDER=/tmp/uploads   # Upload directory
LOG_LEVEL=INFO               # Logging level
CORS_ORIGINS=...             # Allowed CORS origins (comma-separated)
```

## Deployment

### Local Development

1. Start both services
2. Access via localhost URLs
3. Use test pages for verification

### Production Deployment

#### Option 1: Render (Recommended)

1. **Deploy Node.js Backend**:
   - Connect GitHub repository
   - Set build command: `npm install`
   - Set start command: `node server.js`
   - Set environment variables

2. **Deploy Python Service**:
   - Create separate service
   - Set build command: `pip install -r requirements.txt`
   - Set start command: `python langextract_service.py`
   - Configure environment variables

3. **Update CORS Origins**:
   - Set CORS_ORIGINS to include your production URLs

#### Option 2: Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f
```

### Vercel Deployment

1. **Frontend**: Deploy HTML files to Vercel
2. **Backend**: Deploy Node.js service to Render
3. **Python**: Deploy Python service to Render
4. **CORS**: Update CORS origins in environment variables

## Troubleshooting

### Common Issues

#### 1. CORS Errors

**Problem**: "CORS policy blocked" errors in browser
**Solution**: 
- Verify CORS origins include your frontend URL
- Check that CORS is properly configured in both services
- Use test page to verify CORS configuration

#### 2. Service Unavailable

**Problem**: "Service unavailable" or connection errors
**Solution**:
- Verify both services are running
- Check port configurations
- Verify firewall settings

#### 3. File Upload Failures

**Problem**: File uploads fail or timeout
**Solution**:
- Check file size limits (15MB max)
- Verify proxy configuration
- Check Python service logs

#### 4. Authentication Issues

**Problem**: Authentication headers not working
**Solution**:
- Verify CORS allows credentials
- Check authorization header format
- Verify backend authentication logic

### Debug Mode

Enable debug logging:

```bash
# Node.js debug
DEBUG=* node server.js

# Python debug
LOG_LEVEL=DEBUG python langextract_service.py
```

### Log Locations

- **Node.js**: Console output
- **Python**: Console output
- **Browser**: Developer Tools > Console

## Security Considerations

### CORS Security

- Only allow trusted origins
- Limit allowed headers and methods
- Enable credentials only when necessary

### File Upload Security

- Validate file types (PDF, CSV only)
- Enforce file size limits (15MB)
- Sanitize file names
- Store uploads in secure directory

### API Security

- Rate limiting for API endpoints
- Input validation and sanitization
- Error handling without information leakage

## Performance Optimization

### File Processing

- Use batch processing for multiple files
- Implement file size limits
- Add progress indicators for long operations

### Caching

- Cache static files appropriately
- Consider caching API responses
- Use CDN for static assets

### Monitoring

- Monitor service health
- Track error rates
- Monitor resource usage

## Development Workflow

### Adding New Features

1. **Frontend Changes**: Update HTML/JavaScript files
2. **Backend Changes**: Update server.js or langextract_service.py
3. **Testing**: Run integration tests
4. **Documentation**: Update this README

### Code Style

- Use consistent indentation (2 spaces)
- Follow naming conventions
- Add comments for complex logic
- Use meaningful variable names

### Version Control

- Commit changes with descriptive messages
- Use feature branches for new functionality
- Test before merging to main branch

## Support

### Documentation

- [CORS Configuration](CORS_CONFIGURATION.md)
- [API Documentation](#api-endpoints)
- [Troubleshooting Guide](#troubleshooting)

### Testing Resources

- [Integration Test Script](test_integration.js)
- [Manual Test Page](test-data-ingestion.html)
- [Automated Test Suite](#automated-testing)

### Contact

For support and questions:
- Check the troubleshooting section
- Review test results
- Check service logs
- Verify configuration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request
5. Ensure all tests pass

## License

This project is licensed under the terms specified in the LICENSE file.

## Changelog

### v1.0.0
- Initial integration setup
- CORS configuration
- Proxy implementation
- Test suite creation
- Documentation

### Future Versions
- Enhanced error handling
- Performance optimizations
- Additional file formats
- Advanced AI features