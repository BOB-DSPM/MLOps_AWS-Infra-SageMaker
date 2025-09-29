import os
import json
import logging
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import boto3
import pandas as pd
import numpy as np
import requests
from langchain.llms import Ollama
from langchain.schema import BaseMessage, HumanMessage
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# AWS 클라이언트 초기화
sagemaker_runtime = boto3.client('sagemaker-runtime')
sagemaker = boto3.client('sagemaker')
sagemaker_featurestore = boto3.client('sagemaker-featurestore-runtime')

# LangChain + Ollama 초기화 (폴백 처리)
try:
    # Ollama 서버 연결 시도 (컨테이너 내부 또는 외부)
    llm = Ollama(model="llama2:7b", base_url="http://host.docker.internal:11434")
    memory = ConversationBufferMemory()
    conversation = ConversationChain(llm=llm, memory=memory)
    llm_available = True
    logger.info("Ollama LLM initialized successfully")
except Exception as e:
    logger.warning(f"Ollama not available: {e}. Will use simple responses.")
    llm_available = False

# 환경 변수
ENDPOINT_NAME = os.environ.get('SAGEMAKER_ENDPOINT_NAME', 'my-mlops-dev-dev-endpoint')
MODEL_PACKAGE_GROUP = os.environ.get('MODEL_PACKAGE_GROUP', 'my-mlops-dev-dev-pkg')
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ap-northeast-2')
USER_INTERACTION_FG_NAME = os.environ.get('USER_INTERACTION_FG_NAME', 'my-mlops-dev-user-interactions')

# HTML 템플릿
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>테크뉴스 포털 - 최신 기술 소식</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f8f9fa;
        }
        
        /* 상단 헤더 */
        .header {
            background: #1e3a8a;
            color: white;
            padding: 15px 0;
            position: relative;
        }
        .header-content {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 20px;
        }
        .logo {
            font-size: 24px;
            font-weight: bold;
        }
        .nav {
            display: flex;
            gap: 30px;
        }
        .nav a {
            color: white;
            text-decoration: none;
            font-weight: 500;
        }
        
        /* 광고 버튼 스타일 */
        .ad-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        .ad-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        
        /* 광고 위치별 스타일 */
        .ad-header {
            position: absolute;
            right: 20px;
            top: 50%;
            transform: translateY(-50%);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 20px;
            padding: 20px;
        }
        
        .main-content {
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .ad-sidebar {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .ad-content {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            margin: 20px 0;
        }
        
        .ad-bottom {
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin-top: 30px;
        }
        
        .ad-popup {
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            z-index: 1000;
            max-width: 300px;
        }
        
        .user-info {
            background: #e3f2fd;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        
        input[type="number"] {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-sizing: border-box;
        }
        
        .article {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }
        
        .article h2 {
            color: #1e3a8a;
            margin-bottom: 10px;
        }
        
        .article-meta {
            color: #666;
            font-size: 12px;
            margin-bottom: 15px;
        }
        
        .stats {
            background: #f1f5f9;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
        }
        
        .click-count {
            font-weight: bold;
            color: #1e3a8a;
        }
    </style>
</head>
<body>
    <!-- 상단 헤더 광고 -->
    <div class="header">
        <div class="header-content">
            <div class="logo">📰 TechNews Portal</div>
            <nav class="nav">
                <a href="#tech">기술</a>
                <a href="#business">비즈니스</a>
                <a href="#startup">스타트업</a>
                <a href="#ai">AI/ML</a>
            </nav>
            <!-- 위치 1: 상단 헤더 광고 -->
            <button class="ad-btn ad-header" onclick="trackAdClick(1)">
                💻 최신 노트북 50% 할인!
            </button>
        </div>
    </div>

    <!-- 사용자 정보 입력 -->
    <div class="user-info" style="max-width: 1200px; margin: 20px auto; padding: 0 20px;">
        <h3>🔧 사용자 정보 설정</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
            <div class="form-group">
                <label for="user_age">나이</label>
                <input type="number" id="user_age" min="18" max="80" value="25">
            </div>
            <div class="form-group">
                <label for="browsing_history">브라우징 활성도 (0-10)</label>
                <input type="number" id="browsing_history" min="0" max="10" step="0.1" value="7.5">
            </div>
            <div class="form-group">
                <label for="time_of_day">현재 시간 (0-23)</label>
                <input type="number" id="time_of_day" min="0" max="23" value="14">
            </div>
            <div class="form-group">
                <label for="user_behavior_score">클릭 성향 (0-100)</label>
                <input type="number" id="user_behavior_score" min="0" max="100" step="0.1" value="65.5">
            </div>
        </div>
    </div>

    <div class="container">
        <main class="main-content">
            <h1>🚀 오늘의 주요 기술 뉴스</h1>
            
            <article class="article">
                <h2>OpenAI, GPT-5 모델 공개 임박... 성능 대폭 향상 예고</h2>
                <div class="article-meta">2025년 9월 20일 | 기자: 김테크</div>
                <p>인공지능 업계의 선두주자 OpenAI가 차세대 언어모델 GPT-5의 공개를 앞두고 있다고 발표했습니다. 새로운 모델은 기존 GPT-4 대비 추론 능력과 창의성에서 큰 향상을 보일 것으로 예상됩니다...</p>
                
                <!-- 위치 3: 본문 중간 광고 -->
                <div class="ad-content">
                    <h4>📱 AI 학습에 최적화된 클라우드 서비스</h4>
                    <p>GPU 성능 무제한! 첫 달 무료 체험</p>
                    <button class="ad-btn" onclick="trackAdClick(3)">
                        지금 시작하기 →
                    </button>
                </div>
                
                <p>업계 전문가들은 이번 발표가 AI 시장에 미칠 영향을 주목하고 있으며, 특히 자연어 처리와 코드 생성 분야에서의 혁신을 기대하고 있습니다...</p>
            </article>
            
            <article class="article">
                <h2>애플, 새로운 M4 칩셋으로 MacBook Pro 성능 혁신</h2>
                <div class="article-meta">2025년 9월 19일 | 기자: 박하드웨어</div>
                <p>애플이 차세대 M4 칩셋을 탑재한 MacBook Pro를 발표했습니다. 3나노 공정으로 제작된 새로운 칩은 이전 세대 대비 40% 향상된 성능을 제공합니다...</p>
            </article>
            
            <article class="article">
                <h2>메타, 메타버스 플랫폼에 AI 아바타 도입</h2>
                <div class="article-meta">2025년 9월 18일 | 기자: 이가상</div>
                <p>메타(구 페이스북)가 자사의 메타버스 플랫폼에 AI 기반 아바타 시스템을 도입한다고 발표했습니다. 사용자들은 이제 더욱 자연스럽고 지능적인 가상 캐릭터와 상호작용할 수 있게 됩니다...</p>
            </article>
            
            <!-- 위치 4: 본문 하단 광고 -->
            <div class="ad-bottom">
                <h3>🎯 개발자를 위한 특별 혜택!</h3>
                <p>코딩 부트캠프 등록 시 30% 할인 + 무료 멘토링</p>
                <button class="ad-btn" onclick="trackAdClick(4)">
                    할인 받기
                </button>
            </div>
        </main>
        
        <aside class="sidebar">
            <!-- 위치 2: 사이드바 광고 -->
            <div class="ad-sidebar">
                <h4>🔥 HOT DEAL</h4>
                <p>개발자용 모니터<br>최대 70% 할인!</p>
                <button class="ad-btn" onclick="trackAdClick(2)">
                    쇼핑하기
                </button>
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h3>📊 클릭 통계</h3>
                <div class="stats">
                    <div>총 광고 클릭: <span id="total-clicks" class="click-count">0</span></div>
                    <div>상단 헤더: <span id="header-clicks" class="click-count">0</span></div>
                    <div>사이드바: <span id="sidebar-clicks" class="click-count">0</span></div>
                    <div>본문 중간: <span id="content-clicks" class="click-count">0</span></div>
                    <div>본문 하단: <span id="bottom-clicks" class="click-count">0</span></div>
                    <div>팝업: <span id="popup-clicks" class="click-count">0</span></div>
                </div>
            </div>
        </aside>
    </div>
    
    <!-- 위치 5: 팝업 광고 -->
    <div class="ad-popup" id="popup-ad">
        <h4>🎉 신규 가입 이벤트</h4>
        <p>지금 가입하면 프리미엄 계정 1개월 무료!</p>
        <button class="ad-btn" onclick="trackAdClick(5)">
            가입하기
        </button>
        <button onclick="closePopup()" style="background: #666; margin-top: 10px;">
            닫기
        </button>
    </div>
                    <div class="field-description">
                        광고가 노출되는 시간대 (24시간 형식)
                    </div>
                    <input type="number" id="time_of_day" min="0" max="23" value="14" required>
                </div>
                <div class="form-group">
                    <label for="user_behavior_score">⭐ 클릭 성향 점수 (0-100점)</label>
                    <div class="field-description">
                        과거 광고 클릭 이력 기반 행동 패턴 점수<br>
                        0-30: 클릭 기피형, 31-70: 보통, 71-100: 적극 클릭형
                    </div>
                    <input type="number" id="user_behavior_score" min="0" max="100" step="0.1" value="65.5" required>
                </div>
            </div>
            <button type="submit">예측하기</button>
        </form>

        <div id="result" class="result">
            <div class="prediction-value" id="prediction-value"></div>
            <div id="prediction-details"></div>
            <div class="model-info" id="model-info"></div>
        </div>
    </div>

    <script>
        // 클릭 카운터
        let clickCounts = {
            total: 0,
            header: 0,
            sidebar: 0,
            content: 0,
            bottom: 0,
            popup: 0
        };
        
        // 세션 ID 생성
        function generateSessionId() {
            return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
        }
        
        let sessionId = generateSessionId();
        
        // 광고 클릭 추적 함수
        function trackAdClick(position) {
            const userAge = parseInt(document.getElementById('user_age').value) || 25;
            const browsingHistory = parseFloat(document.getElementById('browsing_history').value) || 7.5;
            const timeOfDay = parseInt(document.getElementById('time_of_day').value) || 14;
            const userBehaviorScore = parseFloat(document.getElementById('user_behavior_score').value) || 65.5;
            
            // 먼저 모델로 예측 수행
            const features = [userAge, position, browsingHistory, timeOfDay, userBehaviorScore];
            
            // 실제 클릭 데이터 전송 (클릭됨 = 1)
            const clickData = {
                features: features,
                actual_click: 1,  // 실제로 클릭했으므로 1
                session_id: sessionId,
                timestamp: new Date().toISOString()
            };
            
            // 서버로 클릭 데이터 전송
            fetch('/api/track-click', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(clickData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    console.log('클릭 데이터 전송 성공:', data);
                    
                    // 클릭 카운트 업데이트
                    clickCounts.total++;
                    switch(position) {
                        case 1: clickCounts.header++; break;
                        case 2: clickCounts.sidebar++; break;
                        case 3: clickCounts.content++; break;
                        case 4: clickCounts.bottom++; break;
                        case 5: clickCounts.popup++; break;
                    }
                    updateClickDisplay();
                    
                    // 클릭 애니메이션 효과
                    showClickFeedback(position, data.prediction_probability);
                } else {
                    console.error('클릭 데이터 전송 실패:', data.error);
                }
            })
            .catch(error => {
                console.error('네트워크 오류:', error);
            });
        }
        
        // 클릭 디스플레이 업데이트
        function updateClickDisplay() {
            document.getElementById('total-clicks').textContent = clickCounts.total;
            document.getElementById('header-clicks').textContent = clickCounts.header;
            document.getElementById('sidebar-clicks').textContent = clickCounts.sidebar;
            document.getElementById('content-clicks').textContent = clickCounts.content;
            document.getElementById('bottom-clicks').textContent = clickCounts.bottom;
            document.getElementById('popup-clicks').textContent = clickCounts.popup;
        }
        
        // 클릭 피드백 표시
        function showClickFeedback(position, probability) {
            const positionNames = {
                1: '상단 헤더',
                2: '사이드바', 
                3: '본문 중간',
                4: '본문 하단',
                5: '팝업'
            };
            
            const feedback = document.createElement('div');
            feedback.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                z-index: 10000;
                text-align: center;
                min-width: 300px;
            `;
            
            feedback.innerHTML = `
                <h3>🎯 광고 클릭 감지!</h3>
                <p><strong>위치:</strong> ${positionNames[position]}</p>
                <p><strong>예측 확률:</strong> ${(probability * 100).toFixed(1)}%</p>
                <p><strong>실제 결과:</strong> 클릭됨 ✅</p>
                <p style="font-size: 12px; margin-top: 15px; opacity: 0.8;">
                    데이터가 Feature Store에 저장되었습니다
                </p>
            `;
            
            document.body.appendChild(feedback);
            
            // 3초 후 제거
            setTimeout(() => {
                document.body.removeChild(feedback);
            }, 3000);
        }
        
        // 팝업 닫기
        function closePopup() {
            document.getElementById('popup-ad').style.display = 'none';
        }
        
        // 팝업 자동 표시 (10초 후)
        setTimeout(() => {
            const popup = document.getElementById('popup-ad');
            popup.style.display = 'block';
            
            // 팝업 애니메이션
            popup.style.transform = 'scale(0.8)';
            popup.style.opacity = '0';
            setTimeout(() => {
                popup.style.transition = 'all 0.3s ease';
                popup.style.transform = 'scale(1)';
                popup.style.opacity = '1';
            }, 100);
        }, 10000);
        
        // 현재 시간 자동 설정
        function updateCurrentTime() {
            const now = new Date();
            document.getElementById('time_of_day').value = now.getHours();
        }
        
        // 페이지 로드 시 현재 시간 설정
        window.addEventListener('load', function() {
            updateCurrentTime();
            
            // 환영 메시지
            setTimeout(() => {
                console.log('🚀 실제 광고 클릭 추적 시스템이 활성화되었습니다!');
                console.log('📊 사용자의 광고 클릭 행동이 실시간으로 Feature Store에 저장됩니다.');
            }, 1000);
        });
        
        // 1분마다 시간 업데이트
        setInterval(updateCurrentTime, 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """메인 페이지"""
    return render_template_string(
        HTML_TEMPLATE,
        endpoint_name=ENDPOINT_NAME,
        model_group=MODEL_PACKAGE_GROUP,
        region=AWS_REGION
    )

@app.route('/health')
def health():
    """헬스체크 엔드포인트"""
    try:
        # SageMaker 엔드포인트 상태 확인 (실패해도 OK)
        endpoint_status = 'UNKNOWN'
        try:
            response = sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)
            endpoint_status = response['EndpointStatus']
        except Exception as endpoint_error:
            logger.warning(f"Endpoint not available yet: {str(endpoint_error)}")
            endpoint_status = 'NOT_FOUND'
        
        return jsonify({
            'status': 'healthy',
            'endpoint_status': endpoint_status,
            'timestamp': datetime.utcnow().isoformat(),
            'app_status': 'running'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        # 기본적인 헬스체크는 항상 성공
        return jsonify({
            'status': 'healthy',
            'endpoint_status': 'UNKNOWN',
            'timestamp': datetime.utcnow().isoformat(),
            'note': 'basic_health_check'
        }), 503

def save_to_feature_store(interaction_data):
    """사용자 상호작용 데이터를 Feature Store에 저장"""
    try:
        # 현재 시간을 ISO 형식으로 변환
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        # Feature Store에 저장할 레코드 구성
        record = [
            {
                'FeatureName': 'interaction_id',
                'ValueAsString': interaction_data['interaction_id']
            },
            {
                'FeatureName': 'event_time',
                'ValueAsString': current_time
            },
            {
                'FeatureName': 'user_age',
                'ValueAsString': str(interaction_data.get('user_age', 0))
            },
            {
                'FeatureName': 'ad_position',
                'ValueAsString': str(interaction_data.get('ad_position', 0))
            },
            {
                'FeatureName': 'browsing_history',
                'ValueAsString': str(interaction_data.get('browsing_history', 0))
            },
            {
                'FeatureName': 'time_of_day',
                'ValueAsString': str(interaction_data.get('time_of_day', 0))
            },
            {
                'FeatureName': 'user_behavior_score',
                'ValueAsString': str(interaction_data.get('user_behavior_score', 0))
            },
            {
                'FeatureName': 'predicted_probability',
                'ValueAsString': str(interaction_data.get('predicted_probability', 0))
            },
            {
                'FeatureName': 'predicted_class',
                'ValueAsString': str(interaction_data.get('predicted_class', 0))
            },
            {
                'FeatureName': 'actual_click',
                'ValueAsString': str(interaction_data.get('actual_click', 0))
            },
            {
                'FeatureName': 'session_id',
                'ValueAsString': interaction_data.get('session_id', 'unknown')
            },
            {
                'FeatureName': 'request_type',
                'ValueAsString': interaction_data.get('request_type', 'prediction')
            },
            {
                'FeatureName': 'response_time_ms',
                'ValueAsString': str(interaction_data.get('response_time_ms', 0))
            }
        ]
        
        # Feature Store에 레코드 추가
        response = sagemaker_featurestore.put_record(
            FeatureGroupName=USER_INTERACTION_FG_NAME,
            Record=record
        )
        
        logger.info(f"Successfully saved interaction data to Feature Store: {interaction_data['interaction_id']}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save to Feature Store: {e}")
        return False


def generate_session_id():
    """세션 ID 생성"""
    return str(uuid.uuid4())


# 세션별 고유 ID (실제 구현에서는 Redis나 데이터베이스 사용 권장)
SESSION_STORE = {}


@app.route('/api/status')
def api_status():
    """엔드포인트 상태 API"""
    try:
        response = sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)
        return jsonify({
            'status': response['EndpointStatus'],
            'creation_time': response['CreationTime'].isoformat(),
            'last_modified_time': response['LastModifiedTime'].isoformat()
        })
    except Exception as e:
        logger.error(f"Status check failed: {str(e)}")
        return jsonify({
            'status': 'Error',
            'error': str(e)
        }), 500

def save_to_feature_store(interaction_data):
    """사용자 상호작용 데이터를 Feature Store에 저장"""
    try:
        # 현재 시간을 ISO 형식으로 변환
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        # Feature Store에 저장할 레코드 구성
        record = [
            {
                'FeatureName': 'interaction_id',
                'ValueAsString': interaction_data['interaction_id']
            },
            {
                'FeatureName': 'event_time',
                'ValueAsString': current_time
            },
            {
                'FeatureName': 'user_age',
                'ValueAsString': str(interaction_data.get('user_age', 0))
            },
            {
                'FeatureName': 'ad_position',
                'ValueAsString': str(interaction_data.get('ad_position', 0))
            },
            {
                'FeatureName': 'browsing_history',
                'ValueAsString': str(interaction_data.get('browsing_history', 0))
            },
            {
                'FeatureName': 'time_of_day',
                'ValueAsString': str(interaction_data.get('time_of_day', 0))
            },
            {
                'FeatureName': 'user_behavior_score',
                'ValueAsString': str(interaction_data.get('user_behavior_score', 0))
            },
            {
                'FeatureName': 'predicted_probability',
                'ValueAsString': str(interaction_data.get('predicted_probability', 0))
            },
            {
                'FeatureName': 'predicted_class',
                'ValueAsString': str(interaction_data.get('predicted_class', 0))
            },
            {
                'FeatureName': 'actual_click',
                'ValueAsString': str(interaction_data.get('actual_click', 0))
            },
            {
                'FeatureName': 'session_id',
                'ValueAsString': interaction_data.get('session_id', 'unknown')
            },
            {
                'FeatureName': 'request_type',
                'ValueAsString': interaction_data.get('request_type', 'prediction')
            },
            {
                'FeatureName': 'chat_query_length',
                'ValueAsString': str(interaction_data.get('chat_query_length', 0))
            },
            {
                'FeatureName': 'chat_category',
                'ValueAsString': interaction_data.get('chat_category', 'unknown')
            },
            {
                'FeatureName': 'response_time_ms',
                'ValueAsString': str(interaction_data.get('response_time_ms', 0))
            }
        ]
        
        # Feature Store에 레코드 추가
        response = sagemaker_featurestore.put_record(
            FeatureGroupName=USER_INTERACTION_FG_NAME,
            Record=record
        )
        
        logger.info(f"Successfully saved interaction data to Feature Store: {interaction_data['interaction_id']}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save to Feature Store: {e}")
        return False


def categorize_chat_query(message):
    """챗봇 질문을 카테고리로 분류"""
    message_lower = message.lower()
    
    if any(keyword in message_lower for keyword in ['클릭', 'click', '확률', 'probability']):
        return 'click_prediction'
    elif any(keyword in message_lower for keyword in ['위치', 'position', '배치']):
        return 'ad_positioning'
    elif any(keyword in message_lower for keyword in ['시간', 'time', '언제']):
        return 'timing_strategy'
    elif any(keyword in message_lower for keyword in ['나이', 'age', '연령']):
        return 'demographics'
    elif any(keyword in message_lower for keyword in ['전략', 'strategy', '방법', '개선']):
        return 'marketing_strategy'
    elif any(keyword in message_lower for keyword in ['안녕', 'hello', 'hi']):
        return 'greeting'
    else:
        return 'general_inquiry'


def generate_session_id():
    """세션 ID 생성"""
    return str(uuid.uuid4())


# 세션별 고유 ID (실제 구현에서는 Redis나 데이터베이스 사용 권장)
SESSION_STORE = {}


@app.route('/api/predict', methods=['POST'])
def predict():
    """모델 예측 API"""
    start_time = datetime.now()
    
    try:
        # 요청 데이터 파싱
        data = request.get_json()
        features = data.get('features', [])
        
        if len(features) != 5:
            return jsonify({
                'success': False,
                'error': '정확히 5개의 특성값이 필요합니다.'
            }), 400
        
        # CSV 형태로 변환 (XGBoost 모델 입력 형식)
        input_data = ','.join(map(str, features))
        
        logger.info(f"Sending prediction request: {input_data}")
        
        # SageMaker 엔드포인트 호출
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='text/csv',
            Body=input_data
        )
        
        # 응답 파싱
        result = response['Body'].read().decode('utf-8').strip()
        logger.info(f"Model response: {result}")
        
        # XGBoost는 확률값을 반환하므로 이를 클래스로 변환
        probability = float(result)
        prediction = 1 if probability > 0.5 else 0
        
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # 모델 정보 가져오기 (옵션)
        model_name = None
        try:
            endpoint_config = sagemaker.describe_endpoint_config(
                EndpointConfigName=sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)['EndpointConfigName']
            )
            model_name = endpoint_config['ProductionVariants'][0]['ModelName']
        except:
            pass
        
        # 세션 ID 생성 또는 가져오기
        session_id = data.get('session_id', generate_session_id())
        
        # Feature Store에 저장할 데이터 준비
        interaction_data = {
            'interaction_id': f"pred_{session_id}_{int(datetime.now().timestamp())}",
            'user_age': features[0],
            'ad_position': features[1],
            'browsing_history': features[2],
            'time_of_day': features[3],
            'user_behavior_score': features[4],
            'predicted_probability': probability,
            'predicted_class': prediction,
            'session_id': session_id,
            'request_type': 'prediction',
            'chat_query_length': 0,
            'chat_category': 'prediction_request',
            'response_time_ms': response_time
        }
        
        # Feature Store에 비동기적으로 저장 (실패해도 응답에는 영향 없음)
        save_to_feature_store(interaction_data)
        
        return jsonify({
            'success': True,
            'prediction': prediction,
            'probability': probability,
            'features': features,
            'response_time': round(response_time, 2),
            'model_name': model_name,
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return jsonify({
            'success': False,
            'error': str(e),
            'response_time': round(response_time, 2),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/api/track-click', methods=['POST'])
def track_click():
    """실제 광고 클릭 데이터 수집 API"""
    start_time = datetime.now()
    
    try:
        # 요청 데이터 파싱
        data = request.get_json()
        features = data.get('features', [])
        actual_click = data.get('actual_click', 1)  # 실제 클릭됨
        session_id = data.get('session_id', generate_session_id())
        
        if len(features) != 5:
            return jsonify({
                'success': False,
                'error': '정확히 5개의 특성값이 필요합니다.'
            }), 400
        
        # 모델 예측도 함께 수행하여 예측 vs 실제 비교
        input_data = ','.join(map(str, features))
        
        try:
            # SageMaker 엔드포인트 호출
            response = sagemaker_runtime.invoke_endpoint(
                EndpointName=ENDPOINT_NAME,
                ContentType='text/csv',
                Body=input_data
            )
            
            result = response['Body'].read().decode('utf-8').strip()
            probability = float(result)
            prediction = 1 if probability > 0.5 else 0
            
        except Exception as model_error:
            logger.warning(f"Model prediction failed during click tracking: {model_error}")
            probability = 0.5  # 기본값
            prediction = 0
        
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Feature Store에 저장할 실제 클릭 데이터 준비
        interaction_data = {
            'interaction_id': f"click_{session_id}_{int(datetime.now().timestamp())}",
            'user_age': features[0],
            'ad_position': features[1],
            'browsing_history': features[2],
            'time_of_day': features[3],
            'user_behavior_score': features[4],
            'predicted_probability': probability,
            'predicted_class': prediction,
            'actual_click': actual_click,  # 실제 클릭 결과
            'session_id': session_id,
            'request_type': 'actual_click',
            'chat_query_length': 0,
            'chat_category': 'ad_click',
            'response_time_ms': response_time
        }
        
        # Feature Store에 저장
        save_success = save_to_feature_store(interaction_data)
        
        logger.info(f"Tracked ad click - Position: {features[1]}, Predicted: {prediction}, Actual: {actual_click}, Probability: {probability:.3f}")
        
        return jsonify({
            'success': True,
            'actual_click': actual_click,
            'prediction': prediction,
            'prediction_probability': probability,
            'prediction_correct': (prediction == actual_click),
            'features': features,
            'session_id': session_id,
            'saved_to_feature_store': save_success,
            'response_time': round(response_time, 2),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Click tracking failed: {str(e)}")
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return jsonify({
            'success': False,
            'error': str(e),
            'response_time': round(response_time, 2),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/api/models')
def list_models():
    """모델 패키지 목록 API"""
    try:
        response = sagemaker.list_model_packages(
            ModelPackageGroupName=MODEL_PACKAGE_GROUP,
            ModelApprovalStatus='Approved',
            SortBy='CreationTime',
            SortOrder='Descending',
            MaxResults=10
        )
        
        models = []
        for package in response.get('ModelPackageSummaryList', []):
            models.append({
                'name': package['ModelPackageArn'].split('/')[-1],
                'status': package['ModelApprovalStatus'],
                'creation_time': package['CreationTime'].isoformat()
            })
        
        return jsonify({
            'success': True,
            'models': models,
            'total_count': len(models)
        })
        
    except Exception as e:
        logger.error(f"Failed to list models: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting inference app on port {port}")
    logger.info(f"SageMaker endpoint: {ENDPOINT_NAME}")
    logger.info(f"Model package group: {MODEL_PACKAGE_GROUP}")
    logger.info(f"AWS region: {AWS_REGION}")
    
    # Production에서는 Gunicorn 사용 권장
    if debug:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        from gunicorn.app.wsgiapp import WSGIApplication
        
        class StandaloneApplication(WSGIApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)
            
            def load(self):
                return self.application
        
        options = {
            'bind': f'0.0.0.0:{port}',
            'workers': 2,
            'worker_class': 'sync',
            'timeout': 120,
            'keepalive': 5,
            'max_requests': 1000,
            'preload_app': True,
        }
        
        StandaloneApplication(app, options).run()
