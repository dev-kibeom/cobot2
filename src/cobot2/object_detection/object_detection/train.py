import os
import json
import shutil
from datetime import datetime
from ultralytics import YOLO

def train_and_update_model():
    print("🚀 모델 학습을 시작합니다... (데이터 증강 옵션 켜짐)")
    
    # 1. 모델 로드
    model = YOLO('yolov8n.pt') 
    
    # 2. 모델 학습 (데이터 증강 파라미터 대거 추가)
    results = model.train(
        data='custom_data.yaml', 
        epochs=50, 
        imgsz=640,
        
        # 🎨 색상/조명 증강 (형광등 밝기나 색온도 변화에 대비)
        hsv_h=0.015,        # 색상(Hue) 변화량
        hsv_s=0.7,          # 채도(Saturation) 변화량
        hsv_v=0.4,          # 명도(Value/Brightness) 변화량
        
        # 📐 공간/형태 증강 (물체가 삐딱하게 있거나 멀리 있을 때 대비)
        degrees=15.0,       # 이미지 회전 (±15도)
        translate=0.1,      # 상하좌우 이동 (10%)
        scale=0.5,          # 크기 확대/축소 (±50%)
        fliplr=0.5,         # 50% 확률로 좌우 반전
        flipud=0.5,         # 상하 반전 (물건이 뒤집히는 경우가 없다면 0.0으로 끄는 것이 좋습니다)
        
        # 🧩 고급 증강 기법
        mosaic=1.0,         # 4장의 이미지를 1장으로 잘라 붙이는 모자이크 증강 (100% 적용)
        mixup=0.1,          # 두 이미지를 겹쳐서 합성하는 기법 (10% 확률로 적용)
        close_mosaic=10     # 마지막 10에포크는 순정 데이터로 -> 정확도 향상
    )
    
    # 2. 경로 설정
    save_dir = model.trainer.save_dir
    target_dir = os.path.expanduser('~/cobot_ws/src/cobot2/object_detection/resource/')
    os.makedirs(target_dir, exist_ok=True)
    
    time_str = datetime.now().strftime("%Y%m%d_%H%M")
    
    # 3. class_name.json 생성 
    # 모델이 학습하며 스스로 정립한 클래스 번호와 이름을 그대로 추출합니다.
    class_map = model.model.names
    json_path = os.path.join(target_dir, 'class_name.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(class_map, f, ensure_ascii=False, indent=4)
    print(f"📄 클래스 맵 저장 완료: {json_path}")

    # 4. 모델 가중치 복사[cite: 13]
    source_weight = os.path.join(save_dir, "weights", "best.pt")
    new_model_name = f"best_{time_str}.pt"
    shutil.copy(source_weight, os.path.join(target_dir, new_model_name))
    # 상시 참조용 고정 이름으로도 하나 더 복사해두면 편리합니다.
    shutil.copy(source_weight, os.path.join(target_dir, "best_shaker.pt"))

    # 5. [추가] 평가지표 시각화 자료 추출
    # 학습 결과 폴더(runs/detect/trainX)에서 주요 차트만 골라냅니다.
    metrics_to_copy = [
        "results.png",           # 학습 곡선 (Loss, mAP 등)
        "confusion_matrix.png",   # 혼동 행렬 (어떤 물체랑 헷갈려하는지 확인용)
        "PR_curve.png",          # 정밀도-재현율 곡선
        "F1_curve.png",          # F1 스코어 곡선
        "val_batch0_labels.jpg"  # 실제 정답지 샘플
    ]
    
    eval_folder = os.path.join(target_dir, f"eval_{time_str}")
    os.makedirs(eval_folder, exist_ok=True)
    
    for filename in metrics_to_copy:
        src = os.path.join(save_dir, filename)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(eval_folder, filename))
            
    print(f"📊 평가지표 시각화 완료: {eval_folder}")
    print(f"✅ 모든 프로세스 완료! 최신 모델: {new_model_name}")

if __name__ == '__main__':
    train_and_update_model()