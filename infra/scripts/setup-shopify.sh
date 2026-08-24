#!/bin/bash
#
# Shopify Integration Setup Script
# Configures a Shopify store to send orders to WMS QuickStart
#
# Usage:
#   ./setup-shopify.sh \
#     --wms-url https://your-wms.com \
#     --wms-token "your-jwt-token" \
#     --tenant-id "tenant-xxx" \
#     --client-id "client-xxx" \
#     --shop "my-store.myshopify.com" \
#     --shopify-token "shpat_xxx" \
#     --webhook-secret "xxx" \
#     --warehouse-id "warehouse-xxx"

set -euo pipefail

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --wms-url) WMS_URL="$2"; shift 2 ;;
    --wms-token) WMS_TOKEN="$2"; shift 2 ;;
    --tenant-id) TENANT_ID="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --shop) SHOP_DOMAIN="$2"; shift 2 ;;
    --shopify-token) SHOPIFY_TOKEN="$2"; shift 2 ;;
    --webhook-secret) WEBHOOK_SECRET="$2"; shift 2 ;;
    --warehouse-id) WAREHOUSE_ID="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "=== WMS QuickStart × Shopify Integration Setup ==="
echo ""

# Step 1: Configure Shopify integration in WMS
echo "→ Step 1: Configuring Shopify credentials in WMS..."
curl -sf -X POST "${WMS_URL}/api/v1/integrations/configure" \
  -H "Authorization: Bearer ${WMS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"${CLIENT_ID}\",
    \"platform\": \"shopify\",
    \"config\": {
      \"shop_domain\": \"${SHOP_DOMAIN}\",
      \"access_token\": \"${SHOPIFY_TOKEN}\",
      \"webhook_secret\": \"${WEBHOOK_SECRET}\",
      \"default_warehouse_id\": \"${WAREHOUSE_ID}\"
    }
  }" | python3 -m json.tool
echo ""

# Step 2: Import SKUs from Shopify
echo "→ Step 2: Importing SKUs from Shopify to WMS..."
curl -sf -X POST "${WMS_URL}/api/v1/skus/import-from-shopify?client_id=${CLIENT_ID}" \
  -H "Authorization: Bearer ${WMS_TOKEN}" | python3 -m json.tool
echo ""

# Step 3: Create Webhook in Shopify
WEBHOOK_URL="${WMS_URL}/api/v1/integrations/shopify/webhook/${TENANT_ID}/${CLIENT_ID}"
echo "→ Step 3: Creating order webhook in Shopify..."
echo "  Webhook URL: ${WEBHOOK_URL}"
curl -sf -X POST "https://${SHOP_DOMAIN}/admin/api/2024-01/webhooks.json" \
  -H "X-Shopify-Access-Token: ${SHOPIFY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"webhook\": {
      \"topic\": \"orders/create\",
      \"address\": \"${WEBHOOK_URL}\",
      \"format\": \"json\"
    }
  }" | python3 -m json.tool
echo ""

# Step 4: Verify
echo "→ Step 4: Verifying integration status..."
curl -sf "${WMS_URL}/api/v1/integrations/status/${CLIENT_ID}" \
  -H "Authorization: Bearer ${WMS_TOKEN}" | python3 -m json.tool
echo ""

echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Place a test order on ${SHOP_DOMAIN}"
echo "  2. Check WMS for new outbound order: GET ${WMS_URL}/api/v1/orders/outbound"
echo "  3. Process the order: allocate → pick → pack → ship"
echo "  4. Verify tracking number appears in Shopify"
