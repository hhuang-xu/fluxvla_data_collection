"""Recording control through a std_msgs/String topic."""

import threading
from collections import deque

import rospy
from std_msgs.msg import String


VALID_COMMANDS = {"start", "stop", "cancel"}


class RecordCommandController:
    def __init__(self, command_topic):
        self.command_topic = command_topic
        self._lock = threading.Lock()
        self._commands = deque()
        self._subscriber = rospy.Subscriber(
            command_topic,
            String,
            self._callback,
            queue_size=10,
            tcp_nodelay=True,
        )

    def _callback(self, msg):
        command = (msg.data or "").strip().lower()
        if command not in VALID_COMMANDS:
            rospy.logwarn(
                "Ignoring unsupported record command '%s' on %s. Expected one of %s",
                msg.data,
                self.command_topic,
                sorted(VALID_COMMANDS),
            )
            return
        with self._lock:
            self._commands.append(command)
        rospy.loginfo("Received record command: %s", command)

    def pop_command(self):
        with self._lock:
            if not self._commands:
                return None
            return self._commands.popleft()
