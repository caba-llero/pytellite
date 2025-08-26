#!/bin/bash

# Railway deployment script
echo "🚀 Deploying Satellite Controller Simulator to Railway..."

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    npm install -g @railway/cli
fi

# Login to Railway (if not already logged in)
echo "🔑 Please login to Railway (if prompted):"
railway login

# Initialize Railway project
echo "🏗️  Initializing Railway project..."
railway init --name "satellite-simulator"

# Deploy
echo "🚀 Deploying..."
railway up

# Get the deployment URL
echo "🌐 Your app should be available at:"
railway domain
