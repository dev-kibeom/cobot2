import cv2
import os
import glob
import time
import numpy as np
import argparse
from ultralytics import YOLO

def main():
    # ---------------------------------------------------------
    # ⚙️ 실행 옵션 설정
    # ---------------------------------------------------------
    parser = argparse.ArgumentParser(description="Vision AI 성능 독립 테스트기")
    parser.add_argument('--camera', type=str, default='webcam', choices=['webcam', 'realsense'],
                        help="사용할 카메라 선택: 'webcam' 또는 'realsense'")
    parser.add_argument('--conf', type=float, default=0.2, 
                        help="객체 탐지 신뢰도 임계값 설정")
    args = parser.parse_args()

    # 1. 모델 로드
    target_dir = os.path.expanduser('~/cobot_ws/src/cobot2/object_detection/resource/')
    pt_files = glob.glob(os.path.join(target_dir, 'best_shaker.pt'))

    if not pt_files:
        print(f"❌ '{target_dir}' 경로에 모델 파일(.pt)이 없습니다!")
        return

    latest_model_path = max(pt_files, key=os.path.getctime)
    model_name = os.path.basename(latest_model_path)
    print(f"🧠 모델 로딩 중... [파일: {model_name}]")
    model = YOLO(latest_model_path)

    # 2. 카메라 초기화
    if args.camera == 'realsense':
        try:
            import pyrealsense2 as rs
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            pipeline.start(config)
            print("🟢 Realsense 연결 성공!")
        except Exception as e:
            print(f"❌ Realsense 연결 실패: {e}")
            return
    else:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ 웹캠을 열 수 없습니다.")
            return
        print("🟢 웹캠 연결 성공!")

    prev_time = 0
    try:
        while True:
            if args.camera == 'realsense':
                frames = pipeline.wait_for_frames()
                color_frame = frames.get_color_frame()
                if not color_frame: continue
                frame = np.asanyarray(color_frame.get_data())
            else:
                ret, frame = cap.read()
                if not ret: break

            current_time = time.time()
            
            # ---------------------------------------------------------
            # 4. YOLO 추론 (설정된 conf 값 적용)
            # ---------------------------------------------------------
            results = model(frame, conf=args.conf, verbose=False)
            
            fps = 1 / (current_time - prev_time) if prev_time > 0 else 0
            prev_time = current_time

            conf_list = results[0].boxes.conf.cpu().numpy()
            cls_list = results[0].boxes.cls.cpu().numpy()
            detected_count = len(conf_list)
            annotated_frame = results[0].plot()

            # HUD 출력
            box_height = 100 + (detected_count * 25)
            cv2.rectangle(annotated_frame, (10, 10), (350, box_height), (0, 0, 0), -1)
            cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"Detected: {detected_count}", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            for i in range(detected_count):
                score, cls_id = conf_list[i], int(cls_list[i])
                class_name = model.names[cls_id] if cls_id in model.names else f"ID {cls_id}"
                cv2.putText(annotated_frame, f"-> {class_name}: {score:.2f}", (20, 110 + (i * 25)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            cv2.imshow(f"Vision Test [{args.camera}]", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
    # 6. 자원 해제
    finally:
        if args.camera == 'realsense':
            pipeline.stop()
        else:
            cap.release()
        cv2.destroyAllWindows()
        print("🛑 테스트 종료")

if __name__ == '__main__':
    main()