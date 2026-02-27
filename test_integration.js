#!/usr/bin/env node

/**
 * Integration Test Script for ADMI Backend Services
 * 
 * This script tests the complete workflow from frontend to Python service
 * including CORS configuration, proxy functionality, and error handling.
 */

const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');
const path = require('path');

// Configuration
const CONFIG = {
  nodePort: process.env.NODE_PORT || 3001,
  pythonPort: process.env.PYTHON_PORT || 5001,
  nodeUrl: `http://localhost:${process.env.NODE_PORT || 3001}`,
  pythonUrl: `http://localhost:${process.env.PYTHON_PORT || 5001}`,
  proxyUrl: `http://localhost:${process.env.NODE_PORT || 3001}/python`,
  testTimeout: 5000
};

// Test results
const results = {
  passed: 0,
  failed: 0,
  tests: []
};

/**
 * Test runner utility
 */
class TestRunner {
  static async runTest(name, testFn) {
    console.log(`\n🧪 Running: ${name}`);
    
    try {
      await testFn();
      console.log(`✅ PASSED: ${name}`);
      results.passed++;
      results.tests.push({ name, status: 'PASSED', error: null });
    } catch (error) {
      console.log(`❌ FAILED: ${name}`);
      console.log(`   Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name, status: 'FAILED', error: error.message });
    }
  }

  static async delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Test Suite
 */
async function runTests() {
  console.log('🚀 Starting ADMI Backend Integration Tests');
  console.log('==========================================');

  // Check if services are running
  await TestRunner.runTest('Node.js Backend Health Check', async () => {
    const response = await axios.get(`${CONFIG.nodeUrl}/api`, { timeout: CONFIG.testTimeout });
    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }
    if (!response.data.message) {
      throw new Error('No message in response');
    }
  });

  await TestRunner.runTest('Python Service Health Check', async () => {
    const response = await axios.get(`${CONFIG.pythonUrl}/health`, { timeout: CONFIG.testTimeout });
    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }
    if (!response.data.status) {
      throw new Error('No status in response');
    }
  });

  await TestRunner.runTest('Proxy Health Check', async () => {
    const response = await axios.get(`${CONFIG.proxyUrl}/health`, { timeout: CONFIG.testTimeout });
    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }
    if (!response.data.status) {
      throw new Error('No status in response');
    }
  });

  await TestRunner.runTest('CORS Headers Check', async () => {
    const response = await axios.options(`${CONFIG.proxyUrl}/process`, {
      headers: {
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Content-Type'
      },
      timeout: CONFIG.testTimeout
    });
    
    const corsHeaders = response.headers;
    if (!corsHeaders['access-control-allow-origin']) {
      throw new Error('Missing Access-Control-Allow-Origin header');
    }
    if (!corsHeaders['access-control-allow-methods']) {
      throw new Error('Missing Access-Control-Allow-Methods header');
    }
  });

  await TestRunner.runTest('File Upload Proxy Test', async () => {
    // Create a test CSV file
    const testCsv = 'Name,Age,City\nJohn Doe,30,New York\nJane Smith,25,Los Angeles';
    const testFile = path.join(__dirname, 'test_file.csv');
    fs.writeFileSync(testFile, testCsv);

    try {
      const formData = new FormData();
      formData.append('file', fs.createReadStream(testFile));
      formData.append('prompt', 'Extract all data');

      const response = await axios.post(`${CONFIG.proxyUrl}/process`, formData, {
        headers: {
          ...formData.getHeaders(),
          'Origin': 'http://localhost:3000'
        },
        timeout: CONFIG.testTimeout * 2
      });

      if (response.status !== 200) {
        throw new Error(`Expected 200, got ${response.status}`);
      }
      
      if (!response.data.success && !response.data.error) {
        throw new Error('Invalid response format');
      }

      // Clean up
      fs.unlinkSync(testFile);
    } catch (error) {
      // Clean up on error
      if (fs.existsSync(testFile)) {
        fs.unlinkSync(testFile);
      }
      throw error;
    }
  });

  await TestRunner.runTest('Error Handling Test', async () => {
    try {
      const response = await axios.post(`${CONFIG.proxyUrl}/process`, {
        prompt: 'Test prompt'
      }, {
        timeout: CONFIG.testTimeout
      });
      
      // Should return an error since no file was provided
      if (response.status === 200 && response.data.success) {
        throw new Error('Expected error for missing file');
      }
    } catch (error) {
      // This is expected - the service should handle missing files gracefully
      if (error.response && error.response.status === 500) {
        throw new Error('Internal server error - service not handling errors properly');
      }
    }
  });

  await TestRunner.runTest('Large File Handling', async () => {
    // Create a larger test file (simulate 1MB)
    const largeContent = 'x'.repeat(1024 * 1024); // 1MB of data
    const largeFile = path.join(__dirname, 'large_test_file.txt');
    fs.writeFileSync(largeFile, largeContent);

    try {
      const formData = new FormData();
      formData.append('file', fs.createReadStream(largeFile));
      formData.append('prompt', 'Test large file');

      const response = await axios.post(`${CONFIG.proxyUrl}/process`, formData, {
        headers: formData.getHeaders(),
        timeout: CONFIG.testTimeout * 5
      });

      // Should handle large files gracefully
      if (response.status !== 200) {
        throw new Error(`Expected 200, got ${response.status}`);
      }

      // Clean up
      fs.unlinkSync(largeFile);
    } catch (error) {
      // Clean up on error
      if (fs.existsSync(largeFile)) {
        fs.unlinkSync(largeFile);
      }
      throw error;
    }
  });

  // Print results
  printResults();
}

function printResults() {
  console.log('\n' + '='.repeat(50));
  console.log('📊 TEST RESULTS');
  console.log('='.repeat(50));
  
  results.tests.forEach(test => {
    const statusIcon = test.status === 'PASSED' ? '✅' : '❌';
    console.log(`${statusIcon} ${test.name}`);
    if (test.error) {
      console.log(`   Error: ${test.error}`);
    }
  });

  console.log('\n' + '='.repeat(50));
  console.log(`Total Tests: ${results.tests.length}`);
  console.log(`Passed: ${results.passed}`);
  console.log(`Failed: ${results.failed}`);
  
  if (results.failed === 0) {
    console.log('\n🎉 All tests passed! Integration is working correctly.');
    process.exit(0);
  } else {
    console.log('\n⚠️  Some tests failed. Please check the errors above.');
    process.exit(1);
  }
}

// CLI interface
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.includes('--help') || args.includes('-h')) {
    console.log(`
ADMI Backend Integration Test

Usage: node test_integration.js [options]

Options:
  --help, -h     Show this help message
  --node-port    Node.js backend port (default: 3001)
  --python-port  Python service port (default: 5001)
  --timeout      Test timeout in ms (default: 5000)

Examples:
  node test_integration.js
  node test_integration.js --node-port 3002 --python-port 5002
    `);
    process.exit(0);
  }

  // Parse command line arguments
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i];
    const value = args[i + 1];
    
    if (key === '--node-port') {
      CONFIG.nodePort = parseInt(value);
      CONFIG.nodeUrl = `http://localhost:${CONFIG.nodePort}`;
      CONFIG.proxyUrl = `${CONFIG.nodeUrl}/python`;
    } else if (key === '--python-port') {
      CONFIG.pythonPort = parseInt(value);
      CONFIG.pythonUrl = `http://localhost:${CONFIG.pythonPort}`;
    } else if (key === '--timeout') {
      CONFIG.testTimeout = parseInt(value);
    }
  }

  console.log('Configuration:', {
    nodeUrl: CONFIG.nodeUrl,
    pythonUrl: CONFIG.pythonUrl,
    proxyUrl: CONFIG.proxyUrl,
    timeout: CONFIG.testTimeout
  });

  runTests().catch(error => {
    console.error('Test runner error:', error);
    process.exit(1);
  });
}

module.exports = { runTests, CONFIG, TestRunner };