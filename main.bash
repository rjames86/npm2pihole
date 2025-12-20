#!/usr/bin/env bash
#made by @c00ldude1oo
#updated for Pi-hole 6 CNAME records
sleep 1
n=0
pihole_host=$PIHOLE_HOST
testing_mode=$TESTING_MODE
target_host=$NPM_TARGET_HOST
sleep_interval=${SLEEP_INTERVAL:-900}  # Default to 15 minutes (900 seconds)
restart_needed=false
declare -a domains1
declare -a domains2
echo $(date) - Starting
if [ "${testing_mode,,}" = "true" ]; then
    echo $(date) - "*** TESTING MODE ENABLED - No changes will be applied ***"
fi
echo $(date) - "Check interval: ${sleep_interval} seconds"

#check config
if [ "$pihole_host" = '192.168.0.0' ]; then
    echo Please set PIHOLE_HOST in config.env and restart.
    exit 1
fi

if [ "$target_host" = 'npm.example.com' ]; then
    echo Please set NPM_TARGET_HOST in config.env and restart.
    exit 1
fi

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo $(date) - "jq is required for JSON manipulation. Please install jq."
    exit 1
fi

# Check if SSH key exists
if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -N '' -f /root/.ssh/id_rsa
    echo $(date) - "SSH key generated. Please copy it to your Pi-hole host:"
    echo "ssh-copy-id -i /root/.ssh/id_rsa $pihole_host"
    echo "Then restart this container."
    exit 1
fi

# Ensure the Pi-hole host is known
ssh-keyscan -H "$pihole_host" >> /root/.ssh/known_hosts 2>/dev/null

# Update all CNAME records at once using Pi-hole 6 syntax via SSH
update_cname_records() {
    local -a new_domains=("$@")

    if [ ${#new_domains[@]} -eq 0 ]; then
        echo $(date) - No new domains to process
        return 0
    fi

    echo $(date) - Processing ${#new_domains[@]} domains for CNAME records

    # Get existing CNAME records from remote Pi-hole
    existing_records=$(ssh "$pihole_host" "sudo pihole-FTL --config dns.cnameRecords" 2>/dev/null)

    echo $(date) - "DEBUG: Raw existing records: '$existing_records'"

    # If no existing records or invalid JSON, start with empty array
    if [ -z "$existing_records" ] || ! echo "$existing_records" | jq . >/dev/null 2>&1; then
        echo $(date) - "DEBUG: Invalid JSON or empty, starting fresh"
        existing_records="[]"
    fi

    # Convert existing records to a format we can work with
    existing_array=$(echo "$existing_records" | jq -r '.[]' 2>/dev/null || echo "")
    echo $(date) - "DEBUG: Parsed existing array: '$existing_array'"

    # Build new records array starting with existing records
    new_records="$existing_records"

    # Add each new domain that doesn't already exist
    for domain in "${new_domains[@]}"; do
        domain_record="$domain,$target_host"
        echo $(date) - "DEBUG: Checking if '$domain_record' exists in existing records"
        if echo "$existing_array" | grep -q "^$domain_record$"; then
            echo $(date) - CNAME record already exists: "$domain" -> "$target_host"
        else
            echo $(date) - Adding CNAME record: "$domain" -> "$target_host"
            new_records=$(echo "$new_records" | jq --arg new_record "$domain_record" '. + [$new_record]')
            n=$((n + 1))
        fi
    done

    # Only update if there are changes
    if [ $n -gt 0 ]; then
        # Create the properly quoted format for Pi-hole 6
        # Convert JSON array to Pi-hole format: [ "item1", "item2" ]
        formatted_records="[ "
        first=true
        while IFS= read -r record; do
            if [ "$first" = true ]; then
                first=false
            else
                formatted_records+=", "
            fi
            formatted_records+="\"$record\""
        done < <(echo "$new_records" | jq -r '.[]')
        formatted_records+=" ]"

        # Execute the command on remote Pi-hole via SSH (or just print in testing mode)
        if [ "${testing_mode,,}" = "true" ]; then
            echo $(date) - "[TEST] Would execute: sudo pihole-FTL --config dns.cnameRecords '$formatted_records'"
        else
            ssh "$pihole_host" "sudo pihole-FTL --config dns.cnameRecords '$formatted_records'"
            echo $(date) - CNAME records updated successfully
            # Mark that FTL restart is needed
            restart_needed=true
        fi
    fi
}


main() {
    echo $(date) - Starting Check

    # Check if npm directory exists and list files
    if [ -d "/app/npm" ]; then
        file_count=$(ls -1 /app/npm/ 2>/dev/null | wc -l)
        echo $(date) - Found $file_count files in /app/npm/ directory
    else
        echo $(date) - ERROR: /app/npm/ directory not found! Check your volume mount.
        return
    fi

    domains1=()
    # reads all the files in npm and gets the domains out of them then formats and puts them in the array
    for file in /app/npm/*; do
        if [ -f "$file" ]; then
            server_names=$(grep "server_name" "$file" | sed "s/  server_name //; s/;//")
            if [ -n "$server_names" ]; then
                domains1+=("$server_names")
            fi
        fi
    done
    echo $(date) - Total domains found: ${#domains1[@]}
    if [ "${domains1[*]}" != "${domains2[*]}" ]; then
        # Collect all domains into a single array for batch processing
        all_domains=()
        for i in "${domains1[@]}"; do
            # Handle npm entries with multiple domains
            for a in $i; do
                all_domains+=("$a")
            done
        done

        # Update all CNAME records in a single batch
        update_cname_records "${all_domains[@]}"

        domains2=("${domains1[@]}")

        if [ $n != 0 ]; then
            if [ "${testing_mode,,}" = "true" ]; then
                echo $(date) - "[TEST] Would update $n CNAME records and restart pihole-FTL"
            else
                echo $(date) - Updated $n CNAME records

                # Restart Pi-hole FTL if changes were made
                if [ "$restart_needed" = "true" ]; then
                    echo $(date) - Restarting pihole-FTL to apply CNAME changes...
                    ssh "$pihole_host" "sudo systemctl restart pihole-FTL"
                    echo $(date) - pihole-FTL restarted successfully
                    restart_needed=false
                fi
            fi
        fi
    else
        echo $(date) - No changes detected
    fi
    n=0
}

while true; do
    main
    echo $(date) - "Sleeping for ${sleep_interval} seconds..."
    sleep "$sleep_interval"
done