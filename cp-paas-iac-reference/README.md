# CP PaaS IaC Reference Architecture

This repository implements a **Monorepo + ChartMuseum + ArgoCD** architecture for managing Kubernetes Add-ons and Tenant Onboarding layers.

## Architecture Overview

*   **Monorepo**: Single source of truth for all infrastructure code.
*   **Components**: Source code and Helm charts for individual components (e.g., `cni-core`, `tenant-onboarding`).
*   **Uber Chart**: A single umbrella chart (`cluster-uber`) that bundles all components.
*   **ChartMuseum**: S3-backed (or PVC-backed) Helm repository for versioned artifacts.
*   **ArgoCD**: Deploys the `cluster-uber` chart (from ChartMuseum) combined with environment-specific values (from Git).

## Directory Structure

*   `components/`: Source code and Charts for Add-ons and Tenants.
    *   `addons/`: Infra components (CNI, GPU Operator, etc.).
    *   `tenants/`: Tenant configuration (Namespaces, Quotas, RBAC).
*   `uber/`: The `cluster-uber` chart source.
*   `env/`: Environment-specific configurations.
    *   `overlays/dev`: Values for Dev environment.
    *   `overlays/staging`: Values for Staging environment.
    *   `overlays/prod`: Values for Prod environment.
*   `releases/`: `release.yaml` Source of Truth for versions.
*   `ci/`: Scripts for building and publishing charts.

## Workflows

1.  **Modify Component**: Edit `components/.../helm/...`.
2.  **Publish Charts**: Run `ci/build-and-publish-charts.sh`.
3.  **Update Uber Chart**: Run `ci/build-and-publish-uber.sh`.
4.  **Promote**: Edit `releases/release.yaml` (or `env/overlays/.../argocd-app.yaml`) to update versions.
