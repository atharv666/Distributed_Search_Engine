"""robots.txt policy checks with a cache per origin."""

from urllib import robotparser
from urllib.parse import urlparse


class RobotsPolicy:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._policies: dict[str, robotparser.RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        policy = self._policies.get(origin)
        if policy is None:
            policy = robotparser.RobotFileParser(f"{origin}/robots.txt")
            try:
                policy.read()
            except OSError:
                return False
            self._policies[origin] = policy
        return policy.can_fetch(self.user_agent, url)
