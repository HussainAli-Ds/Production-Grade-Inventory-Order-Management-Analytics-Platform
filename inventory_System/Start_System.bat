@echo off
chcp 65001 >nul
title Hussain's General Store — Inventory System
cls

echo ============================================
echo   Store Inventory ^& Order Management
echo   Hussain's General Store
echo ============================================
echo.

REM Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not installed or not in PATH.
    echo Please install Docker Desktop and try again.
    pause
    exit /b 1
)

REM Check Docker Compose
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Compose not found.
    pause
    exit /b 1
)

echo [1/4] Docker detected.
echo [2/4] Checking environment...

if not exist .env (
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
)

echo [3/4] Starting services...
docker compose up -d --build

if errorlevel 1 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)

echo [4/4] Services starting...
echo.
echo PostgreSQL will be ready shortly...
echo Dashboard will be available at: http://localhost:8080
echo.
echo Waiting for health checks...
timeout /t 10 /nobreak >nul

echo Opening dashboard...
start http://localhost:8080

echo.
echo ============================================
echo   System is running!
echo   Press any key to view logs...
echo ============================================
pause >nul

docker compose logs -f dashboard
