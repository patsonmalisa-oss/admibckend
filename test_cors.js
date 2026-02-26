/**
 * CORS Test Script
 * 
 * This script tests the CORS configuration for the ADMI backend
 * to ensure it properly accepts requests from the frontend domain.
 */

const http = require('http');

// Test configuration
const TEST_CONFIG = {
    backendUrl: 'http://localhost:3001',
    frontendOrigin: 'https://admfront-ibzanzy6u-pmpanashe489-3815s-projects.vercel.app',
    testEndpoints: [
        '/',
        '/api/assistant',
        '/api/research-assistant',
        '/api/documents/extract'
    ]
};

function testCORS() {
    console.log('🧪 Testing CORS Configuration for ADMI Backend\n');
    console.log(`Backend URL: ${TEST_CONFIG.backendUrl}`);
    console.log(`Frontend Origin: ${TEST_CONFIG.frontendOrigin}\n`);

    TEST_CONFIG.testEndpoints.forEach((endpoint, index) => {
        setTimeout(() => {
            console.log(`Test ${index + 1}: ${endpoint}`);
            testEndpoint(endpoint);
        }, index * 1000);
    });
}

function testEndpoint(endpoint) {
    const options = {
        hostname: 'localhost',
        port: 3001,
        path: endpoint,
        method: 'OPTIONS',
        headers: {
            'Origin': TEST_CONFIG.frontendOrigin,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Content-Type,Authorization'
        }
    };

    const req = http.request(options, (res) => {
        console.log(`  Status: ${res.statusCode}`);
        console.log(`  Access-Control-Allow-Origin: ${res.headers['access-control-allow-origin'] || 'NOT SET'}`);
        console.log(`  Access-Control-Allow-Methods: ${res.headers['access-control-allow-methods'] || 'NOT SET'}`);
        console.log(`  Access-Control-Allow-Headers: ${res.headers['access-control-allow-headers'] || 'NOT SET'}`);
        console.log(`  Access-Control-Allow-Credentials: ${res.headers['access-control-allow-credentials'] || 'NOT SET'}`);
        
        if (res.statusCode === 204) {
            console.log('  ✅ OPTIONS request successful\n');
        } else {
            console.log('  ❌ OPTIONS request failed\n');
        }
    });

    req.on('error', (e) => {
        console.log(`  ❌ Request failed: ${e.message}\n`);
    });

    req.end();
}

// Run tests if this script is executed directly
if (require.main === module) {
    testCORS();
}

module.exports = { testCORS };