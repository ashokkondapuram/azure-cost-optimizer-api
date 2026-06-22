# Azure Cost Optimizer API

Python FastAPI service for fetching Azure Cost Management data using Azure Managed Identity and least-privilege RBAC.

## Features
- FastAPI backend for Azure Cost Management queries
- Managed Identity authentication via `DefaultAzureCredential`
- Least-privilege access using `Cost Management Reader`
- Endpoints for health, cost summary, and usage queries
- Deployment-ready for Azure App Service, Container Apps, or AKS

## Project structure
- `app/main.py` - FastAPI application and endpoints
- `app/azure_cost.py` - Azure Cost Management client wrapper
- `requirements.txt` - Python dependencies
- `README.md` - Setup and deployment guide
- `docs/architecture.md` - Architecture, RBAC, and security notes

## Quick start
See `README.md` for local setup, Azure permissions, and deployment steps.
