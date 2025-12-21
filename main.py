#!/usr/bin/env python3

import os
import re
import subprocess
import time
import glob
import logging
from typing import List, Set


class NPM2PiHole:
    def __init__(self):
        self.setup_logging()

        self.pihole_host = os.getenv('PIHOLE_HOST', '192.168.0.0')
        self.target_host = os.getenv('NPM_TARGET_HOST', 'npm.example.com')
        self.testing_mode = os.getenv('TESTING_MODE', 'false').lower() == 'true'
        self.sleep_interval = int(os.getenv('SLEEP_INTERVAL', 900))

        self.validate_config()
        self.setup_ssh()

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

    def validate_config(self):
        """Validate configuration"""
        if self.pihole_host == '192.168.0.0':
            self.logger.error("Please set PIHOLE_HOST in .env file")
            exit(1)

        if self.target_host == 'npm.example.com':
            self.logger.error("Please set NPM_TARGET_HOST in .env file")
            exit(1)

    def setup_ssh(self):
        """Setup SSH keys and known hosts"""
        ssh_key_path = '/root/.ssh/id_rsa'

        if not os.path.exists(ssh_key_path):
            self.logger.info("Generating SSH key...")
            subprocess.run([
                'ssh-keygen', '-t', 'rsa', '-N', '', '-f', ssh_key_path
            ], check=True)

            self.logger.info(f"SSH key generated. Please copy it to your Pi-hole host:")
            self.logger.info(f"ssh-copy-id -i {ssh_key_path} {self.pihole_host}")
            self.logger.info("Then restart this container.")
            exit(1)

        # Add host to known_hosts
        try:
            subprocess.run([
                'ssh-keyscan', '-H', self.pihole_host
            ], stdout=open('/root/.ssh/known_hosts', 'a'), stderr=subprocess.DEVNULL)
        except:
            pass  # Ignore errors, key might already exist

    def run_ssh_command(self, command: str) -> str:
        """Execute command on remote Pi-hole via SSH"""
        try:
            result = subprocess.run([
                'ssh', self.pihole_host, command
            ], capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.logger.info(f"SSH command failed with code {result.returncode}: {result.stderr.strip()}")
                return ""

            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            self.logger.info("SSH command timed out")
            return ""
        except Exception as e:
            self.logger.info(f"SSH error: {e}")
            return ""

    def get_existing_cname_records(self) -> Set[str]:
        """Get existing CNAME records from Pi-hole"""
        command = "sudo pihole-FTL --config dns.cnameRecords"
        response = self.run_ssh_command(command)

        if not response or response == "[]":
            return set()

        # Parse Pi-hole format: [ domain1,target1, domain2,target2, ... ]
        # Each record is "domain,target" separated by ", " (comma-space)
        response = response.strip()
        if response.startswith('[') and response.endswith(']'):
            response = response[1:-1]  # Remove brackets

        # Split by ", " to get individual CNAME records
        records = set()
        if response.strip():
            # Split by ", " (comma followed by space) to get each domain,target pair
            parts = response.split(', ')
            for part in parts:
                part = part.strip()
                if part and ',' in part:
                    records.add(part)

        return records

    def get_nginx_domains(self) -> Set[str]:
        """Extract domains from NPM config files"""
        domains = set()

        # Check if NPM directory exists
        npm_dir = '/app/npm'
        if not os.path.exists(npm_dir):
            self.logger.info("ERROR: /app/npm/ directory not found! Check your volume mount.")
            return domains

        # Get all .conf files
        config_files = glob.glob(f"{npm_dir}/*.conf")
        file_count = len(config_files)

        self.logger.info(f"Found {file_count} files in {npm_dir}/ directory")

        # Extract server_name from each file
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    content = f.read()

                # Find server_name lines
                server_name_pattern = r'server_name\s+([^;]+);'
                matches = re.findall(server_name_pattern, content)

                for match in matches:
                    # Handle multiple domains on one line
                    for domain in match.split():
                        domain = domain.strip()
                        if domain:
                            domains.add(domain)

            except Exception as e:
                self.logger.info(f"Error reading {config_file}: {e}")

        return domains

    def update_cname_records(self, domains: Set[str]):
        """Update CNAME records on Pi-hole"""
        if not domains:
            self.logger.info("No domains to process")
            return

        self.logger.info(f"Processing {len(domains)} domains for CNAME records")

        # Get existing records
        existing_records = self.get_existing_cname_records()

        # Build new records list
        new_records = set(existing_records)  # Start with existing
        added_count = 0

        for domain in domains:
            record = f"{domain},{self.target_host}"

            if record in existing_records:
                self.logger.info(f"CNAME record already exists: {domain} -> {self.target_host}")
            else:
                self.logger.info(f"Adding CNAME record: {domain} -> {self.target_host}")
                new_records.add(record)
                added_count += 1

        # Only update if there are changes
        if added_count > 0:
            # Format for Pi-hole: [ "item1", "item2", "item3" ]
            quoted_records = [f'"{record}"' for record in sorted(new_records)]
            formatted_records = f'[ {", ".join(quoted_records)} ]'

            command = f"sudo pihole-FTL --config dns.cnameRecords '{formatted_records}'"

            if self.testing_mode:
                self.logger.info(f"[TEST] Would execute: {command}")
                self.logger.info(f"[TEST] Would update {added_count} CNAME records and restart pihole-FTL")
            else:
                result = self.run_ssh_command(command)
                if result != "":  # Command succeeded (returns empty string on failure)
                    self.logger.info("CNAME records updated successfully")
                    self.logger.info(f"Updated {added_count} CNAME records")

                    # Restart pihole-FTL
                    self.logger.info("Restarting pihole-FTL to apply CNAME changes...")
                    restart_result = self.run_ssh_command("sudo systemctl restart pihole-FTL")
                    if restart_result != "":
                        self.logger.info("pihole-FTL restarted successfully")
                    else:
                        self.logger.error("Failed to restart pihole-FTL")
                else:
                    self.logger.error(f"Failed to update CNAME records. Command: {command}")
        else:
            self.logger.info("No changes detected")

    def run_check(self):
        """Run a single check cycle"""
        self.logger.info("Starting Check")

        # Get domains from NPM configs
        current_domains = self.get_nginx_domains()
        self.logger.info(f"Total domains found: {len(current_domains)}")

        if current_domains:
            # Update CNAME records
            self.update_cname_records(current_domains)

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