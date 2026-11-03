"""Runtime configuration, read from environment variables and the CF service bindings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OAuthService:
    """Credentials of a bound service that uses client-credentials against XSUAA."""

    token_url: str  # UAA base url, without /oauth/token
    client_id: str
    client_secret: str
    extra: dict[str, Any] = field(default_factory=dict)  # service specific (uri, proxy host...)


@dataclass(frozen=True)
class XsuaaBinding:
    url: str
    client_id: str
    xsappname: str
    tenant_id: str | None


@dataclass(frozen=True)
class Settings:
    port: int
    public_url: str
    xsuaa: XsuaaBinding
    destination_service: OAuthService
    connectivity_service: OAuthService | None  # only needed for ProxyType=OnPremise
    destination_name: str
    # Backend OData mapping. Defaults follow API_SALES_ORDER_SRV; adjust to the ECC service in use.
    sales_service_path: str
    sales_entity_set: str
    # Draft creation has no safe default: it stays disabled until an entity set is configured.
    draft_entity_set: str | None
    draft_defaults: dict[str, Any]
    draft_id_field: str


class ConfigError(RuntimeError):
    pass


def _binding(vcap: dict[str, Any], label: str) -> dict[str, Any] | None:
    instances = vcap.get(label) or []
    return instances[0]["credentials"] if instances else None


def _oauth_service(creds: dict[str, Any], label: str) -> OAuthService:
    if not creds.get("clientsecret"):
        # x509 (mTLS) bindings carry certificate/key instead of a secret and are not handled here.
        raise ConfigError(f"'{label}' binding has no clientsecret; secret-based binding is required.")
    return OAuthService(
        token_url=creds["url"].rstrip("/"),
        client_id=creds["clientid"],
        client_secret=creds["clientsecret"],
        extra=creds,
    )


def load_settings() -> Settings:
    vcap = json.loads(os.environ.get("VCAP_SERVICES", "{}"))

    xsuaa = _binding(vcap, "xsuaa")
    destination = _binding(vcap, "destination")
    if not xsuaa:
        raise ConfigError("No 'xsuaa' service binding found in VCAP_SERVICES.")
    if not destination:
        raise ConfigError("No 'destination' service binding found in VCAP_SERVICES.")
    connectivity = _binding(vcap, "connectivity")

    port = int(os.environ.get("PORT", "8080"))
    public_url = os.environ.get("PUBLIC_URL")
    if not public_url:
        uris = json.loads(os.environ.get("VCAP_APPLICATION", "{}")).get("application_uris") or []
        public_url = f"https://{uris[0]}" if uris else f"http://localhost:{port}"

    return Settings(
        port=port,
        public_url=public_url.rstrip("/"),
        xsuaa=XsuaaBinding(
            url=xsuaa["url"].rstrip("/"),
            client_id=xsuaa["clientid"],
            xsappname=xsuaa["xsappname"],
            tenant_id=xsuaa.get("tenantid"),
        ),
        destination_service=_oauth_service(destination, "destination"),
        connectivity_service=_oauth_service(connectivity, "connectivity") if connectivity else None,
        destination_name=os.environ.get("DESTINATION_NAME", "Gateway-x96-SSO"),
        sales_service_path=os.environ.get("SALES_SERVICE_PATH", "/sap/opu/odata/sap/API_SALES_ORDER_SRV"),
        sales_entity_set=os.environ.get("SALES_ENTITY_SET", "A_SalesOrder"),
        draft_entity_set=os.environ.get("SALES_DRAFT_ENTITY_SET") or None,
        draft_defaults=json.loads(os.environ.get("SALES_DRAFT_DEFAULTS", "{}")),
        draft_id_field=os.environ.get("SALES_DRAFT_ID_FIELD", "SalesOrder"),
    )
