"""Tests for device emulation in animawatch.devices."""

from animawatch.devices import (
    DEVICES,
    DeviceCategory,
    DeviceProfile,
    get_device,
    list_devices,
)


class TestDeviceCategory:
    """Tests for DeviceCategory enum."""

    def test_device_categories(self) -> None:
        """Test that all device categories exist."""
        assert DeviceCategory.MOBILE.value == "mobile"
        assert DeviceCategory.TABLET.value == "tablet"
        assert DeviceCategory.DESKTOP.value == "desktop"


class TestDeviceProfile:
    """Tests for DeviceProfile dataclass."""

    def test_device_profile_creation(self) -> None:
        """Test creating a device profile."""
        profile = DeviceProfile(
            name="Test Device",
            category=DeviceCategory.MOBILE,
            width=375,
            height=667,
            device_scale_factor=2.0,
            user_agent="Mozilla/5.0 Test",
            has_touch=True,
            is_mobile=True,
        )
        assert profile.name == "Test Device"
        assert profile.category == DeviceCategory.MOBILE
        assert profile.width == 375
        assert profile.has_touch is True

    def test_device_profile_viewport(self) -> None:
        """Test viewport property."""
        profile = DeviceProfile(
            name="Test",
            category=DeviceCategory.MOBILE,
            width=375,
            height=667,
            device_scale_factor=2.0,
            user_agent="Test",
            has_touch=True,
            is_mobile=True,
        )
        viewport = profile.viewport
        assert viewport["width"] == 375
        assert viewport["height"] == 667


class TestDevices:
    """Tests for predefined device profiles."""

    def test_devices_dict_exists(self) -> None:
        """Test that DEVICES dict contains profiles."""
        assert len(DEVICES) > 0

    def test_iphone_15_pro(self) -> None:
        """Test iPhone 15 Pro profile."""
        device = DEVICES.get("iphone_15_pro")
        assert device is not None
        assert device.category == DeviceCategory.MOBILE
        assert device.has_touch is True
        assert device.is_mobile is True

    def test_ipad_pro_12(self) -> None:
        """Test iPad Pro 12.9 profile."""
        device = DEVICES.get("ipad_pro_12")
        assert device is not None
        assert device.category == DeviceCategory.TABLET

    def test_desktop_profiles(self) -> None:
        """Test desktop profiles exist."""
        desktop_devices = [d for d in DEVICES.values() if d.category == DeviceCategory.DESKTOP]
        assert len(desktop_devices) >= 1


class TestGetDevice:
    """Tests for get_device function."""

    def test_get_existing_device(self) -> None:
        """Test getting an existing device."""
        device = get_device("iphone_15_pro")
        assert device is not None
        assert device.name == "iPhone 15 Pro"

    def test_get_nonexistent_device(self) -> None:
        """Test getting a non-existent device returns None."""
        device = get_device("nonexistent_device")
        assert device is None

    def test_get_device_flexible_matching(self) -> None:
        """Test that device lookup works with flexible matching."""
        # The function normalizes keys: lowercase, replace spaces/hyphens with underscore
        device = get_device("iPhone 15 Pro")  # With spaces
        assert device is not None

    def test_get_device_with_hyphen(self) -> None:
        """Test that device lookup works with hyphens."""
        device = get_device("iphone-15-pro")
        assert device is not None


class TestListDevices:
    """Tests for list_devices function."""

    def test_list_all_devices(self) -> None:
        """Test listing all devices."""
        devices = list_devices()
        assert len(devices) == len(DEVICES)

    def test_list_mobile_devices(self) -> None:
        """Test filtering by mobile category."""
        devices = list_devices(category=DeviceCategory.MOBILE)
        assert all(d.category == DeviceCategory.MOBILE for d in devices)
        assert len(devices) > 0

    def test_list_tablet_devices(self) -> None:
        """Test filtering by tablet category."""
        devices = list_devices(category=DeviceCategory.TABLET)
        assert all(d.category == DeviceCategory.TABLET for d in devices)

    def test_list_desktop_devices(self) -> None:
        """Test filtering by desktop category."""
        devices = list_devices(category=DeviceCategory.DESKTOP)
        assert all(d.category == DeviceCategory.DESKTOP for d in devices)
