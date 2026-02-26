@echo off
REM ADMI Backend Deployment Script for Windows
REM This script helps deploy the ADMI Backend to Render.com

setlocal enabledelayedexpansion

REM Colors (Windows doesn't support ANSI colors in batch, so we'll use simple text)
set INFO=[INFO]
set SUCCESS=[SUCCESS]
set WARNING=[WARNING]
set ERROR=[ERROR]

REM Configuration
set SERVICE_NAME=admibackend
set PYTHON_SERVICE_NAME=admipython
set DOCKER_IMAGE_NAME=admibackend
set PYTHON_IMAGE_NAME=admipython

echo.
echo ========================================
echo ADMI Backend Windows Deployment Script
echo ========================================
echo.

REM Function to check prerequisites
:check_prerequisites
echo %INFO% Checking prerequisites...
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %ERROR% Docker is not installed. Please install Docker first.
    echo Download from: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Check if docker-compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %WARNING% Docker Compose is not installed. Some features may not work.
    echo Install Docker Desktop which includes docker-compose.
)

echo %SUCCESS% Prerequisites check completed
echo.
goto :eof

REM Function to build images
:build_images
echo %INFO% Building Docker images...
echo.

REM Build main backend image
echo %INFO% Building main backend image...
docker build -t %DOCKER_IMAGE_NAME% .

REM Build Python service image
echo %INFO% Building Python service image...
docker build --target python-service -t %PYTHON_IMAGE_NAME% .

echo %SUCCESS% Docker images built successfully
echo.
goto :eof

REM Function to test locally
:test_locally
echo %INFO% Testing locally with docker-compose...
echo.

if exist docker-compose.yml (
    docker-compose down -v
    docker-compose up -d
    
    echo %INFO% Waiting for services to start...
    timeout /t 10 /nobreak >nul
    
    REM Test Node.js backend (using PowerShell for curl)
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:3001/' -UseBasicParsing; if ($response.StatusCode -eq 200) { echo '%SUCCESS% Node.js backend is running on http://localhost:3001' } else { echo '%ERROR% Node.js backend is not responding' } } catch { echo '%ERROR% Node.js backend is not responding' }"
    
    REM Test Python service
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:5001/health' -UseBasicParsing; if ($response.StatusCode -eq 200) { echo '%SUCCESS% Python service is running on http://localhost:5001' } else { echo '%ERROR% Python service is not responding' } } catch { echo '%ERROR% Python service is not responding' }"
    
    echo.
    echo %INFO% Local testing completed. Services are running.
    echo %INFO% To stop services, run: docker-compose down -v
) else (
    echo %WARNING% docker-compose.yml not found. Skipping local test.
)

echo.
goto :eof

REM Function to deploy to Render
:deploy_to_render
echo %INFO% Deploying to Render.com...
echo.

REM Check if render CLI is available
render whoami >nul 2>&1
if %errorlevel% equ 0 (
    echo %INFO% Using Render CLI for deployment...
    
    REM Deploy using render.yaml
    if exist render.yaml (
        render deploy --service-file render.yaml
        echo %SUCCESS% Deployment initiated via Render CLI
    ) else (
        echo %ERROR% render.yaml not found
    )
) else (
    echo %INFO% Render CLI not available. Please deploy manually:
    echo.
    echo 1. Go to https://dashboard.render.com/
    echo 2. Create a new Web Service
    echo 3. Connect your GitHub repository
    echo 4. Use the following settings:
    echo    - Build Command: docker build -t admibackend .
    echo    - Start Command: docker run -p 10000:3001 -p 5001:5001 admibackend
    echo    - Health Check Path: /
    echo 5. Set environment variables:
    echo    - NODE_ENV=production
    echo    - PORT=10000
    echo    - PYTHON_SERVICE_HOST=localhost
    echo    - PYTHON_SERVICE_PORT=5001
    echo    - JWT_SECRET=^<your-secret-key^>
    echo    - DEEPSEEK_API_KEY=^<your-api-key^>
    echo    - DEEPSEEK_MODEL=deepseek-chat
    echo.
)

echo.
goto :eof

REM Function to show usage
:show_usage
echo Usage: %0 [OPTION]
echo.
echo Options:
echo   build     Build Docker images only
echo   test      Test locally with docker-compose
echo   deploy    Deploy to Render.com
echo   full      Build, test locally, and deploy (default)
echo   help      Show this help message
echo.
echo Examples:
echo   %0 build    ^> Build images only
echo   %0 test     ^> Test locally
echo   %0          ^> Full deployment process
echo.
goto :eof

REM Main execution
set ARG=%1
if "%ARG%"=="" set ARG=full

if /i "%ARG%"=="build" (
    call :check_prerequisites
    call :build_images
) else if /i "%ARG%"=="test" (
    call :check_prerequisites
    call :test_locally
) else if /i "%ARG%"=="deploy" (
    call :check_prerequisites
    call :deploy_to_render
) else if /i "%ARG%"=="full" (
    call :check_prerequisites
    call :build_images
    call :test_locally
    call :deploy_to_render
) else if /i "%ARG%"=="help" (
    call :show_usage
) else (
    echo %ERROR% Unknown option: %ARG%
    call :show_usage
    pause
    exit /b 1
)

echo.
echo ========================================
echo Deployment process completed!
echo ========================================
echo.

pause