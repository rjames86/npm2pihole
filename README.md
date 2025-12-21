# NPM2PiHole - Unified Domain Management

**Single Source of Truth for NPM and Pi-hole Domain Configuration**

This tool automatically generates Nginx Proxy Manager configurations AND keeps Pi-hole CNAME records in perfect sync - all from a single configuration file.

## 🎯 What This Does

1. **Generates NPM configs** from your service definitions
2. **Restarts NPM container** to pick up new configurations
3. **Updates Pi-hole CNAME records** to match your domains
4. **Restarts Pi-hole FTL** to apply DNS changes

**Result**: Your reverse proxy and DNS stay perfectly synchronized with zero manual intervention!

## ⚡ Quick Start

1. **Copy the example config:**
   ```bash
   cp example.env .env
   ```

2. **Edit `.env` with your services and settings:**
   ```bash
   # Your domain and Pi-hole settings
   DOMAIN_SUFFIX=home.ryanmo.net
   PIHOLE_HOST=192.168.1.217
   NPM_TARGET_HOST=npm.home.ryanmo.net
   NPM_CONTAINER_NAME=npm-app-1

   # Define your services (add as many as you need)
   SERVICE_1_NAME=grafana
   SERVICE_1_IP=192.168.1.58
   SERVICE_1_PORT=3000
   ```

3. **Test and deploy:**
   ```bash
   # Test first
   echo "TESTING_MODE=true" >> .env
   docker compose up --build

   # Deploy when ready
   sed -i 's/TESTING_MODE=true/TESTING_MODE=false/' .env
   docker compose restart
   ```

## 🔄 Workflow

```
Edit .env → Generate NPM configs → Restart NPM → Update Pi-hole CNAMEs → Restart Pi-hole FTL
```

## 🚀 Benefits

- ✅ **Single source of truth** - Edit services in one place
- ✅ **Zero manual work** - Configs and DNS update automatically
- ✅ **Always in sync** - NPM and Pi-hole never get out of sync
- ✅ **Easy to manage** - Simple environment variable format
- ✅ **Testing mode** - Safe to test changes before applying