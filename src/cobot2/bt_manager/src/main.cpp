#include <rclcpp/rclcpp.hpp>
#include <behaviortree_cpp_v3/bt_factory.h>
#include <ament_index_cpp/get_package_share_directory.hpp>

#include "PopNextTask.hpp"
#include "IsTargetRequired.hpp"
#include "ExecutePythonAction.hpp"
#include "IsTargetLocated.hpp"
#include "IsObjectGripped.hpp"

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    auto ros_node = std::make_shared<rclcpp::Node>("bt_manager");

    BT::BehaviorTreeFactory factory;

    factory.registerNodeType<PopNextTask>("PopNextTask");
    factory.registerNodeType<IsTargetRequired>("IsTargetRequired");
    factory.registerNodeType<IsTargetLocated>("IsTargetLocated"); 
    factory.registerNodeType<IsObjectGripped>("IsObjectGripped"); 

    // ExecutePythonAction 등록 (ROS 통신을 위해 ros_node 주입)
    BT::NodeBuilder execute_builder = [ros_node](const std::string& name, const BT::NodeConfiguration& config) {
        return std::make_unique<ExecutePythonAction>(name, config, ros_node);
    };
    factory.registerBuilder<ExecutePythonAction>("ExecutePythonAction", execute_builder);

    // XML 경로 찾기 및 로드
    std::string pkg_share = ament_index_cpp::get_package_share_directory("bt_manager");
    std::string xml_path = pkg_share + "/config/bt_cobot2.xml";
    
    auto tree = factory.createTreeFromFile(xml_path);

    RCLCPP_INFO(ros_node->get_logger(), "🌳 Behavior Tree 실행 시작...");

    // 블랙보드 초기 변수 설정 (나중에는 LLM 노드가 이 값을 덮어쓰게 됩니다)
    std::string test_json = R"([
        {"action": "finding", "params": {"target": "apple"}},
        {"action": "pick_horizontal", "params": {"target": "apple"}},
        {"action": "shake", "params": {"target": "none"}}
    ])";
    tree.rootBlackboard()->set("llm_json", test_json);

    // 실행 루프
    rclcpp::Rate rate(10); // 10Hz
    BT::NodeStatus status = BT::NodeStatus::RUNNING;

    while (rclcpp::ok() && status == BT::NodeStatus::RUNNING) {
        status = tree.tickRoot();
        rclcpp::spin_some(ros_node);
        rate.sleep();
    }

    RCLCPP_INFO(ros_node->get_logger(), "🏁 Behavior Tree 실행 종료. 최종 상태: %s", BT::toStr(status).c_str());

    rclcpp::shutdown();
    return 0;
}