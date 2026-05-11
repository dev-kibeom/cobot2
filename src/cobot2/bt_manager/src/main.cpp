#include <rclcpp/rclcpp.hpp>
#include <behaviortree_cpp_v3/bt_factory.h>
#include <ament_index_cpp/get_package_share_directory.hpp>

#include "PickItemNode.hpp"
// #include "SearchTargetNode.hpp" 등등...

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    auto ros_node = std::make_shared<rclcpp::Node>("bt_manager_node");

    BT::BehaviorTreeFactory factory;

    // PickItemNode 등록
    BT::NodeBuilder pick_builder = [ros_node](const std::string& name, const BT::NodeConfiguration& config) {
        return std::make_unique<PickItemNode>(name, config, ros_node);
    };
    factory.registerBuilder<PickItemNode>("PickItem", pick_builder);
    
    // factory.registerNodeType<SearchTargetNode>("SearchTarget", ros_node);
    // factory.registerNodeType<ClearAlarmNode>("ClearAlarm", ros_node);
    // factory.registerNodeType<ResetPoseNode>("ResetPose", ros_node);

    // 2. XML 경로 찾기 및 로드
    std::string pkg_share = ament_index_cpp::get_package_share_directory("bt_manager");
    std::string xml_path = pkg_share + "/config/pick_place_tree.xml";
    
    auto tree = factory.createTreeFromFile(xml_path);

    // 3. 블랙보드 초기 변수 설정
    tree.rootBlackboard()->set("target_item", "shaker");

    RCLCPP_INFO(ros_node->get_logger(), "🌳 Behavior Tree 실행 시작...");

    // 4. 실행 루프
    rclcpp::Rate rate(10); // 10Hz
    BT::NodeStatus status = BT::NodeStatus::RUNNING;

    while (rclcpp::ok() && status == BT::NodeStatus::RUNNING) {
        status = tree.tickOnce();
        rclcpp::spin_some(ros_node);
        rate.sleep();
    }

    RCLCPP_INFO(ros_node->get_logger(), "🏁 Behavior Tree 실행 종료. 최종 상태: %s", BT::toStr(status).c_str());

    rclcpp::shutdown();
    return 0;
}