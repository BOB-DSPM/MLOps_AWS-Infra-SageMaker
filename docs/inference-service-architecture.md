# MLOps 추론 서비스 아키텍처 다이어그램

```mermaid
graph TB
    %% 사용자/클라이언트
    User[👤 사용자<br/>웹 브라우저]
    
    %% 추론 서비스 VPC (별도 VPC)
    subgraph InferenceVPC ["🌐 추론 서비스 VPC (독립적)"]
        ALB[🔄 Application Load Balancer<br/>Public Subnet]
        
        subgraph ECS ["📦 ECS Fargate Cluster"]
            subgraph InferenceApp ["🚀 추론 웹 애플리케이션<br/>Private Subnet"]
                WebApp[Flask 웹앱<br/>:8080]
                TaskRole[ECS Task Role<br/>추론 권한]
            end
        end
        
        subgraph Logs ["📊 로깅"]
            CloudWatchLogs[CloudWatch Logs<br/>애플리케이션 로그]
        end
    end
    
    %% 운영 MLOps VPC
    subgraph ProdVPC ["🏭 운영 MLOps VPC"]
        subgraph MLPipeline ["🔄 ML 파이프라인"]
            CodeCommit[📝 CodeCommit<br/>소스코드]
            CodePipeline[⚙️ CodePipeline<br/>CI/CD]
            CodeBuild1[🏗️ CodeBuild Train<br/>모델 훈련]
            ManualApproval[✋ Manual Approval<br/>수동 승인]
            CodeBuild2[🚀 CodeBuild Deploy<br/>모델 배포]
        end
        
        subgraph ModelRegistry ["📚 모델 레지스트리"]
            ModelPackageGroup[📦 Model Package Group<br/>my-mlops-prod-pkg]
            ApprovedModels[✅ Approved Models<br/>승인된 모델 버전들]
        end
        
        subgraph SageMakerInfra ["🧠 SageMaker 인프라"]
            SageMakerEndpoint[🎯 SageMaker Endpoint<br/>my-mlops-prod-endpoint<br/>ml.m5.large]
            SageMakerModel[🤖 SageMaker Model<br/>최신 승인 모델]
            EndpointConfig[⚙️ Endpoint Config<br/>인스턴스 설정]
        end
        
        subgraph DataStore ["💾 데이터 저장소"]
            FeatureStore[🏪 Feature Store<br/>my-mlops-feature-group-v2<br/>(공유)]
            UserInteractionFS[👥 User Interaction<br/>Feature Store<br/>my-mlops-user-interactions-v1]
            S3Bucket[🪣 S3 Data Bucket<br/>훈련/모델 데이터]
        end
    end
    
    %% AWS Shared Services
    subgraph AWSServices ["☁️ AWS 공유 서비스"]
        IAM[🔐 IAM Roles & Policies<br/>권한 관리]
        CloudWatch[📈 CloudWatch<br/>모니터링 & 알람]
        KMS[🔑 KMS<br/>암호화 키]
    end
    
    %% 플로우: 사용자 요청
    User -->|HTTPS 요청| ALB
    ALB -->|로드밸런싱| WebApp
    
    %% 플로우: 모델 추론
    WebApp -->|🔍 invoke_endpoint<br/>CSV 데이터| SageMakerEndpoint
    SageMakerEndpoint -->|🎯 예측 결과<br/>확률값| WebApp
    WebApp -->|📊 상호작용 로그| UserInteractionFS
    
    %% 플로우: 모델 배포 파이프라인
    CodeCommit -->|트리거| CodePipeline
    CodePipeline -->|단계 1| CodeBuild1
    CodeBuild1 -->|훈련 완료<br/>PendingManualApproval| ModelPackageGroup
    ModelPackageGroup -->|승인 대기| ManualApproval
    ManualApproval -->|✅ 승인| CodeBuild2
    CodeBuild2 -->|최신 Approved 모델<br/>조회 & 배포| SageMakerEndpoint
    
    %% 플로우: 모델 업데이트
    ApprovedModels -->|최신 승인 모델| SageMakerModel
    SageMakerModel -->|모델 참조| SageMakerEndpoint
    EndpointConfig -->|인스턴스 설정| SageMakerEndpoint
    
    %% 플로우: 데이터 흐름
    FeatureStore -->|훈련 데이터| CodeBuild1
    S3Bucket -->|모델 아티팩트| SageMakerModel
    
    %% 플로우: 모니터링 & 권한
    TaskRole -.->|추론 권한| SageMakerEndpoint
    TaskRole -.->|로그 권한| UserInteractionFS
    WebApp -->|애플리케이션 로그| CloudWatchLogs
    CloudWatchLogs -->|통합 모니터링| CloudWatch
    
    %% 환경 변수 설정
    WebApp -.->|환경변수<br/>SAGEMAKER_ENDPOINT_NAME=<br/>my-mlops-prod-endpoint| SageMakerEndpoint
    WebApp -.->|환경변수<br/>MODEL_PACKAGE_GROUP=<br/>my-mlops-prod-pkg| ModelPackageGroup
    
    %% 스타일링
    classDef userClass fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef inferenceClass fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef prodClass fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef dataClass fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef awsClass fill:#fafafa,stroke:#424242,stroke-width:2px
    
    class User userClass
    class ALB,WebApp,TaskRole,CloudWatchLogs inferenceClass
    class CodeCommit,CodePipeline,CodeBuild1,CodeBuild2,ManualApproval,ModelPackageGroup,ApprovedModels,SageMakerEndpoint,SageMakerModel,EndpointConfig prodClass
    class FeatureStore,UserInteractionFS,S3Bucket dataClass
    class IAM,CloudWatch,KMS awsClass
```

## 🔄 **핵심 연결 흐름**

### 1️⃣ **모델 배포 흐름** (운영 → 추론 서비스)
```
개발자 코드 커밋 
→ CodePipeline 트리거 
→ 모델 훈련 (CodeBuild) 
→ Model Package 생성 (PendingManualApproval)
→ 수동 승인 
→ 최신 Approved 모델을 SageMaker Endpoint에 배포
→ 추론 서비스가 자동으로 새 모델 사용
```

### 2️⃣ **실시간 추론 흐름** (사용자 → 추론 서비스 → 운영 모델)
```
사용자 웹 요청 
→ ALB → ECS Fargate 
→ Flask 웹앱 → SageMaker Endpoint 호출
→ 모델 예측 결과 반환 
→ 사용자 상호작용 Feature Store 저장
→ 결과를 사용자에게 반환
```

### 3️⃣ **권한 & 보안 흐름**
```
ECS Task Role 
→ SageMaker Endpoint 호출 권한
→ Feature Store 쓰기 권한  
→ CloudWatch 로그 권한
```

### 4️⃣ **환경 변수 연결**
```python
# inference_app 컨테이너 환경변수
SAGEMAKER_ENDPOINT_NAME = "my-mlops-prod-endpoint"  # 운영 엔드포인트
MODEL_PACKAGE_GROUP = "my-mlops-prod-pkg"          # 운영 모델 그룹
USER_INTERACTION_FG_NAME = "my-mlops-user-interactions-v1"  # 공유 Feature Store
```

## 🎯 **핵심 포인트**

1. **완전 분리된 VPC**: 추론 서비스는 별도 VPC에서 독립 운영
2. **크로스 VPC 모델 참조**: 추론 VPC → 운영 VPC의 SageMaker Endpoint 호출
3. **자동 모델 업데이트**: 운영에서 새 모델 승인 시 추론 서비스는 자동으로 최신 모델 사용
4. **공유 Feature Store**: 추론 로그는 운영과 동일한 Feature Store에 저장
5. **권한 기반 접근**: IAM Role을 통한 세분화된 권한 관리

이 구조로 **추론 서비스는 완전히 독립적이면서도 운영 모델을 실시간으로 활용**할 수 있습니다! 🚀
