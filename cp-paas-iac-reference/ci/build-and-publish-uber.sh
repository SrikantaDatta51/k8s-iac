#!/bin/bash
set -e

# Configuration
CHARTMUSEUM_URL="http://192.168.100.10:30080"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Function to get latest version from ChartMuseum
get_remote_version() {
    local chart_name=$1
    local version=$(curl -s "$CHARTMUSEUM_URL/api/charts/$chart_name" | jq -r '.[0].version' 2>/dev/null)
    if [ "$version" == "null" ] || [ -z "$version" ]; then
        echo "0.0.0"
    else
        echo "$version"
    fi
}

bump_version() {
    local version=$1
    echo "$version" | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g'
}

# List of uber charts
UBER_CHARTS=("cluster-addons-uber" "tenant-uber")

for chart in "${UBER_CHARTS[@]}"; do
    CHART_DIR="$REPO_ROOT/uber/$chart"
    echo "Processing Uber Chart: $chart..."

    # Check dependencies and bump if needed
    # (Simplified logic: always bump for now to ensure latest components are picked up if ranges are used)
    # Ideally, we check if dependencies in Chart.yaml changed or if the dependency charts themselves got new versions.
    
    # Update dependencies to get latest versions from ChartMuseum
    helm dependency update "$CHART_DIR"
    
    # Git diff verification could range here too.
    
    current_version=$(grep '^version:' "$CHART_DIR/Chart.yaml" | awk '{print $2}')
    remote_version=$(get_remote_version "$chart")
    
    if [ "$(printf '%s\n' "$remote_version" "$current_version" | sort -V | tail -n1)" == "$remote_version" ]; then
            new_version=$(bump_version "$remote_version")
            echo "  Bumping version from $current_version to $new_version"
            sed -i "s/^version: .*/version: $new_version/" "$CHART_DIR/Chart.yaml"
    fi

    # Package
    echo "Packaging $chart..."
    helm package "$CHART_DIR" -d /tmp/charts

    # Publish
    version=$(grep '^version:' "$CHART_DIR/Chart.yaml" | awk '{print $2}')
    pkg="/tmp/charts/${chart}-${version}.tgz"
    echo "Publishing $pkg to $CHARTMUSEUM_URL..."
    curl -s --data-binary "@$pkg" "$CHARTMUSEUM_URL/api/charts"
    echo " Done."
done
