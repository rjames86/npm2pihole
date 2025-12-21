#!/usr/bin/env python3

import os
import subprocess
from typing import Set


class PiHoleManager:
    """Manages Pi-hole operations including SSH connection, CNAME record management, and service restarts"""

    def __init__(self, logger, pihole_host: str, target_host: str, testing_mode: bool = False):
        self.logger = logger
        self.pihole_host = pihole_host
        self.target_host = target_host
        self.testing_mode = testing_mode

        self.setup_ssh()

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
                    self.restart_pihole_ftl()
                else:
                    self.logger.error(f"Failed to update CNAME records. Command: {command}")
        else:
            self.logger.info("No changes detected")

    def restart_pihole_ftl(self):
        """Restart pihole-FTL service"""
        if self.testing_mode:
            self.logger.info("[TEST] Would restart pihole-FTL")
            return

        self.logger.info("Restarting pihole-FTL to apply CNAME changes...")
        restart_result = self.run_ssh_command("sudo systemctl restart pihole-FTL")
        if restart_result != "":
            self.logger.info("pihole-FTL restarted successfully")
        else:
            self.logger.error("Failed to restart pihole-FTL")