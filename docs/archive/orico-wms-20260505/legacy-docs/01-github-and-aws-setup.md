# Step 1: GitHub + AWS Activate 设置指南

## GitHub 推送（5分钟）

```bash
# 1. 在浏览器中创建仓库
#    打开 https://github.com/new
#    Name: wms-quickstart
#    Visibility: Private
#    不要勾选 Initialize with README
#    点击 Create repository

# 2. 推送代码
cd /Volumes/MaxRelocated/WMS
git push -u origin main

# 3. 验证
#    打开 https://github.com/wuqxmark/wms-quickstart
#    应看到 98 个文件
```

## AWS Activate 积分申请（15分钟）

### 什么是 AWS Activate
AWS 给创业公司免费的云资源额度，$1K-$100K 不等。你的 WMS 起步月费约 $245，$10K 积分可以用 40 个月。

### 申请步骤

1. **打开申请页面**: https://aws.amazon.com/activate/
2. **选择**: "Activate Founders" (无需加速器背书)
3. **填写信息**:
   - Company Name: `GreenEcoPower Corp`
   - Website: `https://maxsmartagv.ai`
   - Address: `2806 Green Circle Dr., Mansfield, TX 76063`
   - Industry: `Logistics & Supply Chain`
   - Description: `Cloud-based Warehouse Management System (WMS) SaaS for 3PL operators in North America, with AGV automation integration path`
   - Stage: `Pre-Revenue / MVP`
   - AWS Account ID: (你的 AWS 账号 ID)
4. **提交后**: 通常 3-5 个工作日审批，额度 $1,000 起
5. **高额积分**: 如果有 VC 投资或加速器，可申请 Activate Portfolio ($10K-$100K)

### 申请后立即做

```bash
# 安装 AWS CLI
brew install awscli

# 配置凭证
aws configure
# AWS Access Key ID: (从 AWS Console > IAM 获取)
# AWS Secret Access Key: (同上)
# Default region: us-east-1
# Default output format: json

# 创建 ECR 仓库（存储 Docker 镜像）
aws ecr create-repository --repository-name wms-quickstart --region us-east-1

# 创建 Terraform 状态存储桶
aws s3 mb s3://wms-quickstart-terraform-state --region us-east-1
```
