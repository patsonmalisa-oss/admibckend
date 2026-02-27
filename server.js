const express = require('express');
const path = require('path');
const axios = require('axios');
const cors = require('cors');
const app = express();

// Middleware to parse incoming JSON bodies
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS configuration
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

// Serve static files from the current directory
app.use(express.static(path.join(__dirname, '.')));

// Proxy middleware for Python service
const createProxyHandler = (targetUrl) => {
  return async (req, res) => {
    try {
      const url = `${targetUrl}${req.originalUrl}`;
      const method = req.method;
      const headers = { ...req.headers };
      
      // Remove host header to avoid conflicts
      delete headers.host;
      delete headers.origin;
      
      let response;
      
      if (method === 'GET') {
        response = await axios.get(url, { headers });
      } else if (method === 'POST') {
        if (req.is('multipart/form-data')) {
          // For file uploads, forward the entire request
          const FormData = require('form-data');
          const form = new FormData();
          
          // Add form fields
          Object.keys(req.body).forEach(key => {
            form.append(key, req.body[key]);
          });
          
          // Add files if any
          if (req.files) {
            Object.keys(req.files).forEach(key => {
              form.append(key, req.files[key].buffer, req.files[key].originalname);
            });
          }
          
          response = await axios.post(url, form, {
            headers: {
              ...form.getHeaders(),
              ...headers
            }
          });
        } else {
          response = await axios.post(url, req.body, { headers });
        }
      } else if (method === 'PUT') {
        response = await axios.put(url, req.body, { headers });
      } else if (method === 'DELETE') {
        response = await axios.delete(url, { headers });
      } else {
        return res.status(405).json({ error: 'Method not allowed' });
      }
      
      res.status(response.status).json(response.data);
    } catch (error) {
      console.error(`Proxy error for ${req.method} ${req.originalUrl}:`, error.message);
      
      if (error.response) {
        // Server responded with error status
        res.status(error.response.status).json({
          error: error.response.data?.error || 'Backend service error',
          details: error.response.data
        });
      } else if (error.request) {
        // Request was made but no response received
        res.status(503).json({
          error: 'Backend service unavailable',
          message: 'Unable to connect to the Python service'
        });
      } else {
        // Something else happened
        res.status(500).json({
          error: 'Proxy error',
          message: error.message
        });
      }
    }
  };
};

// Proxy routes for Python service
app.use('/python', createProxyHandler('http://localhost:5001'));

// API routes for Node.js backend
app.get('/api', (req, res) => {
  res.json({ message: 'Node.js backend is running' });
});

app.post('/api/prompt', async (req, res) => {
  try {
    const { prompt } = req.body;
    const backendUrl = 'https://admibckend-1.onrender.com';

    // Forward the prompt to the backend server
    const backendResponse = await axios.post(backendUrl, { prompt });

    // Send the response from the backend back to the frontend client
    res.json(backendResponse.data);
  } catch (error) {
    console.error('Error proxying to backend:', error.message);
    res.status(500).json({ error: 'Failed to communicate with the backend server.' });
  }
});

// Serve index.html for all routes (SPA support)
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Python service proxy: http://localhost:${PORT}/python`);
  console.log(`Node.js API: http://localhost:${PORT}/api`);
});
