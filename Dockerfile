# Multi-stage Dockerfile for ADMI Backend
# Stage 1: Python Service (LangExtract)
FROM python:3.11-slim as python-service

# Set working directory
WORKDIR /app/python-service

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python service files
COPY langextract_service.py .
COPY temp_uploads 

# Expose Python service port
EXPOSE 5001

# Start Python service
CMD ["python", "langextract_service.py"]

# Stage 2: Node.js Backend
FROM node:20-slim as node-backend

# Set working directory
WORKDIR /app/node-backend

# Copy package files
COPY package.json ./

# Install Node.js dependencies
RUN npm install

# Copy Node.js backend files
COPY main.js .
COPY workflows

# Expose Node.js service port
EXPOSE 3001

# Start Node.js backend
CMD ["node", "main.js"]

# Stage 3: Combined Service (Production)
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python service files
COPY langextract_service.py .
COPY temp_uploads/ ./temp_uploads/

# Copy Node.js files
COPY package.json ./
RUN npm install
COPY main.js .
COPY workflows


# Create uploads directory
RUN mkdir -p temp_uploads

# Expose ports
EXPOSE 3001 5001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3001/ || exit 1

# Start both services

CMD ["sh", "-c", "python langextract_service.py & node main.js"]


