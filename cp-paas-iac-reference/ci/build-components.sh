#!/bin/bash
set -e

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

# Function to bump patch version
bump_version() {
    local version=$1
    echo "$version" | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g'
}

# Iterate over all components (Addons and Tenants)
find "$REPO_ROOT/components" -mindepth 3 -maxdepth 3 -type d -name "helm" | while read chart_dir_parent; do
    component_dir="$(dirname "$chart_dir_parent")"
    chart_dir="$chart_dir_parent/$(ls "$chart_dir_parent")"
    chart_name=$(grep '^name:' "$chart_dir/Chart.yaml" | awk '{print $2}')

    echo "Checking component: $chart_name in $component_dir"

    # Check for changes in src or helm (excluding Chart.yaml itself to avoid loops if we commit back)
    # Using git diff against previous commit for demonstration.
    # In a real CI, this might compare against origin/main.
    # Handle HEAD~1 failure.
    # Check for changes in src or helm
    prev_commit="HEAD~1"
    if ! git rev-parse --verify "$prev_commit" >/dev/null 2>&1; then
        echo "  Initial commit or shallow history, forcing build."
        # Treat as changed
        # The original `if true; then # proceed : fi` is removed as it's a no-op and the subsequent code will run.
    else
        if ! git diff --name-only "$prev_commit" HEAD | grep -q "$component_dir"; then
             echo "  No changes detected."
             continue
        fi
    fi

    echo "  Changes detected or forced build."

    # Build src container (Mock)
    if [ -d "$component_dir/src" ]; then
        echo "  Building source code for $chart_name..."
        # docker build -t registry/$chart_name:latest $component_dir/src
        # docker push registry/$chart_name:latest
    fi

    # Bump Chart Version
    current_version=$(grep '^version:' "$chart_dir/Chart.yaml" | awk '{print $2}')
    # logic: if current local version <= remote version, bump it.
    remote_version=$(get_remote_version "$chart_name")

    if [ "$(printf '%s\n' "$remote_version" "$current_version" | sort -V | tail -n1)" == "$remote_version" ]; then
         new_version=$(bump_version "$remote_version")
         echo "  Bumping version from $current_version to $new_version"
         sed -i "s/^version: .*/version: $new_version/" "$chart_dir/Chart.yaml"
         # Also update appVersion if needed
    else
         echo "  Local version $current_version is already ahead of remote $remote_version"
    fi

    # Package and Publish
    echo "  Packaging and Publishing..."
    helm dependency update "$chart_dir"
    helm package "$chart_dir" -d /tmp/charts
    pkg_version=$(grep '^version:' "$chart_dir/Chart.yaml" | awk '{print $2}' | tr -d '[:space:]')
    pkg_path="/tmp/charts/${chart_name}-${pkg_version}.tgz"
    if [ -f "$pkg_path" ]; then
        curl -s --data-binary "@$pkg_path" "$CHARTMUSEUM_URL/api/charts"
        echo "  Done."
    else
        echo "  Error: Package $pkg_path not found."
    fi
done
