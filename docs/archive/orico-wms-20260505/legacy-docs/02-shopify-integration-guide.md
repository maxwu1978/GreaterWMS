# Shopify Integration Guide — WMS QuickStart

## Overview

当你的3PL客户（货主）在Shopify上卖货时，消费者下的订单需要自动流入WMS进行拣货发货。

```
Shopify 店铺下单 → Webhook → WMS 创建出库单 → 拣货发货 → 运单号回传 Shopify
```

## Step 1: 创建 Shopify Custom App（每个货主做一次）

### 1.1 进入 Shopify Partner Dashboard

货主需要在自己的 Shopify 店铺后台操作：

1. 登录 Shopify Admin: `https://{shop}.myshopify.com/admin`
2. 左侧菜单 → Settings → Apps and sales channels
3. 点击 "Develop apps" → "Create an app"
4. App name: `WMS QuickStart`
5. 点击 "Configure Admin API scopes"

### 1.2 配置 API 权限

勾选以下权限（最小化原则）：

| Scope | 用途 |
|-------|------|
| `read_orders` | 读取订单信息 |
| `write_orders` | 更新订单状态 |
| `read_products` | 读取商品信息（SKU映射） |
| `read_inventory` | 读取库存水平 |
| `write_inventory` | 回写库存数量 |
| `write_fulfillments` | 创建发货记录（回传运单号） |
| `read_shipping` | 读取收货地址 |

### 1.3 安装并获取 Access Token

1. 点击 "Install app"
2. 记录 **Admin API access token**（只显示一次！）
3. 记录 **API secret key**（用于验证 Webhook 签名）

## Step 2: 在 WMS 中配置集成

### 2.1 通过 API 配置

```bash
# 替换为实际值
curl -X POST https://your-wms.com/api/v1/integrations/configure \
  -H "Authorization: Bearer {your_operator_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "客户ID",
    "platform": "shopify",
    "config": {
      "shop_domain": "my-store.myshopify.com",
      "access_token": "shpat_xxxxxxxxxxxxx",
      "webhook_secret": "xxxxxxxxxxxxxxx",
      "default_warehouse_id": "仓库ID"
    }
  }'
```

### 2.2 通过前端配置（推荐）

在 WMS 管理界面：Clients → 选择客户 → Integrations → Shopify → 填入上述信息

## Step 3: 配置 Shopify Webhook

### 3.1 在 Shopify 后台创建 Webhook

1. Settings → Notifications → Webhooks
2. 点击 "Create webhook"
3. 配置：
   - Event: `Order creation`
   - Format: `JSON`
   - URL: `https://your-wms.com/api/v1/integrations/shopify/webhook/{tenant_id}/{client_id}`
4. 保存

### 3.2 使用 API 自动创建（推荐）

```bash
# 通过 Shopify Admin API 创建 Webhook
curl -X POST https://my-store.myshopify.com/admin/api/2024-01/webhooks.json \
  -H "X-Shopify-Access-Token: shpat_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "topic": "orders/create",
      "address": "https://your-wms.com/api/v1/integrations/shopify/webhook/{tenant_id}/{client_id}",
      "format": "json"
    }
  }'
```

## Step 4: 测试流程

### 4.1 本地测试（ngrok）

开发阶段，Shopify无法直接访问 localhost。使用 ngrok 创建临时公网URL：

```bash
# 安装 ngrok
brew install ngrok

# 启动隧道
ngrok http 8000

# 得到类似: https://abc123.ngrok.io
# 用这个URL配置 Shopify Webhook
```

### 4.2 Shopify 测试订单

1. 在 Shopify Admin → Settings → Payments
2. 启用 "Shopify Payments" 测试模式（或 Bogus Gateway）
3. 在店铺前台下一个测试订单
4. 检查 WMS 是否收到订单：

```bash
# 查看最新出库单
curl https://your-wms.com/api/v1/orders/outbound?status=pending \
  -H "Authorization: Bearer {token}"
```

### 4.3 验证发货回传

1. 在 WMS 中完成拣货→打包→发货流程
2. 确认运单号已回传到 Shopify：
   - Shopify Admin → Orders → 查看测试订单
   - 应显示 "Fulfilled" + 运单追踪号

## Step 5: SKU 映射

### 重要：Shopify SKU 必须与 WMS SKU 匹配

```
Shopify 商品 SKU (如 "WIDGET-001")
  ↕ 必须完全一致
WMS SKU code (如 "WIDGET-001")
```

如果 SKU 不匹配，订单行项会被跳过。

### 导入 SKU 到 WMS

在配置集成之前，确保客户的所有 SKU 已录入 WMS：

```bash
# 创建 SKU
curl -X POST https://your-wms.com/api/v1/skus \
  -H "Authorization: Bearer {token}" \
  -d '{
    "client_id": "客户ID",
    "sku_code": "WIDGET-001",
    "barcode": "123456789012",
    "name": "Standard Widget"
  }'
```

## 常见问题

### Q: Webhook 没收到怎么办？
1. 检查 Shopify Admin → Settings → Notifications → Webhooks → 查看投递日志
2. 确认URL可访问（用浏览器打开 `https://your-wms.com/health`）
3. 检查 WMS 后端日志

### Q: 订单进来了但没有行项？
SKU 不匹配。检查 Shopify 商品的 SKU 字段是否与 WMS 中的 `sku_code` 完全一致。

### Q: 如何处理退货？
当前版本暂不支持自动退货。退货需在 WMS 中手动创建入库单处理。后续版本会增加 `orders/cancelled` 和 `refunds/create` Webhook。

### Q: 多个 Shopify 店铺怎么处理？
每个店铺对应一个 WMS Client。重复 Step 1-3 为每个店铺创建独立的 App + Webhook。
