#!/usr/bin/env python3

import os
import requests
import json
from typing import Set, Dict, List, Optional


class NPMAPIManager:
    """Manages Nginx Proxy Manager operations via API"""

    def __init__(self, logger, domain_suffix: str, npm_host: str, npm_email: str, npm_password: str, certificate_id: int = 1, testing_mode: bool = False):
        self.logger = logger
        self.domain_suffix = domain_suffix
        self.npm_host = npm_host
        self.npm_email = npm_email
        self.npm_password = npm_password
        self.certificate_id = certificate_id
        self.testing_mode = testing_mode
        self.base_url = f"http://{npm_host}/api"
        self.token = None
        self.token_expires = None

    def _get_auth_token(self) -> bool:
        """Get JWT token from NPM API"""
        if self.testing_mode:
            self.logger.info("[TEST] Would authenticate with NPM API")
            self.token = "test_token"
            return True

        try:
            auth_data = {
                "identity": self.npm_email,
                "secret": self.npm_password
            }

            response = requests.post(
                f"{self.base_url}/tokens",
                json=auth_data,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data['token']
                self.token_expires = data['expires']
                self.logger.info("Successfully authenticated with NPM API")
                return True
            else:
                self.logger.error(f"Failed to authenticate with NPM API: {response.status_code} {response.text}")
                return False

        except Exception as e:
            self.logger.error(f"Error authenticating with NPM API: {e}")
            return False

    def _make_api_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated API request to NPM"""
        if not self.token and not self._get_auth_token():
            return None

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        try:
            if method.upper() == "GET":
                response = requests.get(f"{self.base_url}{endpoint}", headers=headers, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(f"{self.base_url}{endpoint}", headers=headers, json=data, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(f"{self.base_url}{endpoint}", headers=headers, json=data, timeout=30)
            elif method.upper() == "DELETE":
                response = requests.delete(f"{self.base_url}{endpoint}", headers=headers, timeout=30)
            else:
                self.logger.error(f"Unsupported HTTP method: {method}")
                return None

            if response.status_code in [200, 201]:
                return response.json() if response.text else {}
            elif response.status_code == 401:
                # Token expired, try to refresh
                self.logger.info("Token expired, refreshing...")
                self.token = None
                if self._get_auth_token():
                    headers["Authorization"] = f"Bearer {self.token}"
                    # Retry the request
                    if method.upper() == "GET":
                        response = requests.get(f"{self.base_url}{endpoint}", headers=headers, timeout=30)
                    elif method.upper() == "POST":
                        response = requests.post(f"{self.base_url}{endpoint}", headers=headers, json=data, timeout=30)
                    elif method.upper() == "PUT":
                        response = requests.put(f"{self.base_url}{endpoint}", headers=headers, json=data, timeout=30)
                    elif method.upper() == "DELETE":
                        response = requests.delete(f"{self.base_url}{endpoint}", headers=headers, timeout=30)

                    if response.status_code in [200, 201]:
                        return response.json() if response.text else {}

                self.logger.error(f"API request failed: {response.status_code} {response.text}")
                return None
            else:
                self.logger.error(f"API request failed: {response.status_code} {response.text}")
                return None

        except Exception as e:
            self.logger.error(f"Error making API request: {e}")
            return None

    def get_existing_proxy_hosts(self) -> List[Dict]:
        """Get all existing proxy hosts from NPM"""
        if self.testing_mode:
            self.logger.info("[TEST] Would fetch existing proxy hosts")
            return []

        result = self._make_api_request("GET", "/nginx/proxy-hosts")
        if result is not None:
            self.logger.info(f"Found {len(result)} existing proxy hosts")
            return result
        else:
            self.logger.error("Failed to fetch existing proxy hosts")
            return []

    def create_proxy_host(self, domain: str, forward_host: str, forward_port: int) -> Optional[Dict]:
        """Create a new proxy host via NPM API"""
        if self.testing_mode:
            self.logger.info(f"[TEST] Would create proxy host: {domain} -> {forward_host}:{forward_port}")
            return {"id": 999, "domain_names": [domain]}

        # Payload structure matches the captured request exactly
        payload = {
            "domain_names": [domain],
            "forward_scheme": "http",
            "forward_host": forward_host,
            "forward_port": forward_port,
            "access_list_id": 0,
            "caching_enabled": False,
            "block_exploits": False,
            "allow_websocket_upgrade": True,
            "locations": [],
            "certificate_id": self.certificate_id,
            "ssl_forced": True,
            "http2_support": True,
            "hsts_enabled": False,
            "hsts_subdomains": False,
            "advanced_config": "",
            "meta": {}
        }

        result = self._make_api_request("POST", "/nginx/proxy-hosts", payload)
        if result:
            self.logger.info(f"Created proxy host: {domain} -> {forward_host}:{forward_port}")
            return result
        else:
            self.logger.error(f"Failed to create proxy host for {domain}")
            return None

    def delete_proxy_host(self, host_id: int) -> bool:
        """Delete a proxy host via NPM API"""
        if self.testing_mode:
            self.logger.info(f"[TEST] Would delete proxy host ID: {host_id}")
            return True

        result = self._make_api_request("DELETE", f"/nginx/proxy-hosts/{host_id}")
        if result is not None:
            self.logger.info(f"Deleted proxy host ID: {host_id}")
            return True
        else:
            self.logger.error(f"Failed to delete proxy host ID: {host_id}")
            return False

    def load_services_from_json(self, json_file: str = "/app/data/services.json") -> List[Dict]:
        """Load services configuration from JSON file"""
        try:
            if not os.path.exists(json_file):
                self.logger.error(f"Services configuration file not found: {json_file}")
                return []

            with open(json_file, 'r') as f:
                data = json.load(f)

            services = []
            for service in data.get('services', []):
                # Validate required fields
                if not all(key in service for key in ['domain_names', 'forward_host', 'forward_port']):
                    self.logger.warning(f"Skipping incomplete service config: {service}")
                    continue

                # Validate data types
                if not isinstance(service['domain_names'], list) or not service['domain_names']:
                    self.logger.warning(f"Invalid domain_names for service: {service}")
                    continue

                try:
                    port = int(service['forward_port'])

                    # Create a service entry for each domain name
                    for domain_name in service['domain_names']:
                        services.append({
                            "hostname": domain_name,
                            "server_ip": service['forward_host'],
                            "port": port,
                            "description": service.get('description', '')
                        })
                        self.logger.info(f"Loaded service: {domain_name} -> {service['forward_host']}:{port}")

                except (ValueError, TypeError):
                    self.logger.error(f"Invalid port for service: {service}")
                    continue

            self.logger.info(f"Loaded {len(services)} domain configurations from {json_file}")
            return services

        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing JSON configuration file: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error loading services configuration: {e}")
            return []

    def sync_proxy_hosts_from_services(self) -> Set[str]:
        """Synchronize NPM proxy hosts with service definitions"""
        self.logger.info("Synchronizing proxy hosts with service definitions...")

        # Load services from JSON configuration
        services = self.load_services_from_json()
        if not services:
            self.logger.warning("No services found in JSON configuration")
            return set()

        # Get existing proxy hosts
        existing_hosts = self.get_existing_proxy_hosts()

        # Build expected domains
        expected_domains = set()
        for service in services:
            domain = f"{service['hostname']}.{self.domain_suffix}"
            expected_domains.add(domain)

        # Find existing domains
        existing_domains = {}
        for host in existing_hosts:
            for domain in host.get('domain_names', []):
                existing_domains[domain] = host['id']

        # Delete hosts that shouldn't exist
        for domain, host_id in existing_domains.items():
            if domain not in expected_domains:
                self.logger.info(f"Removing unused proxy host: {domain}")
                self.delete_proxy_host(host_id)

        # Create missing hosts
        for service in services:
            domain = f"{service['hostname']}.{self.domain_suffix}"
            if domain not in existing_domains:
                self.logger.info(f"Creating new proxy host: {domain}")
                self.create_proxy_host(domain, service['server_ip'], service['port'])

        self.logger.info(f"Proxy host synchronization complete. Configured {len(expected_domains)} domains")
        return expected_domains