#!/bin/bash

# ADMI Backend Deployment Script
# This script helps deploy the ADMI Backend to Render.com

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="admibackend"
PYTHON_SERVICE_NAME="admipython"
DOCKER_IMAGE_NAME="admibackend"
PYTHON_IMAGE_NAME="admipython"
RENDER_API_URL="https://api.render.com"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_warning "Docker Compose is not installed. Some features may not work."
    fi
    
    # Check if render CLI is installed (optional)
    if command -v render &> /dev/null; then
        log_info "Render CLI found"
    else
        log_warning "Render CLI not found. You can install it from: https://render.com/docs/cli"
    fi
    
    log_success "Prerequisites check completed"
}

build_images() {
    log_info "Building Docker images..."
    
    # Build main backend image
    log_info "Building main backend image..."
    docker build -t $DOCKER_IMAGE_NAME .
    
    # Build Python service image
    log_info "Building Python service image..."
    docker build --target python-service -t $PYTHON_IMAGE_NAME .
    
    log_success "Docker images built successfully"
}

test_locally() {
    log_info "Testing locally with docker-compose..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose down -v
        docker-compose up -d
        
        log_info "Waiting for services to start..."
        sleep 10
        
        # Test Node.js backend
        if curl -f http://localhost:3001/ > /dev/null 2>&1; then
            log_success "Node.js backend is running on http://localhost:3001"
        else
            log_error "Node.js backend is not responding"
            docker-compose logs node-backend
        fi
        
        # Test Python service
        if curl -f http://localhost:5001/health > /dev/null 2>&1; then
            log_success "Python service is running on http://localhost:5001"
        else
            log_error "Python service is not responding"
            docker-compose logs python-service
        fi
        
        log_info "Local testing completed. Services are running."
        log_info "To stop services, run: docker-compose down -v"
    else
        log_warning "Docker Compose not available. Skipping local test."
    fi
}

deploy_to_render() {
    log_info "Deploying to Render.com..."
    
    # Check if render CLI is available
    if command -v render &> /dev/null; then
        log_info "Using Render CLI for deployment..."
        
        # Login to Render (if not already logged in)
        if ! render whoami &> /dev/null; then
            log_info "Please log in to Render.com..."
            render login
        fi
        
        # Deploy using render.yaml
        render deploy --service-file render.yaml
        
        log_success "Deployment initiated via Render CLI"
    else
        log_info "Render CLI not available. Please deploy manually:"
        log_info "1. Go to https://dashboard.render.com/"
        log_info "2. Create a new Web Service"
        log_info "3. Connect your GitHub repository"
        log_info "4. Use the following settings:"
        log_info "   - Build Command: docker build -t admibackend ."
        log_info "   - Start Command: docker run -p 10000:3001 -p 5001:5001 admibackend"
        log_info "   - Health Check Path: /"
        log_info "5. Set environment variables:"
        log_info "   - NODE_ENV=production"
        log_info "   - PORT=10000"
        log_info "   - PYTHON_SERVICE_HOST=localhost"
        log_info "   - PYTHON_SERVICE_PORT=5001"
        log_info "   - JWT_SECRET=<your-secret-key>"
        log_info "   - DEEPSEEK_API_KEY=<your-api-key>"
        log_info "   - DEEPSEEK_MODEL=deepseek-chat"
    fi
}

show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  build     Build Docker images only"
    echo "  test      Test locally with docker-compose"
    echo "  deploy    Deploy to Render.com"
    echo "  full      Build, test locally, and deploy (default)"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build    # Build images only"
    echo "  $0 test     # Test locally"
    echo "  $0          # Full deployment process"
}

# Main execution
main() {
    case "${1:-full}" in
        "build")
            check_prerequisites
            build_images
            ;;
        "test")
            check_prerequisites
            test_locally
            ;;
        "deploy")
            check_prerequisites
            deploy_to_render
            ;;
        "full")
            check_prerequisites
            build_images
            test_locally
            deploy_to_render
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"