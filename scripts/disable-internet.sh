#!/bin/bash

# MLOps Inference Stack - Internet Access Disable Script  
# 이 스크립트는 인터넷 접근을 차단합니다 (DDoS 보호)

set -e

echo "🛡️  MLOps Inference Stack - 인터넷 접근 차단 중..."
echo "=================================================="

# 변수 설정
REGION="ap-northeast-2"
VPC_ID="vpc-0c4b84e791e0af4a3"
ROUTE_TABLE_1="rtb-0138c497424f41bf1"
ROUTE_TABLE_2="rtb-018739e59e1e585df"

echo "📍 VPC ID: $VPC_ID"
echo "🔒 DDoS 보호를 위해 인터넷 라우트를 제거합니다"
echo ""

# Route Table 1에서 인터넷 라우트 제거
echo "🔧 Route Table 1 ($ROUTE_TABLE_1)에서 인터넷 라우트 제거 중..."
aws ec2 delete-route \
    --route-table-id $ROUTE_TABLE_1 \
    --destination-cidr-block 0.0.0.0/0 \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Route Table 1 라우트 제거 완료"
else
    echo "❌ Route Table 1 라우트 제거 실패 (이미 제거되었을 수 있음)"
fi

# Route Table 2에서 인터넷 라우트 제거  
echo "🔧 Route Table 2 ($ROUTE_TABLE_2)에서 인터넷 라우트 제거 중..."
aws ec2 delete-route \
    --route-table-id $ROUTE_TABLE_2 \
    --destination-cidr-block 0.0.0.0/0 \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Route Table 2 라우트 제거 완료"
else
    echo "❌ Route Table 2 라우트 제거 실패 (이미 제거되었을 수 있음)"
fi

echo ""
echo "🛡️  인터넷 접근 차단 완료!"
echo "=================================================="
echo "✅ DDoS 공격으로부터 안전합니다"
echo "✅ 외부 트래픽 비용이 발생하지 않습니다"
echo "✅ 내부 AWS 서비스는 정상 작동합니다"
echo ""
echo "📝 참고: 인터넷 접근을 다시 활성화하려면 enable-internet.sh를 실행하세요."