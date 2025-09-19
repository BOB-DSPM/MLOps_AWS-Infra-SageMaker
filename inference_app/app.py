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
ENDPOINT_NAME = os.environ.get('SAGEMAKER_ENDPOINT_NAME', 'my-mlops-dev-endpoint')
MODEL_PACKAGE_GROUP = os.environ.get('MODEL_PACKAGE_GROUP', 'my-mlops-dev-pkg')
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ap-northeast-2')
USER_INTERACTION_FG_NAME = os.environ.get('USER_INTERACTION_FG_NAME', 'my-mlops-dev-user-interactions')

# HTML 템플릿
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MLOps 모델 추론 서비스</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
        }
        .info-section {
            background: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #34495e;
        }
        .field-description {
            color: #7f8c8d;
            font-size: 12px;
            display: block;
            margin-bottom: 8px;
            line-height: 1.4;
            background: #f8f9fa;
            padding: 8px;
            border-radius: 3px;
            border-left: 3px solid #3498db;
        }
        input[type="number"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #bdc3c7;
            border-radius: 5px;
            font-size: 16px;
            box-sizing: border-box;
        }
        input[type="number"]:focus {
            border-color: #3498db;
            outline: none;
            box-shadow: 0 0 5px rgba(52, 152, 219, 0.3);
        }
        button {
            background: #3498db;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            width: 100%;
            margin-top: 10px;
        }
        button:hover {
            background: #2980b9;
        }
        .result {
            margin-top: 20px;
            padding: 20px;
            border-radius: 5px;
            display: none;
        }
        .result.success {
            background: #d5f4e6;
            border: 1px solid #27ae60;
            color: #27ae60;
        }
        .result.error {
            background: #f8d7da;
            border: 1px solid #e74c3c;
            color: #e74c3c;
        }
        .prediction-value {
            font-size: 24px;
            font-weight: bold;
            text-align: center;
            margin: 10px 0;
        }
        .model-info {
            font-size: 12px;
            color: #7f8c8d;
            margin-top: 10px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 MLOps 모델 추론 서비스</h1>
        
        <div class="info-section">
            <h3>📊 모델 정보</h3>
            <p><strong>엔드포인트:</strong> {{ endpoint_name }}</p>
            <p><strong>모델 그룹:</strong> {{ model_group }}</p>
            <p><strong>리전:</strong> {{ region }}</p>
            <p><strong>상태:</strong> <span id="endpoint-status">확인 중...</span></p>
        </div>

        <h3>🔮 광고 클릭 예측하기</h3>
        <p>광고 클릭 여부를 예측하는 XGBoost 모델입니다. 각 항목의 의미를 참고하여 값을 입력해주세요:</p>
        
        <form id="prediction-form">
            <div class="grid">
                <div class="form-group">
                    <label for="user_age">👤 사용자 나이 (18-80세)</label>
                    <div class="field-description">
                        광고 대상 사용자의 연령대
                    </div>
                    <input type="number" id="user_age" min="18" max="80" value="25" required>
                </div>
                <div class="form-group">
                    <label for="ad_position">📍 광고 위치 (1-5번)</label>
                    <div class="field-description">
                        웹페이지 내 광고 배치 위치<br>
                        1: 상단헤더, 2: 사이드바, 3: 본문중간, 4: 본문하단, 5: 팝업
                    </div>
                    <input type="number" id="ad_position" min="1" max="5" value="2" required>
                </div>
                <div class="form-group">
                    <label for="browsing_history">📊 브라우징 활성도 (0-10점)</label>
                    <div class="field-description">
                        최근 30일간 웹사이트 방문 빈도 및 체류시간 기반 점수<br>
                        0-3: 낮음, 4-6: 보통, 7-10: 높음
                    </div>
                    <input type="number" id="browsing_history" min="0" max="10" step="0.1" value="7.5" required>
                </div>
                <div class="form-group">
                    <label for="time_of_day">🕐 광고 노출 시간 (0-23시)</label>
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

        <!-- AI 챗봇 섹션 -->
        <div style="margin-top: 40px; border-top: 2px solid #ecf0f1; padding-top: 30px;">
            <h3>🤖 AI 어시스턴트</h3>
            <p>광고 예측에 대한 질문이나 마케팅 조언을 받아보세요!</p>
            
            <div id="chat-container" style="border: 1px solid #bdc3c7; border-radius: 10px; height: 300px; overflow-y: auto; padding: 15px; background: #f8f9fa; margin-bottom: 15px;">
                <div id="chat-messages"></div>
            </div>
            
            <div style="display: flex; gap: 10px;">
                <input type="text" id="chat-input" placeholder="예: 25세 사용자의 클릭률을 높이려면?" 
                       style="flex: 1; padding: 12px; border: 1px solid #bdc3c7; border-radius: 5px; font-size: 16px;">
                <button onclick="sendMessage()" id="chat-button" 
                        style="padding: 12px 20px; background: #27ae60; color: white; border: none; border-radius: 5px; cursor: pointer;">
                    전송
                </button>
            </div>
            
            <div style="margin-top: 10px; font-size: 12px; color: #7f8c8d;">
                💡 팁: "클릭률 높이는 방법", "광고 위치 효과", "시간대별 전략" 등을 물어보세요!
            </div>
        </div>
    </div>

    <script>
        // 페이지 로드 시 엔드포인트 상태 확인
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                document.getElementById('endpoint-status').textContent = data.status;
                document.getElementById('endpoint-status').style.color = 
                    data.status === 'InService' ? '#27ae60' : '#e74c3c';
            })
            .catch(error => {
                document.getElementById('endpoint-status').textContent = '오류';
                document.getElementById('endpoint-status').style.color = '#e74c3c';
            });

        // 예측 폼 제출
        document.getElementById('prediction-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const features = [
                parseFloat(document.getElementById('user_age').value),
                parseFloat(document.getElementById('ad_position').value),
                parseFloat(document.getElementById('browsing_history').value),
                parseFloat(document.getElementById('time_of_day').value),
                parseFloat(document.getElementById('user_behavior_score').value)
            ];

            const button = e.target.querySelector('button');
            button.textContent = '예측 중...';
            button.disabled = true;

            fetch('/api/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ features: features })
            })
            .then(response => response.json())
            .then(data => {
                const resultDiv = document.getElementById('result');
                const predictionValue = document.getElementById('prediction-value');
                const predictionDetails = document.getElementById('prediction-details');
                const modelInfo = document.getElementById('model-info');

                if (data.success) {
                    resultDiv.className = 'result success';
                    const probability = data.probability;
                    const prediction = data.prediction;
                    
                    predictionValue.textContent = prediction === 1 ? 
                        '🎯 클릭할 가능성이 높습니다!' : 
                        '❌ 클릭하지 않을 가능성이 높습니다.';
                    
                    predictionDetails.innerHTML = `
                        <p><strong>클릭 확률:</strong> ${(probability * 100).toFixed(2)}%</p>
                        <p><strong>예측 결과:</strong> ${prediction === 1 ? '클릭 예상' : '클릭 안함 예상'}</p>
                        <div style="margin-top: 15px; font-size: 14px; background: #f8f9fa; padding: 15px; border-radius: 5px;">
                            <p><strong>📋 입력된 사용자 프로필 분석:</strong></p>
                            <ul style="margin: 10px 0; padding-left: 20px; line-height: 1.6;">
                                <li><strong>나이:</strong> ${features[0]}세 (${features[0] < 25 ? '젊은층' : features[0] < 40 ? '중년층' : '장년층'})</li>
                                <li><strong>광고 위치:</strong> ${features[1]}번 (${
                                    features[1] == 1 ? '상단헤더 - 높은 노출도' :
                                    features[1] == 2 ? '사이드바 - 중간 노출도' :
                                    features[1] == 3 ? '본문중간 - 자연스러운 노출' :
                                    features[1] == 4 ? '본문하단 - 낮은 노출도' :
                                    '팝업 - 강제 노출'
                                })</li>
                                <li><strong>브라우징 활성도:</strong> ${features[2]}점 (${
                                    features[2] < 4 ? '낮음 - 비활성 사용자' :
                                    features[2] < 7 ? '보통 - 일반 사용자' :
                                    '높음 - 활성 사용자'
                                })</li>
                                <li><strong>노출 시간:</strong> ${features[3]}시 (${
                                    features[3] < 6 ? '새벽시간대' :
                                    features[3] < 12 ? '오전시간대' :
                                    features[3] < 18 ? '오후시간대' :
                                    '저녁시간대'
                                })</li>
                                <li><strong>클릭 성향:</strong> ${features[4]}점 (${
                                    features[4] < 31 ? '클릭 기피형 - 광고 회피 성향' :
                                    features[4] < 71 ? '보통 - 일반적인 클릭 패턴' :
                                    '적극 클릭형 - 광고에 관심 많음'
                                })</li>
                            </ul>
                        </div>
                    `;
                    
                    modelInfo.textContent = `응답 시간: ${data.response_time}ms | 모델 버전: ${data.model_name || 'Unknown'}`;
                } else {
                    resultDiv.className = 'result error';
                    predictionValue.textContent = '예측 실패';
                    predictionDetails.innerHTML = `<p>오류: ${data.error}</p>`;
                    modelInfo.textContent = '';
                }

                resultDiv.style.display = 'block';
            })
            .catch(error => {
                const resultDiv = document.getElementById('result');
                resultDiv.className = 'result error';
                resultDiv.style.display = 'block';
                document.getElementById('prediction-value').textContent = '네트워크 오류';
                document.getElementById('prediction-details').innerHTML = `<p>${error.message}</p>`;
            })
            .finally(() => {
                button.textContent = '예측하기';
                button.disabled = false;
            });
        });

        // 챗봇 기능
        function sendMessage() {
            const input = document.getElementById('chat-input');
            const button = document.getElementById('chat-button');
            const message = input.value.trim();
            
            if (!message) return;
            
            // 사용자 메시지 추가
            addMessage('user', message);
            
            // 입력 필드 초기화 및 버튼 비활성화
            input.value = '';
            button.textContent = '전송 중...';
            button.disabled = true;
            
            // AI 응답 요청
            fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addMessage('assistant', data.response, data.model);
                } else {
                    addMessage('assistant', '죄송합니다. 오류가 발생했습니다: ' + data.error);
                }
            })
            .catch(error => {
                addMessage('assistant', '네트워크 오류가 발생했습니다. 다시 시도해주세요.');
            })
            .finally(() => {
                button.textContent = '전송';
                button.disabled = false;
                input.focus();
            });
        }
        
        function addMessage(sender, text, model = null) {
            const chatMessages = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.style.marginBottom = '15px';
            
            if (sender === 'user') {
                messageDiv.innerHTML = `
                    <div style="text-align: right;">
                        <div style="display: inline-block; background: #3498db; color: white; padding: 10px; border-radius: 10px; max-width: 70%; text-align: left;">
                            <strong>👤 사용자:</strong><br>${text}
                        </div>
                    </div>
                `;
            } else {
                const modelInfo = model ? ` (${model})` : '';
                messageDiv.innerHTML = `
                    <div style="text-align: left;">
                        <div style="display: inline-block; background: white; border: 1px solid #27ae60; color: #2c3e50; padding: 10px; border-radius: 10px; max-width: 70%;">
                            <strong>🤖 AI 어시스턴트${modelInfo}:</strong><br><pre style="white-space: pre-wrap; margin: 5px 0 0 0; font-family: inherit;">${text}</pre>
                        </div>
                    </div>
                `;
            }
            
            chatMessages.appendChild(messageDiv);
            
            // 스크롤을 아래로
            const chatContainer = document.getElementById('chat-container');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        // Enter 키로 메시지 전송
        document.getElementById('chat-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        // 초기 환영 메시지
        window.addEventListener('load', function() {
            setTimeout(() => {
                addMessage('assistant', 
                    '안녕하세요! 👋 광고 클릭 예측 AI 어시스턴트입니다.\\n\\n다음과 같은 질문을 도와드릴 수 있어요:\\n• 광고 클릭률을 높이는 방법\\n• 예측 모델 사용법\\n• 마케팅 전략 조언\\n• 사용자 세그먼트 분석\\n\\n무엇이든 물어보세요! 🤖', 
                    'Rule-based'
                );
            }, 1000);
        });
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

@app.route('/api/chat', methods=['POST'])
def chat():
    """AI 챗봇 엔드포인트"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        session_id = data.get('session_id', generate_session_id())
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': '메시지가 필요합니다.'
            }), 400
        
        start_time = datetime.now()
        chat_category = categorize_chat_query(user_message)
        
        if llm_available:
            # LangChain + Ollama 사용
            try:
                # 광고 예측 컨텍스트 추가
                system_context = """당신은 광고 클릭 예측 전문가입니다. 
                사용자의 질문에 대해 마케팅과 광고 관점에서 도움이 되는 답변을 제공하세요.
                현재 시스템은 XGBoost 모델을 사용하여 광고 클릭 확률을 예측합니다."""
                
                full_message = f"{system_context}\n\n사용자 질문: {user_message}"
                response = conversation.predict(input=full_message)
                
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                model_used = 'Llama2-7B'
                
            except Exception as e:
                logger.error(f"LLM error: {e}")
                # 폴백 응답
                response = get_fallback_response(user_message)
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                model_used = 'Fallback'
        else:
            # LLM 사용 불가시 간단한 규칙 기반 응답
            response = get_fallback_response(user_message)
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            model_used = 'Rule-based'
        
        # Feature Store에 저장할 데이터 준비
        interaction_data = {
            'interaction_id': f"chat_{session_id}_{int(datetime.now().timestamp())}",
            'user_age': 0,  # 챗봇에서는 알 수 없음
            'ad_position': 0,
            'browsing_history': 0,
            'time_of_day': datetime.now().hour,
            'user_behavior_score': 0,
            'predicted_probability': 0,
            'predicted_class': 0,
            'session_id': session_id,
            'request_type': 'chat',
            'chat_query_length': len(user_message),
            'chat_category': chat_category,
            'response_time_ms': response_time
        }
        
        # Feature Store에 비동기적으로 저장
        save_to_feature_store(interaction_data)
        
        return jsonify({
            'success': True,
            'response': response,
            'response_time': round(response_time, 2),
            'model': model_used,
            'session_id': session_id,
            'chat_category': chat_category,
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_fallback_response(message):
    """LLM 사용 불가시 폴백 응답"""
    message_lower = message.lower()
    
    if '클릭' in message or 'click' in message_lower:
        return """광고 클릭률에 영향을 주는 주요 요인들:
        
📊 **높은 클릭률 조건:**
- 젊은 연령층 (20-35세)
- 상단헤더나 본문중간 위치
- 높은 브라우징 활성도 (7-10점)
- 오후~저녁 시간대 (12-18시)
- 적극적 클릭 성향 (70점 이상)

📉 **낮은 클릭률 조건:**
- 고령층 (60세 이상)
- 팝업이나 하단 위치  
- 낮은 브라우징 활성도 (0-3점)
- 새벽 시간대 (0-6시)
- 클릭 기피 성향 (30점 이하)"""
    
    elif '예측' in message or 'predict' in message_lower:
        return """현재 XGBoost 모델이 다음 5가지 특성으로 광고 클릭을 예측합니다:

1. 👤 사용자 나이
2. 📍 광고 위치 
3. 📊 브라우징 활성도
4. 🕐 광고 노출 시간
5. ⭐ 클릭 성향 점수

위 입력 폼에서 값을 조정하여 다양한 시나리오를 테스트해보세요!"""
    
    elif '안녕' in message or 'hello' in message_lower or 'hi' in message_lower:
        return """안녕하세요! 👋 광고 클릭 예측 AI 어시스턴트입니다.

다음과 같은 질문을 도와드릴 수 있어요:
- 광고 클릭률을 높이는 방법
- 예측 모델 사용법
- 마케팅 전략 조언
- 사용자 세그먼트 분석

무엇이든 물어보세요! 🤖"""
    
    else:
        return f""""{message}"에 대한 질문을 받았습니다.

광고 클릭 예측과 관련된 더 구체적인 질문을 해주시면 더 도움이 되는 답변을 드릴 수 있어요!

예를 들어:
- "25세 사용자의 클릭률을 높이려면?"
- "사이드바 광고의 효과는?"
- "오후 시간대 광고 전략은?"

🤖 현재는 간단한 규칙 기반 응답을 제공하고 있습니다."""


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
