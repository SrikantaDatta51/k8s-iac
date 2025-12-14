#!/bin/bash
set -e

# Configuration
CHARTMUSEUM_URL="http://192.168.100.10:30080"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPONENTS_DIR="$REPO_ROOT/components"

# Function to package and publish
publish_chart() {
    local chart_path=$1
    local name=$(basename "$chart_path")
    
    echo "Processing $name..."
    helm package "$chart_path" -d /tmp/charts
    
    # Get version from Chart.yaml
    local version=$(grep '^version:' "$chart_path/Chart.yaml" | awk '{print $2}')
    local pkg="/tmp/charts/${name}-${version}.tgz"
    
    echo "Publishing $pkg to $CHARTMUSEUM_URL..."
    curl -s --data-binary "@$pkg" "$CHARTMUSEUM_URL/api/charts"
    echo " Done."
}

# Publish Add-ons
for d in "$COMPONENTS_DIR"/addons/*/helm/*; do
    publish_chart "$d"
done

# Publish Tenants
for d in "$COMPONENTS_DIR"/tenants/*/helm/*; do
    publish_chart "$d"
done
