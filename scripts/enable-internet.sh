#!/bin/bash

# MLOps Inference Stack - Internet Access Enable Script
# 이 스크립트는 인터넷 접근을 다시 활성화합니다

set -e

echo "🌐 MLOps Inference Stack - 인터넷 접근 활성화 중..."
echo "=================================================="

# 변수 설정
REGION="ap-northeast-2"
VPC_ID="vpc-0c4b84e791e0af4a3"
IGW_ID="igw-0c55e2d23ae10020b"
ROUTE_TABLE_1="rtb-0138c497424f41bf1"
ROUTE_TABLE_2="rtb-018739e59e1e585df"

echo "📍 VPC ID: $VPC_ID"
echo "📍 Internet Gateway ID: $IGW_ID"
echo ""

# Route Table 1에 인터넷 라우트 추가
echo "🔧 Route Table 1 ($ROUTE_TABLE_1)에 인터넷 라우트 추가 중..."
aws ec2 create-route \
    --route-table-id $ROUTE_TABLE_1 \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Route Table 1 라우트 추가 완료"
else
    echo "❌ Route Table 1 라우트 추가 실패 (이미 존재할 수 있음)"
fi

# Route Table 2에 인터넷 라우트 추가
echo "🔧 Route Table 2 ($ROUTE_TABLE_2)에 인터넷 라우트 추가 중..."
aws ec2 create-route \
    --route-table-id $ROUTE_TABLE_2 \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID \
    --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ Route Table 2 라우트 추가 완료"
else
    echo "❌ Route Table 2 라우트 추가 실패 (이미 존재할 수 있음)"
fi

echo ""
echo "🎉 인터넷 접근 활성화 완료!"
echo "=================================================="

# 로드밸런서 URL 가져오기
echo "🔍 로드밸런서 URL 확인 중..."
LB_DNS=$(aws elbv2 describe-load-balancers \
    --query 'LoadBalancers[?VpcId==`'$VPC_ID'`].DNSName' \
    --output text \
    --region $REGION)

if [ ! -z "$LB_DNS" ] && [ "$LB_DNS" != "None" ]; then
    echo "🌐 접근 가능한 URL: http://$LB_DNS"
else
    echo "⚠️  로드밸런서 URL을 찾을 수 없습니다."
fi

echo ""
echo "📝 참고: 인터넷 접근을 다시 차단하려면 disable-internet.sh를 실행하세요."