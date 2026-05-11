#include <rclcpp/rclcpp.hpp>
#include <behaviortree_cpp_v3/action_node.h>
#include <nlohmann/json.hpp>

class PickItemNode: public BT::SyncActionNode {
    private:
    rclcpp::Node::SharedPtr ros_node_;

    public:
    PickItemNode(const std::string& name, const BT::NodeConfiguration& config, rclcpp::Node::SharedPtr node):
    BT::SyncActionNode(name, config), ros_node_(node) {
        // action_client_ = rclcpp_action::create_client<command::action::Command>(ros_node_, "execute_command");
    }

    static BT::PortsList providedPorts() {
        return { BT::InputPort<std::string>("target_name")};
    }

    BT::NodeStatus tick() override {
        std::string target;
        if (!getInput<std::string>("target_name", target)) {
            RCLCPP_ERROR(ros_node_->get_logger(), "포트에서 target_name을 읽을 수 없습니다.");
            return BT::NodeStatus::FAILURE;
        }

        RCLCPP_INFO(ros_node_->get_logger(), "🤖 [%s] C++ 노드 -> Python 몸통으로 'pick_horizontal' 명령 전송!", target.c_str());

        // executer로 넘기기 위해 JSON 명령어 생성
        std::string json_cmd = "[{\"action\": \"pick_horizontal\", \"params\": {\"target\": \"" + target + "\"}}]";

        // bool_success = send_goal_and_wait(json_cmd);

        bool success = true;

        return success ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
    }
};