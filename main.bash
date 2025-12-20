#!/usr/bin/env bash
#made by @c00ldude1oo
#updated for Pi-hole 6 CNAME records
sleep 1
n=0
pihole_host=$PIHOLE_HOST
testing_mode=$TESTING_MODE
target_host=$NPM_TARGET_HOST
restart_needed=false
declare -a domains1
declare -a domains2
echo $(date) - Starting
if [ "${testing_mode,,}" = "true" ]; then
    echo $(date) - "*** TESTING MODE ENABLED - No changes will be applied ***"
fi

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

# Add CNAME record using Pi-hole 6 syntax via SSH
add_cname_record() {
    local domain="$1"
    local target="$2"
    echo $(date) - Adding CNAME record: "$domain" -> "$target"

    # Get existing CNAME records from remote Pi-hole
    existing_records=$(ssh "$pihole_host" "sudo pihole-FTL --config dns.cnameRecords" 2>/dev/null)

    # If no existing records, start with empty array
    if [ -z "$existing_records" ]; then
        existing_records="[]"
    fi

    # Check if record already exists
    if echo "$existing_records" | jq -r '.[]' | grep -q "^$domain,$target$"; then
        echo $(date) - CNAME record already exists: "$domain" -> "$target"
        return 0
    fi

    # Add new record to the array using jq
    new_records=$(echo "$existing_records" | jq --arg new_record "$domain,$target" '. + [$new_record]')

    # Set the new CNAME records (Pi-hole 6 expects the format with spaces inside brackets)
    formatted_records=$(echo "$new_records" | jq -c '.' | sed 's/\[/ [ /; s/\]/ ] /')

    # Execute the command on remote Pi-hole via SSH (or just print in testing mode)
    if [ "${testing_mode,,}" = "true" ]; then
        echo $(date) - "[TEST] Would execute: sudo pihole-FTL --config dns.cnameRecords '$formatted_records'"
        echo $(date) - "[TEST] Would restart pihole-FTL service"
    else
        ssh "$pihole_host" "sudo pihole-FTL --config dns.cnameRecords '$formatted_records'"
        echo $(date) - CNAME record added successfully
        # Mark that FTL restart is needed
        restart_needed=true
    fi
}

# Check and add CNAME record for domain
check_and_add_cname() {
    #makes sure input is not empty
    if [ "$1" == "" ]; then
        echo $(date) - "Missing <domain>"
        return 1
    fi

    local domain="$1"
    # Use the target host from environment variable

    echo $(date) - Checking CNAME for \"$domain\"

    # Get current CNAME records from remote Pi-hole
    existing_records=$(ssh "$pihole_host" "sudo pihole-FTL --config dns.cnameRecords" 2>/dev/null)

    if [ -z "$existing_records" ]; then
        existing_records="[]"
    fi

    # Check if this domain already has a CNAME record using jq
    if echo "$existing_records" | jq -r '.[]' | grep -q "^$domain,"; then
        echo $(date) - CNAME record already exists for "$domain"
    else
        echo $(date) - Adding CNAME record for "$domain"
        add_cname_record "$domain" "$target_host"
        n=$((n + 1))
    fi
    echo
}

main() {
#dev     echo Starting Check
    domains1=()
    # reads all the files in npm and gets the domains out of them then formats and puts them in the array
    for file in npm/*; do
        if [ -f "$file" ]; then
            domains1+=("$(grep "server_name" "$file" | sed "s/  server_name //; s/;//")")
        fi
    done
#dev     echo Found domains from npm
#dev     echo "this  - last"
#dev     echo "check - check"
#dev     echo "  ""${#domains1[@]}""   -   ""${#domains2[@]}"
    if [ "${domains1[*]}" != "${domains2[*]}" ]; then
#dev         echo found new domains
        for i in "${domains1[@]}"; do
        #a temp fix for npm entries with more then 1 domain.
            for a in $i; do
                check_and_add_cname "$a"
            done
        done
        domains2=("${domains1[@]}")
        if [ $n != 0 ]; then
            if [ "${testing_mode,,}" = "true" ]; then
                echo $(date) - "[TEST] Would update $n CNAME records"
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
    fi
    n=0
}

while true; do
    main
#dev    echo $(date) - sleeping
    sleep 15
done