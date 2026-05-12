#include <behaviortree_cpp_v3/action_node.h>
#include <queue>
#include <string>
#include <iostream>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

struct Task {
    std::string action;
    std::string target;
};

class PopNextTask : public BT::SyncActionNode {
private:
    std::queue<Task> task_queue_;
    std::string last_parsed_json_ = ""; // 중복 파싱 방지용 기억 장치

public:
    PopNextTask(const std::string& name, const BT::NodeConfiguration& config)
        : BT::SyncActionNode(name, config) {}

    static BT::PortsList providedPorts() {
        return { 
            BT::InputPort<std::string>("llm_json"), // 💡 LLM이 주는 JSON 문자열을 받을 입력 포트
            BT::OutputPort<std::string>("action_name"),
            BT::OutputPort<std::string>("target_name")
        };
    }

    BT::NodeStatus tick() override {
        std::string json_str;
        
        // 1. 블랙보드에서 JSON 문자열을 읽어옵니다. (새로운 문자열이 들어오면 파싱!)
        if (getInput<std::string>("llm_json", json_str) && !json_str.empty() && json_str != last_parsed_json_) {
            try {
                std::cout << "[PopNextTask] 📥 새로운 LLM 명령 수신, 파싱 시작...\n";
                json j_array = json::parse(json_str);
                
                // 기존 큐 비우기
                while(!task_queue_.empty()) task_queue_.pop(); 

                // 전체 시퀀스 맨 처음으로 reset 주입
                task_queue_.push({"reset", "none"});
                
                // LLM이 지시한 테스크들을 큐에 순차 삽입
                for (const auto& item : j_array) {
                    Task t;
                    t.action = item["action"];
                    if (item.contains("params") && item["params"].contains("target")) {
                        t.target = item["params"]["target"];
                    } else {
                        t.target = "none";
                    }
                    task_queue_.push(t);
                }
                last_parsed_json_ = json_str; // 파싱 완료 기록
                std::cout << "[PopNextTask] ✅ 총 " << task_queue_.size() << "개의 태스크를 큐에 저장했습니다.\n";

            } catch (const json::exception& e) {
                std::cout << "🚨 [PopNextTask] JSON 파싱 에러: " << e.what() << "\n";
                return BT::NodeStatus::FAILURE;
            }
        }

        // 2. 큐가 비어있다면 대기(FAILURE 반환 -> 트리 루프 종료 또는 재시도)
        if (task_queue_.empty()) {
            return BT::NodeStatus::FAILURE; 
        }

        // 3. 큐에서 가장 앞의 태스크를 꺼냅니다.
        Task next_task = task_queue_.front();
        task_queue_.pop();

        if (next_task.target.empty()) {
            next_task.target = "none";
        }

        // 4. 다음 노드들이 쓸 수 있게 블랙보드에 값 세팅
        setOutput("action_name", next_task.action);
        setOutput("target_name", next_task.target);

        std::cout << "[PopNextTask] 🚀 다음 동작 하달 -> Action: " << next_task.action << " | Target: " << next_task.target << "\n";

        return BT::NodeStatus::SUCCESS;
    }
};