import os
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
    
    # 3. 이번 학습의 결과물 원본 경로 확인
    source_weight = f"{model.trainer.save_dir}/weights/best.pt"
    
    # 4. ROS 2 패키지 리소스 폴더로 복사
    target_dir = os.path.expanduser('~/cobot_ws/src/object_detection/resource/')
    os.makedirs(target_dir, exist_ok=True)
    
    time_str = datetime.now().strftime("%Y%m%d_%H%M")
    new_filename = f"best_{time_str}.pt"
    target_weight = os.path.join(target_dir, new_filename)
    
    shutil.copy(source_weight, target_weight)
    
    print(f"✅ 학습 완료!")
    print(f"👉 저장된 최신 모델: {new_filename}")

if __name__ == '__main__':
    train_and_update_model()