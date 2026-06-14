"""Behavioral biometrics and session pattern analysis for Tranc3."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class KeystrokeFeatures:
    dwell_times: list[float]
    flight_times: list[float]
    typing_speed_cpm: float
    error_rate: float


@dataclass
class SessionProfile:
    user_id: str
    request_intervals: list[float]
    endpoint_sequence: list[str]
    avg_session_duration: float
    typical_hour_distribution: list[float]
    anomaly_score: float = 0.0


class BehavioralBiometrics:
    def __init__(self) -> None:
        self._profiles: dict[str, SessionProfile] = {}
        self._request_log: dict[str, list[tuple[float, str]]] = {}

    def record_request(
        self,
        user_id: str,
        path: str,
        timestamp: float | None = None,
    ) -> None:
        ts = timestamp if timestamp is not None else time.time()
        if user_id not in self._request_log:
            self._request_log[user_id] = []
        self._request_log[user_id].append((ts, path))

    def build_profile(self, user_id: str) -> SessionProfile:
        log = self._request_log.get(user_id, [])
        timestamps = [entry[0] for entry in log]
        paths = [entry[1] for entry in log]

        intervals: list[float] = []
        for i in range(1, len(timestamps)):
            intervals.append(timestamps[i] - timestamps[i - 1])

        avg_interval = sum(intervals) / len(intervals) if intervals else 0.0

        hour_dist = [0.0] * 24
        for ts, _ in log:
            hour = int(time.gmtime(ts).tm_hour)
            hour_dist[hour] += 1.0
        total = sum(hour_dist)
        if total > 0:
            hour_dist = [c / total for c in hour_dist]

        profile = SessionProfile(
            user_id=user_id,
            request_intervals=intervals,
            endpoint_sequence=list(paths),
            avg_session_duration=avg_interval,
            typical_hour_distribution=hour_dist,
        )
        self._profiles[user_id] = profile
        return profile

    def score_request(
        self,
        user_id: str,
        path: str,
        timestamp: float | None = None,
    ) -> dict:
        ts = timestamp if timestamp is not None else time.time()
        reasons: list[str] = []

        profile = self._profiles.get(user_id)
        log = self._request_log.get(user_id, [])

        if profile is not None:
            hour = int(time.gmtime(ts).tm_hour)
            sorted_hours = sorted(
                range(24),
                key=lambda h: profile.typical_hour_distribution[h],
                reverse=True,
            )
            top_8 = set(sorted_hours[:8])
            if hour not in top_8:
                reasons.append("unusual_hour")

            if log:
                last_ts = log[-1][0]
                interval = ts - last_ts
                if 0 <= interval < 0.1:
                    reasons.append("bot_speed")

            known_endpoints = set(profile.endpoint_sequence)
            if path not in known_endpoints:
                reasons.append("new_endpoint")

        recent = [entry for entry in log if ts - entry[0] <= 60]
        if len(recent) > 20:
            reasons.append("request_burst")

        score = min(1.0, len(reasons) * 0.25)
        return {
            "anomaly": len(reasons) > 0,
            "score": score,
            "reasons": reasons,
        }

    def analyze_keystroke(
        self,
        dwell_times: list[float],
        flight_times: list[float],
    ) -> dict:
        all_times = dwell_times + flight_times
        if not all_times:
            return {"speed_cpm": 0.0, "consistency": 0.0, "anomaly": True}

        total_time_minutes = sum(all_times) / 60000.0
        speed_cpm = (len(all_times) / total_time_minutes) if total_time_minutes > 0 else 0.0

        mean = sum(all_times) / len(all_times)
        if mean > 0 and len(all_times) > 1:
            variance = sum((t - mean) ** 2 for t in all_times) / len(all_times)
            std = math.sqrt(variance)
            consistency = max(0.0, 1.0 - std / mean)
        else:
            consistency = 1.0

        anomaly = consistency < 0.3 or speed_cpm > 1000

        return {
            "speed_cpm": round(speed_cpm, 2),
            "consistency": round(consistency, 4),
            "anomaly": anomaly,
        }

    def get_profile(self, user_id: str) -> dict | None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return None
        return {
            "user_id": profile.user_id,
            "request_intervals": profile.request_intervals,
            "endpoint_sequence": profile.endpoint_sequence,
            "avg_session_duration": profile.avg_session_duration,
            "typical_hour_distribution": profile.typical_hour_distribution,
            "anomaly_score": profile.anomaly_score,
        }

    def stats(self) -> dict:
        total_requests = sum(len(log) for log in self._request_log.values())
        return {
            "total_users_profiled": len(self._profiles),
            "total_requests_logged": total_requests,
        }
