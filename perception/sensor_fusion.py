"""Sensor fusion: tilt estimation and position filtering."""

from __future__ import annotations


class Kalman1D:
    """Scalar Kalman filter with a random-walk process model."""

    def __init__(self, x0: float = 0.0, p0: float = 1.0, q: float = 0.01, r: float = 0.25):
        self.x, self.p, self.q, self.r = x0, p0, q, r

    def predict(self, control: float = 0.0) -> float:
        self.x += control
        self.p += self.q
        return self.x

    def update(self, measurement: float) -> float:
        gain = self.p / (self.p + self.r)
        self.x += gain * (measurement - self.x)
        self.p *= 1.0 - gain
        return self.x

    @property
    def variance(self) -> float:
        return self.p


class ComplementaryFilter:
    """Fuses gyro rate (smooth, drifts) with accelerometer angle (noisy, no drift)."""

    def __init__(self, alpha: float = 0.98, angle0: float = 0.0):
        self.alpha = alpha
        self.angle = angle0

    def update(self, gyro_rate_rad_s: float, accel_angle_rad: float, dt: float) -> float:
        self.angle = self.alpha * (self.angle + gyro_rate_rad_s * dt) + (1.0 - self.alpha) * accel_angle_rad
        return self.angle


class SensorFusion:
    def __init__(self) -> None:
        self.tilt = ComplementaryFilter()
        self.x = Kalman1D()
        self.y = Kalman1D()

    def update_tilt(self, gyro_rate_rad_s: float, accel_angle_rad: float, dt: float) -> float:
        return self.tilt.update(gyro_rate_rad_s, accel_angle_rad, dt)

    def update_position(self, odom_dx: float, odom_dy: float,
                        measured_x: float, measured_y: float) -> tuple[float, float]:
        self.x.predict(odom_dx)
        self.y.predict(odom_dy)
        return self.x.update(measured_x), self.y.update(measured_y)
