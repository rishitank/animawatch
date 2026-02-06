"""Mobile device emulation profiles for browser testing.

Provides predefined device profiles matching common mobile and tablet devices.
Used for responsive design testing and mobile-specific animation analysis.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class DeviceCategory(str, Enum):
    """Device category for filtering."""

    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


@dataclass(frozen=True)
class DeviceProfile:
    """Device emulation profile."""

    name: str
    category: DeviceCategory
    width: int
    height: int
    device_scale_factor: float
    is_mobile: bool
    has_touch: bool
    user_agent: str

    @property
    def viewport(self) -> dict[str, int]:
        """Get viewport dict for Playwright."""
        return {"width": self.width, "height": self.height}


# User agent strings (long strings, kept on separate lines for readability)
_UA_IPHONE_17 = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
_UA_IPHONE_16 = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
_UA_IPHONE_15 = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
)
_UA_ANDROID_PIXEL = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_UA_ANDROID_GALAXY = (
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_UA_IPAD_17 = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
_UA_IPAD_16 = (
    "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
_UA_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_UA_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Common device profiles based on Playwright's device descriptors
DEVICES: dict[str, DeviceProfile] = {
    # iPhones
    "iphone_15_pro": DeviceProfile(
        name="iPhone 15 Pro",
        category=DeviceCategory.MOBILE,
        width=393,
        height=852,
        device_scale_factor=3,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_IPHONE_17,
    ),
    "iphone_14": DeviceProfile(
        name="iPhone 14",
        category=DeviceCategory.MOBILE,
        width=390,
        height=844,
        device_scale_factor=3,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_IPHONE_16,
    ),
    "iphone_se": DeviceProfile(
        name="iPhone SE",
        category=DeviceCategory.MOBILE,
        width=375,
        height=667,
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_IPHONE_15,
    ),
    # Android phones
    "pixel_8": DeviceProfile(
        name="Pixel 8",
        category=DeviceCategory.MOBILE,
        width=412,
        height=915,
        device_scale_factor=2.625,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_ANDROID_PIXEL,
    ),
    "galaxy_s24": DeviceProfile(
        name="Galaxy S24",
        category=DeviceCategory.MOBILE,
        width=360,
        height=780,
        device_scale_factor=3,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_ANDROID_GALAXY,
    ),
    # Tablets
    "ipad_pro_12": DeviceProfile(
        name="iPad Pro 12.9",
        category=DeviceCategory.TABLET,
        width=1024,
        height=1366,
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_IPAD_17,
    ),
    "ipad_air": DeviceProfile(
        name="iPad Air",
        category=DeviceCategory.TABLET,
        width=820,
        height=1180,
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        user_agent=_UA_IPAD_16,
    ),
    # Desktop viewports
    "desktop_1080p": DeviceProfile(
        name="Desktop 1080p",
        category=DeviceCategory.DESKTOP,
        width=1920,
        height=1080,
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        user_agent=_UA_WINDOWS,
    ),
    "desktop_1440p": DeviceProfile(
        name="Desktop 1440p",
        category=DeviceCategory.DESKTOP,
        width=2560,
        height=1440,
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        user_agent=_UA_MAC,
    ),
    "laptop": DeviceProfile(
        name="Laptop",
        category=DeviceCategory.DESKTOP,
        width=1366,
        height=768,
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        user_agent=_UA_WINDOWS,
    ),
}


def get_device(name: str) -> DeviceProfile | None:
    """Get a device profile by name (case-insensitive, flexible matching)."""
    key = name.lower().replace(" ", "_").replace("-", "_")
    return DEVICES.get(key)


def list_devices(category: DeviceCategory | None = None) -> list[DeviceProfile]:
    """List all available device profiles, optionally filtered by category."""
    if category is None:
        return list(DEVICES.values())
    return [d for d in DEVICES.values() if d.category == category]


DeviceName = Literal[
    "iphone_15_pro",
    "iphone_14",
    "iphone_se",
    "pixel_8",
    "galaxy_s24",
    "ipad_pro_12",
    "ipad_air",
    "desktop_1080p",
    "desktop_1440p",
    "laptop",
]
