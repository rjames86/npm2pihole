#!/usr/bin/env python3

import os
import subprocess
import time
from typing import Set
from generate_nginx_configs import NginxConfigGenerator


class NPMManager:
    """Manages Nginx Proxy Manager operations including config generation and container restarts"""

    def __init__(self, logger, domain_suffix: str, npm_config_dir: str, npm_container: str, testing_mode: bool = False):
        self.logger = logger
        self.domain_suffix = domain_suffix
        self.npm_config_dir = npm_config_dir
        self.npm_container = npm_container
        self.testing_mode = testing_mode

        # Initialize nginx config generator
        self.nginx_generator = NginxConfigGenerator(self.logger)

    def generate_nginx_configs_from_services(self) -> Set[str]:
        """Generate nginx configs from service environment variables"""
        self.logger.info("Generating nginx configurations from services...")

        # Load services from environment variables
        services = self.nginx_generator.load_services_from_env()

        if not services:
            self.logger.warning("No services found in environment variables")
            return set()

        # Generate nginx configs
        generated_files = self.nginx_generator.generate_configs(
            services,
            self.domain_suffix,
            self.npm_config_dir
        )

        # Return the set of domains that were configured
        domains = set()
        for service in services:
            domain = f"{service['hostname']}.{self.domain_suffix}"
            domains.add(domain)

        return domains

    def reload_nginx_config(self) -> bool:
        """Reload nginx configuration inside the NPM container"""
        if self.testing_mode:
            self.logger.info(f"[TEST] Would reload nginx config in container: {self.npm_container}")
            return True

        try:
            self.logger.info(f"Reloading nginx configuration in container: {self.npm_container}")
            result = subprocess.run([
                'docker', 'exec', self.npm_container, 'nginx', '-s', 'reload'
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                self.logger.info("Nginx configuration reloaded successfully")
                return True
            else:
                self.logger.error(f"Failed to reload nginx config: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("Nginx reload timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error reloading nginx config: {e}")
            return False