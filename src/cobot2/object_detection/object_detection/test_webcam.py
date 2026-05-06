import cv2
import os
import glob
import time
from ultralytics import YOLO

# 1. 최신 모델 자동 로드 (기존과 동일)
target_dir = os.path.expanduser('~/cobot_ws/src/object_detection/resource/')
pt_files = glob.glob(os.path.join(target_dir, '*.pt'))

if not pt_files:
    print(f"❌ '{target_dir}' 경로에 모델 파일(.pt)이 없습니다!")
    exit()

latest_model_path = max(pt_files, key=os.path.getctime)
model_name = os.path.basename(latest_model_path)

print(f"🧠 성능 분석기 로딩 중... [모델: {model_name}]")
model = YOLO(latest_model_path)

# 2. 웹캠 켜기
camera_id = 0
cap = cv2.VideoCapture(camera_id)

if not cap.isOpened():
    print(f"❌ {camera_id}번 웹캠을 열 수 없습니다.")
    exit()

print("🟢 실시간 성능 분석이 시작되었습니다. (종료: 'q' 키)")

# FPS 계산용 변수
prev_time = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # FPS 측정을 위한 시작 시간
    current_time = time.time()

    # YOLO 추론 진행 (성능 분석을 위해 verbose 끔)
    results = model(frame, conf=0.5, verbose=False)

    # ---------------------------------------------------------
    # 📊 성능 지표 계산
    # ---------------------------------------------------------
    # 1. FPS 계산
    fps = 1 / (current_time - prev_time) if prev_time > 0 else 0
    prev_time = current_time

    # 2. 평균 신뢰도(Confidence) 계산
    conf_list = results[0].boxes.conf.cpu().numpy()
    avg_conf = conf_list.mean() if len(conf_list) > 0 else 0.0
    detected_count = len(conf_list)

    # 기본 박스 그리기
    annotated_frame = results[0].plot()

    # ---------------------------------------------------------
    # 📺 화면에 성능 지표(HUD) 출력
    # ---------------------------------------------------------
    # 배경 박스 (텍스트가 잘 보이도록)
    cv2.rectangle(annotated_frame, (10, 10), (350, 100), (0, 0, 0), -1)
    
    # 텍스트 출력
    cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (20, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(annotated_frame, f"Avg Conf: {avg_conf:.2f}", (20, 65), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(annotated_frame, f"Detected: {detected_count} objects", (20, 90), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    # 화면 출력
    cv2.imshow(f"Vision AI Performance - {model_name}", annotated_frame)

    # 'q' 누르면 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("🛑 성능 분석 종료")