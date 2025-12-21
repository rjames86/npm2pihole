#!/usr/bin/env python3

import os
import time
import logging
from npm_manager import NPMManager
from pihole_manager import PiHoleManager


class NPM2PiHole:
    def __init__(self):
        self.setup_logging()
        self.load_config()
        self.validate_config()

        # Initialize managers
        self.npm_manager = NPMManager(
            self.logger,
            self.domain_suffix,
            self.npm_config_dir,
            self.npm_container,
            self.testing_mode
        )

        self.pihole_manager = PiHoleManager(
            self.logger,
            self.pihole_host,
            self.target_host,
            self.testing_mode
        )

    def setup_logging(self):
        """Configure logging with Docker-friendly format"""
        # Create custom formatter that matches the original timestamp format
        class DockerFormatter(logging.Formatter):
            def format(self, record):
                # Format: "Sat Dec 20 19:28:59 UTC 2025 - message"
                from datetime import datetime
                timestamp = datetime.now().strftime('%a %b %d %H:%M:%S UTC %Y')
                return f"{timestamp} - {record.getMessage()}"

        # Configure root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Create console handler with custom formatter
        handler = logging.StreamHandler()
        handler.setFormatter(DockerFormatter())
        logger.addHandler(handler)

        # Store logger reference
        self.logger = logger

    def load_config(self):
        """Load configuration from environment variables"""
        self.pihole_host = os.getenv('PIHOLE_HOST', '192.168.0.0')
        self.target_host = os.getenv('NPM_TARGET_HOST', 'npm.example.com')
        self.domain_suffix = os.getenv('DOMAIN_SUFFIX', 'home.example.com')
        self.npm_config_dir = os.getenv('NPM_CONFIG_DIR', '/app/npm-configs')
        self.npm_container = os.getenv('NPM_CONTAINER_NAME', 'npm-app-1')
        self.testing_mode = os.getenv('TESTING_MODE', 'false').lower() == 'true'
        self.sleep_interval = int(os.getenv('SLEEP_INTERVAL', 900))

    def validate_config(self):
        """Validate configuration"""
        if self.pihole_host == '192.168.0.0':
            self.logger.error("Please set PIHOLE_HOST in .env file")
            exit(1)

        if self.target_host == 'npm.example.com':
            self.logger.error("Please set NPM_TARGET_HOST in .env file")
            exit(1)

        if self.domain_suffix == 'home.example.com':
            self.logger.error("Please set DOMAIN_SUFFIX in .env file")
            exit(1)

    def run_check(self):
        """Run a single check cycle with unified workflow"""
        self.logger.info("Starting Check")

        # Step 1: Generate nginx configs from service definitions
        current_domains = self.npm_manager.generate_nginx_configs_from_services()
        self.logger.info(f"Total domains configured: {len(current_domains)}")

        if current_domains:
            # Step 2: Reload nginx configuration to pick up new configs
            if self.npm_manager.reload_nginx_config():
                # Step 3: Update Pi-hole CNAME records
                self.pihole_manager.update_cname_records(current_domains)
            else:
                self.logger.error("Failed to reload nginx configuration, skipping Pi-hole update")
        else:
            self.logger.warning("No domains configured, nothing to do")

    def run(self):
        """Main run loop"""
        self.logger.info("Starting")
        if self.testing_mode:
            self.logger.info("*** TESTING MODE ENABLED - No changes will be applied ***")
        self.logger.info(f"Check interval: {self.sleep_interval} seconds")

        while True:
            try:
                self.run_check()
                self.logger.info(f"Sleeping for {self.sleep_interval} seconds...")
                time.sleep(self.sleep_interval)
            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(60)  # Wait a minute before retrying


if __name__ == "__main__":
    npm2pihole = NPM2PiHole()
    npm2pihole.run()