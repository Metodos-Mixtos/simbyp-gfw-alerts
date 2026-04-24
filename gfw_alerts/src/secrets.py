"""
Secrets management module for GFW alerts pipeline.

Supports three loading strategies in order:
1. Environment variables (Cloud Run or pre-injected)
2. .env file (local development)
3. Google Cloud Secret Manager (local dev with enhanced security)
"""

import os
from typing import Dict, List, Tuple
from pathlib import Path


# Required secrets for the pipeline
REQUIRED_SECRETS = [
    "GFW_USERNAME",
    "GFW_PASSWORD",
    "ALIAS",
    "EMAIL",
    "ORG",
    "OUTPUTS_BASE_PATH",
    "GCP_PROJECT",
    "INPUTS_PATH",
]


def _check_env_vars() -> Tuple[bool, Dict[str, str], List[str]]:
    """
    Check if all required secrets are available in environment variables.
    
    Returns:
        Tuple of (all_found: bool, secrets_dict: dict, missing_vars: list)
    """
    secrets = {}
    missing = []
    
    for secret_id in REQUIRED_SECRETS:
        value = os.getenv(secret_id)
        if value:
            secrets[secret_id] = value
        else:
            missing.append(secret_id)
    
    return len(missing) == 0, secrets, missing


def _load_dotenv_file() -> Tuple[bool, Dict[str, str], str]:
    """
    Try to load secrets from .env file.
    
    Returns:
        Tuple of (success: bool, secrets_dict: dict, error_message: str)
    """
    env_path = Path(__file__).parent.parent.parent / ".env"
    
    if not env_path.exists():
        return False, {}, f".env file not found at {env_path}"
    
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        
        secrets = {}
        for secret_id in REQUIRED_SECRETS:
            value = os.getenv(secret_id)
            if value:
                secrets[secret_id] = value
        
        if len(secrets) == len(REQUIRED_SECRETS):
            return True, secrets, ""
        else:
            missing = [s for s in REQUIRED_SECRETS if s not in secrets]
            return False, secrets, f"Incomplete .env file, missing: {', '.join(missing)}"
    
    except Exception as e:
        return False, {}, f"Error reading .env file: {str(e)}"


def _load_secret_manager(project_id: str) -> Tuple[bool, Dict[str, str], str]:
    """
    Try to load secrets from Google Cloud Secret Manager.
    
    Args:
        project_id: GCP project ID
    
    Returns:
        Tuple of (success: bool, secrets_dict: dict, error_message: str)
    """
    try:
        from google.cloud import secretmanager
    except ImportError:
        return False, {}, "google-cloud-secret-manager not installed"
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        secrets = {}
        
        for secret_id in REQUIRED_SECRETS:
            try:
                name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                secrets[secret_id] = response.payload.data.decode("UTF-8")
            except Exception as e:
                return False, {}, f"Failed to access secret '{secret_id}': {str(e)}"
        
        return True, secrets, ""
    
    except Exception as e:
        return False, {}, f"Secret Manager error: {str(e)}"


def load_secrets(project_id: str = "bosques-bogota-416214") -> Dict[str, str]:
    """
    Load secrets using a three-tier fallback strategy.
    
    Strategy (in order):
    1. Environment variables (Cloud Run or pre-injected)
    2. .env file (local development)
    3. Google Cloud Secret Manager (local dev with enhanced security)
    
    Args:
        project_id: GCP project ID (for Secret Manager access)
    
    Returns:
        Dictionary with all required secrets
    
    Raises:
        SystemExit: If secrets cannot be loaded from any source
    """
    print("\n🔐 === Secrets Management ===")
    
    # Strategy 1: Environment Variables
    print("\n1️⃣  Trying environment variables...")
    env_complete, env_secrets, env_missing = _check_env_vars()
    
    if env_complete:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from environment variables")
        print("   📍 Source: Cloud Run / Pre-injected environment")
        return env_secrets
    else:
        if env_secrets:
            print(f"   ⚠️  Partial environment variables (found {len(env_secrets)}/{len(REQUIRED_SECRETS)})")
            print(f"   ⏭️  Missing: {', '.join(env_missing)}")
        else:
            print(f"   ❌ No environment variables found")
    
    # Strategy 2: .env File
    print("\n2️⃣  Trying .env file...")
    dotenv_success, dotenv_secrets, dotenv_error = _load_dotenv_file()
    
    if dotenv_success:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from .env file")
        env_path = Path(__file__).parent.parent.parent / ".env"
        print(f"   📍 Source: {env_path}")
        return dotenv_secrets
    else:
        print(f"   ❌ {dotenv_error}")
    
    # Strategy 3: Google Cloud Secret Manager
    print("\n3️⃣  Trying Google Cloud Secret Manager...")
    print(f"   📍 Project: {project_id}")
    
    sm_success, sm_secrets, sm_error = _load_secret_manager(project_id)
    
    if sm_success:
        print(f"   ✅ Loaded all {len(REQUIRED_SECRETS)} secrets from Secret Manager")
        return sm_secrets
    else:
        print(f"   ❌ {sm_error}")
    
    # All strategies failed
    print("\n" + "="*70)
    print("❌ FATAL: Could not load secrets from any source")
    print("="*70)
    
    print("\nTo fix this issue, try one of the following:\n")
    
    print("Option 1 - Use .env file (local development):")
    print("  1. Create/update .env file at project root")
    print("  2. Add all required variables:")
    for secret_id in REQUIRED_SECRETS:
        print(f"     {secret_id}=<value>")
    print("  3. Run: python gfw_alerts/main.py\n")
    
    print("Option 2 - Use environment variables (Cloud Run):")
    print("  1. Set environment variables before running:")
    print("     export GFW_USERNAME=<value>")
    print("     export GFW_PASSWORD=<value>")
    print("     ... (repeat for all required secrets)")
    print("  2. Run: python gfw_alerts/main.py\n")
    
    print("Option 3 - Use Google Cloud Secret Manager (local development):")
    print("  1. Authenticate with GCP:")
    print("     gcloud auth application-default login")
    print("  2. Create secrets in Secret Manager:")
    for secret_id in REQUIRED_SECRETS:
        print(f"     echo -n '<value>' | gcloud secrets create {secret_id} --data-file=-")
    print("  3. Grant access to your user:")
    print("     for secret in " + " ".join(REQUIRED_SECRETS) + "; do")
    print("       gcloud secrets add-iam-policy-binding $secret \\")
    print("         --member=user:$(gcloud config get-value account) \\")
    print("         --role=roles/secretmanager.secretAccessor")
    print("     done")
    print("  4. Run: python gfw_alerts/main.py\n")
    
    exit(1)
