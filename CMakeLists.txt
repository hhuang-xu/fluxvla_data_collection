cmake_minimum_required(VERSION 3.0.2)
project(fluxvla_data_collection)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  sensor_msgs
  geometry_msgs
  message_filters
  cv_bridge
)

catkin_python_setup()

catkin_package()

catkin_install_python(PROGRAMS
  scripts/collect_data_generic_parquet.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY config
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
