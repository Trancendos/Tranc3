# Disable all advanced features instantly
kubectl exec deployment/tranc3-api -- python -c "
from src.core.feature_flags import FeatureFlag, FeatureFlagManager
import redis
redis_client = redis.from_url('redis://localhost:6379/0')
fm = FeatureFlagManager(redis_client)
for flag in FeatureFlag:
    fm.emergency_disable(flag)
"
