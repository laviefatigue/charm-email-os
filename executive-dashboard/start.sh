#!/bin/bash

# Charm Executive Dashboard - Startup Script
# Starts the dashboard on port 3006

echo "🚀 Starting Charm Executive Dashboard..."
echo "📊 Dashboard will be available at: http://localhost:3006"
echo "🔗 Connecting to Charm API at: http://localhost:8000"
echo ""

# Check if API is running
if ! curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "⚠️  WARNING: Charm API doesn't appear to be running at http://localhost:8000"
    echo "   Please start the Charm API first for the dashboard to work properly."
    echo ""
fi

# Start the dashboard
npm start
