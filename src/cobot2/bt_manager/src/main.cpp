#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp> // 💡 ROS String 메시지 타입 추가
#include <behaviortree_cpp_v3/bt_factory.h>
#include <ament_index_cpp/get_package_share_directory.hpp>

#include "PopNextTask.hpp"
#include "IsTargetRequired.hpp"
#include "ExecutePythonAction.hpp"
#include "IsTargetLocated.hpp"
#include "IsObjectGripped.hpp"
#include "IsResetAction.hpp"

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    auto ros_node = std::make_shared<rclcpp::Node>("bt_manager");

    BT::BehaviorTreeFactory factory;

    factory.registerNodeType<PopNextTask>("PopNextTask");
    factory.registerNodeType<IsTargetRequired>("IsTargetRequired");
    factory.registerNodeType<IsTargetLocated>("IsTargetLocated"); 
    factory.registerNodeType<IsObjectGripped>("IsObjectGripped"); 
    factory.registerNodeType<IsResetAction>("IsResetAction");
    
    BT::NodeBuilder execute_builder = [ros_node](const std::string& name, const BT::NodeConfiguration& config) {
        return std::make_unique<ExecutePythonAction>(name, config, ros_node);
    };
    factory.registerBuilder<ExecutePythonAction>("ExecutePythonAction", execute_builder);

    std::string pkg_share = ament_index_cpp::get_package_share_directory("bt_manager");
    std::string xml_path = pkg_share + "/config/bt_cobot2.xml";
    
    auto tree = factory.createTreeFromFile(xml_path);
    
    // 초기 블랙보드 비우기
    tree.rootBlackboard()->set("llm_json", "");

    // =====================================================================
    // 💡 [핵심] ROS 2 토픽을 받아서 BT 블랙보드에 연결해주는 Subscriber 생성
    // =====================================================================
    auto subscription = ros_node->create_subscription<std_msgs::msg::String>(
        "/voice_command", 10,
        [&tree, ros_node](const std_msgs::msg::String::SharedPtr msg) {
            RCLCPP_INFO(ros_node->get_logger(), "📨 외부 명령 수신! BT 블랙보드 업데이트...");
            tree.rootBlackboard()->set("llm_json", msg->data);
        });

    RCLCPP_INFO(ros_node->get_logger(), "🌳 Behavior Tree 대기 모드 시작...");

    rclcpp::Rate rate(10); // 10Hz
    BT::NodeStatus status = BT::NodeStatus::IDLE;

    while (rclcpp::ok()) {
        status = tree.tickRoot();
        rclcpp::spin_some(ros_node);
        rate.sleep();
    }

    RCLCPP_INFO(ros_node->get_logger(), "🏁 Behavior Tree 실행 종료. 최종 상태: %s", BT::toStr(status).c_str());

    rclcpp::shutdown();
    return 0;
}