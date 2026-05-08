"""LLM 명령 파싱 배치 도구 (ROS 무관 순수 Python 스크립트).

사용법:
    1. resource/commands.txt 에 명령을 한 줄에 하나씩 작성
    2. python3 src/cobot2/voice_processing/voice_processing/text_to_command.py
    3. resource/sequence.json 에 결과가 덮어쓰기 저장됨

입력  : resource/commands.txt   (한 줄 = 한 명령, 빈 줄/# 주석 무시)
출력  : resource/sequence.json  (실행할 때마다 덮어쓰기)
"""
import json
import os
import sys
from pathlib import Path

# 같은 디렉토리의 prompt.py 로드
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt import PROMPT_CONTENT  # noqa: E402

from langchain.prompts import PromptTemplate  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402


HERE = Path(__file__).resolve().parent              # .../voice_processing/voice_processing
PACKAGE_ROOT = HERE.parent                            # .../voice_processing
INPUT_FILE  = PACKAGE_ROOT / "resource" / "commands.txt"
OUTPUT_FILE = PACKAGE_ROOT / "resource" / "sequence.json"


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY 환경변수 없음. ~/.bashrc에 export 후 source 하세요.")
        return

    if not INPUT_FILE.exists():
        print(f"❌ 입력 파일 없음: {INPUT_FILE}")
        print(f"   파일을 만들고 한 줄에 하나씩 명령을 적어주세요.")
        print(f"   예:")
        print(f"     사과 버려줘")
        print(f"     컵 잡아")
        print(f"     병으로 컵에 부어줘")
        return

    # 입력 파일에서 명령 읽기 (빈 줄, # 주석 무시)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        commands = [
            line.strip() for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not commands:
        print(f"❌ {INPUT_FILE} 비어있음.")
        return

    print(f"📦 배치 모드: {len(commands)}개 명령 처리 시작")
    print(f"📄 입력:  {INPUT_FILE}")
    print(f"📄 출력:  {OUTPUT_FILE}\n")

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.0,
        openai_api_key=api_key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    template = PromptTemplate(input_variables=["user_input"], template=PROMPT_CONTENT)
    chain = template | llm

    records = []
    for i, cmd in enumerate(commands, 1):
        print(f"[{i}/{len(commands)}] {cmd}")
        try:
            response = chain.invoke({"user_input": cmd})
            result = json.loads(response.content)
            sequence = result.get("sequence", [])
            reply = str(result.get("reply", ""))

            records.append({
                "command": cmd,
                "sequence": sequence,
                "reply": reply,
            })

            print(f"    ✅ sequence: {sequence}")
            print(f"    💬 reply:    {reply}\n")
        except json.JSONDecodeError as e:
            print(f"    ❌ LLM JSON 파싱 실패: {e}\n")
            records.append({"command": cmd, "error": f"JSON parse error: {e}"})
        except Exception as e:
            print(f"    ❌ 에러: {e}\n")
            records.append({"command": cmd, "error": str(e)})

    # 결과 저장 (덮어쓰기)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"📦 완료: {len(records)}개 처리, {OUTPUT_FILE} 저장됨")


if __name__ == "__main__":
    main()
